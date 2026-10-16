import httpx
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database import get_db, User, Order, Investment, Consultation, Transaction, Withdrawal, Produce
from auth import decode_token
from config import PAYSTACK_SECRET_KEY, COMMISSION_RATES, MIN_WITHDRAWAL, PLATFORM_EMAIL, PAYSTACK_CALLBACK_URL
from notifications import (notify_farmer_payment_received, notify_buyer_order_confirmed,
                           notify_buyer_order_shipped, notify_farmer_delivery_confirmed,
                           notify_investor_payment)
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

PAYSTACK_BASE = "https://api.paystack.co"
HEADERS = {
    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    "Content-Type": "application/json"
}


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def generate_reference():
    return f"AGN-{uuid.uuid4().hex[:12].upper()}"


# ===== INITIALIZE PAYMENT =====
class InitPayment(BaseModel):
    type: str  # order | investment | consultation
    related_id: int
    amount: Optional[float] = None  # for consultation only


@router.post("/payments/initialize")
async def initialize_payment(
    data: InitPayment,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    reference = generate_reference()
    amount_kobo = 0
    description = ""

    if data.type == "order":
        order = db.query(Order).filter(Order.id == data.related_id, Order.buyer_id == current_user.id).first()
        if not order:
            raise HTTPException(404, "Order not found")
        if order.payment_status == "paid":
            raise HTTPException(400, "Order already paid")
        amount_kobo = int(order.total_price * 100)
        description = f"Payment for order #{order.id}"
        order.paystack_reference = reference
        db.commit()

    elif data.type == "investment":
        investment = db.query(Investment).filter(Investment.id == data.related_id, Investment.investor_id == current_user.id).first()
        if not investment:
            raise HTTPException(404, "Investment not found")
        if investment.payment_status == "paid":
            raise HTTPException(400, "Investment already paid")
        amount_kobo = int(investment.amount * 100)
        description = f"Investment in {investment.crop}"
        investment.paystack_reference = reference
        db.commit()

    elif data.type == "consultation":
        consultation = db.query(Consultation).filter(Consultation.id == data.related_id).first()
        if not consultation:
            raise HTTPException(404, "Consultation not found")
        if not data.amount:
            raise HTTPException(400, "Amount required for consultation")
        amount_kobo = int(data.amount * 100)
        description = f"Vet consultation fee"
        consultation.fee = data.amount
        consultation.paystack_reference = reference
        db.commit()

    else:
        raise HTTPException(400, "Invalid payment type")

    # Create transaction record
    transaction = Transaction(
        user_id=current_user.id,
        reference=reference,
        amount=amount_kobo / 100,
        type=data.type,
        related_id=data.related_id,
        status="pending"
    )
    db.add(transaction)
    db.commit()

    # Initialize with Paystack
    payload = {
        "email": current_user.email,
        "amount": amount_kobo,
        "reference": reference,
        "callback_url": PAYSTACK_CALLBACK_URL,
        "metadata": {
            "type": data.type,
            "related_id": data.related_id,
            "user_id": current_user.id,
            "description": description
        }
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(f"{PAYSTACK_BASE}/transaction/initialize", json=payload, headers=HEADERS)
        result = res.json()

    if not result.get("status"):
        raise HTTPException(400, result.get("message", "Payment initialization failed"))

    return {
        "authorization_url": result["data"]["authorization_url"],
        "reference": reference,
        "amount": amount_kobo / 100
    }


# ===== VERIFY PAYMENT =====
@router.get("/payments/verify/{reference}")
async def verify_payment(
    reference: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{PAYSTACK_BASE}/transaction/verify/{reference}", headers=HEADERS)
        result = res.json()

    if not result.get("status") or result["data"]["status"] != "success":
        raise HTTPException(400, "Payment verification failed")

    metadata = result["data"].get("metadata", {})
    payment_type = metadata.get("type")
    related_id = metadata.get("related_id")
    amount = result["data"]["amount"] / 100

    # Update transaction
    transaction = db.query(Transaction).filter(Transaction.reference == reference).first()
    if transaction:
        transaction.status = "success"
        db.commit()

    if payment_type == "order":
        order = db.query(Order).filter(Order.id == related_id).first()
        if order and order.payment_status != "paid":
            commission = amount * COMMISSION_RATES["produce"]
            farmer_amount = amount - commission
            order.payment_status = "paid"
            order.commission = commission
            order.farmer_amount = farmer_amount
            order.status = "confirmed"
            # Reduce produce quantity
            produce = db.query(Produce).filter(Produce.id == order.produce_id).first()
            if produce:
                produce.quantity -= order.quantity
                if produce.quantity <= 0:
                    produce.is_available = False
            # Add to farmer pending wallet
            farmer = db.query(User).filter(User.id == order.farmer_id).first()
            if farmer:
                farmer.wallet_pending += farmer_amount
                notify_farmer_payment_received(farmer.id, order.produce.title if order.produce else "", farmer_amount)
            notify_buyer_order_confirmed(order.buyer_id, order.produce.title if order.produce else "")
            db.commit()
            return {"message": "Order payment confirmed!", "type": "order", "order_id": related_id}

    elif payment_type == "investment":
        investment = db.query(Investment).filter(Investment.id == related_id).first()
        if investment and investment.payment_status != "paid":
            commission = amount * COMMISSION_RATES["investment"]
            investment.payment_status = "paid"
            investment.commission = commission
            investment.status = "active"
            notify_investor_payment(investment.investor_id, investment.crop, investment.amount)
            db.commit()
            return {"message": "Investment payment confirmed!", "type": "investment", "investment_id": related_id}

    elif payment_type == "consultation":
        consultation = db.query(Consultation).filter(Consultation.id == related_id).first()
        if consultation and consultation.payment_status != "paid":
            commission = amount * COMMISSION_RATES["vet"]
            vet_amount = amount - commission
            consultation.payment_status = "paid"
            consultation.commission = commission
            consultation.status = "confirmed"
            vet = db.query(User).filter(User.id == consultation.vet_id).first()
            if vet:
                vet.wallet_pending += vet_amount
            db.commit()
            return {"message": "Consultation payment confirmed!", "type": "consultation"}

    return {"message": "Payment verified", "type": payment_type}


# ===== CONFIRM DELIVERY (releases funds to farmer) =====
@router.put("/orders/{order_id}/confirm-delivery")
def confirm_delivery(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id, Order.buyer_id == current_user.id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != "shipped":
        raise HTTPException(400, "Order must be shipped before confirming delivery")
    if order.payment_status != "paid":
        raise HTTPException(400, "Order must be paid first")

    order.status = "delivered"
    farmer = db.query(User).filter(User.id == order.farmer_id).first()
    if farmer:
        farmer.wallet_pending -= order.farmer_amount
        farmer.wallet_balance += order.farmer_amount
        farmer.total_earned += order.farmer_amount
        notify_farmer_delivery_confirmed(farmer.id, order.produce.title if order.produce else "", order.farmer_amount)
    db.commit()
    return {"message": "Delivery confirmed! Payment released to farmer."}


# ===== WALLET =====
@router.get("/wallet/balance")
def get_wallet(current_user: User = Depends(get_current_user)):
    return {
        "balance": current_user.wallet_balance,
        "pending": current_user.wallet_pending,
        "total_earned": current_user.total_earned
    }


# ===== WITHDRAWAL REQUEST =====
class WithdrawalRequest(BaseModel):
    amount: float
    bank_name: str
    account_number: str
    account_name: str


@router.post("/wallet/withdraw")
def request_withdrawal(
    data: WithdrawalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if data.amount < MIN_WITHDRAWAL:
        raise HTTPException(400, f"Minimum withdrawal is ₦{MIN_WITHDRAWAL:,.0f}")
    if data.amount > current_user.wallet_balance:
        raise HTTPException(400, "Insufficient wallet balance")

    current_user.wallet_balance -= data.amount
    withdrawal = Withdrawal(
        user_id=current_user.id,
        amount=data.amount,
        bank_name=data.bank_name,
        account_number=data.account_number,
        account_name=data.account_name,
        status="pending"
    )
    db.add(withdrawal)
    db.commit()
    return {"message": f"Withdrawal request of ₦{data.amount:,.0f} submitted. Processing within 24-48 hours."}


@router.get("/wallet/withdrawals")
def get_withdrawals(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    withdrawals = db.query(Withdrawal).filter(Withdrawal.user_id == current_user.id).all()
    return [{"id": w.id, "amount": w.amount, "bank_name": w.bank_name,
             "account_number": w.account_number, "account_name": w.account_name,
             "status": w.status, "created_at": str(w.created_at)} for w in withdrawals]


@router.get("/wallet/transactions")
def get_transactions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).order_by(Transaction.created_at.desc()).all()
    return [{"id": t.id, "reference": t.reference, "amount": t.amount,
             "type": t.type, "status": t.status, "created_at": str(t.created_at)} for t in transactions]


# ===== ADMIN: Process withdrawals =====
@router.get("/admin/withdrawals")
def admin_withdrawals(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_token(token)
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user or user.role != "admin":
        raise HTTPException(403, "Admin only")
    withdrawals = db.query(Withdrawal).all()
    return [{"id": w.id, "user_name": w.user.full_name, "amount": w.amount,
             "bank_name": w.bank_name, "account_number": w.account_number,
             "account_name": w.account_name, "status": w.status,
             "created_at": str(w.created_at)} for w in withdrawals]


@router.put("/admin/withdrawals/{withdrawal_id}/approve")
def approve_withdrawal(withdrawal_id: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_token(token)
    admin = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not admin or admin.role != "admin":
        raise HTTPException(403, "Admin only")
    withdrawal = db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).first()
    if not withdrawal:
        raise HTTPException(404, "Not found")
    withdrawal.status = "approved"
    withdrawal.processed_at = datetime.utcnow()
    db.commit()
    return {"message": "Withdrawal approved"}


@router.put("/admin/withdrawals/{withdrawal_id}/reject")
def reject_withdrawal(withdrawal_id: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_token(token)
    admin = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not admin or admin.role != "admin":
        raise HTTPException(403, "Admin only")
    withdrawal = db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).first()
    if not withdrawal:
        raise HTTPException(404, "Not found")
    # Refund to wallet
    withdrawal.user.wallet_balance += withdrawal.amount
    withdrawal.status = "rejected"
    withdrawal.processed_at = datetime.utcnow()
    db.commit()
    return {"message": "Withdrawal rejected and refunded to wallet"}