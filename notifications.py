from database import SessionLocal, Notification
from datetime import datetime


def send_notification(user_id: int, title: str, message: str, type: str = "info"):
    """Create a notification for a user"""
    db = SessionLocal()
    try:
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=type,
            created_at=datetime.utcnow()
        )
        db.add(notif)
        db.commit()
    except Exception as e:
        print(f"Notification error: {e}")
    finally:
        db.close()


# Notification templates
def notify_farmer_new_order(farmer_id: int, produce_title: str, quantity: int, buyer_name: str):
    send_notification(
        farmer_id,
        "🛒 New Order Received!",
        f"{buyer_name} ordered {quantity} unit(s) of {produce_title}. Please confirm the order.",
        "order"
    )

def notify_farmer_payment_received(farmer_id: int, produce_title: str, amount: float):
    send_notification(
        farmer_id,
        "💰 Payment Received!",
        f"Payment of ₦{amount:,.0f} received for {produce_title}. Funds are in your pending wallet.",
        "payment"
    )

def notify_farmer_delivery_confirmed(farmer_id: int, produce_title: str, amount: float):
    send_notification(
        farmer_id,
        "✅ Delivery Confirmed!",
        f"Buyer confirmed delivery of {produce_title}. ₦{amount:,.0f} has been released to your wallet.",
        "payment"
    )

def notify_buyer_order_confirmed(buyer_id: int, produce_title: str):
    send_notification(
        buyer_id,
        "✅ Order Confirmed!",
        f"Your order for {produce_title} has been confirmed by the farmer.",
        "order"
    )

def notify_buyer_order_shipped(buyer_id: int, produce_title: str):
    send_notification(
        buyer_id,
        "🚚 Order Shipped!",
        f"Your order for {produce_title} is on its way! Please confirm delivery when it arrives.",
        "order"
    )

def notify_farmer_vet_answer(farmer_id: int, question: str):
    send_notification(
        farmer_id,
        "🩺 Vet Answered Your Question!",
        f"A vet has answered your question: \"{question[:60]}...\"",
        "vet"
    )

def notify_investor_payment(investor_id: int, crop: str, amount: float):
    send_notification(
        investor_id,
        "💰 Investment Confirmed!",
        f"Your investment of ₦{amount:,.0f} in {crop} has been received and is now active.",
        "investment"
    )

def notify_withdrawal_approved(user_id: int, amount: float):
    send_notification(
        user_id,
        "💸 Withdrawal Approved!",
        f"Your withdrawal of ₦{amount:,.0f} has been approved and will be processed within 24 hours.",
        "payment"
    )

def notify_withdrawal_rejected(user_id: int, amount: float):
    send_notification(
        user_id,
        "❌ Withdrawal Rejected",
        f"Your withdrawal of ₦{amount:,.0f} was rejected. The amount has been refunded to your wallet.",
        "payment"
    )

def notify_user_verified(user_id: int, role: str):
    send_notification(
        user_id,
        "✅ Account Verified!",
        f"Congratulations! Your {role} account has been verified. You now have full access to AgriNet.",
        "info"
    )