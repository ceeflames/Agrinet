from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse as JSONResp
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
import os, shutil, uuid

from database import get_db, init_db, User, UserDocument, Produce, Order, Investment, VetQuestion, Consultation, Withdrawal, Transaction, Notification, ColdRoom, ColdRoomBooking, Equipment, Farmland, EquipmentBooking, FarmlandBooking
from payments import router as payments_router
from auth import verify_password, get_password_hash, create_access_token, decode_token, generate_otp, send_otp_sms, normalize_phone
from notifications import (notify_farmer_new_order, notify_buyer_order_shipped, notify_farmer_vet_answer, notify_user_verified, notify_withdrawal_approved, notify_withdrawal_rejected)
from config import COMMISSION_RATES

app = FastAPI(title="AgriNet API", version="3.0")
app.include_router(payments_router)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "; ".join([f"{' -> '.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors])
    return JSONResp(status_code=422, content={"detail": msg})

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

@app.on_event("startup")
def startup():
    init_db()

from starlette.middleware.base import BaseHTTPMiddleware
class HTTPSProxyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.scope["scheme"] = "https"
        return await call_next(request)
app.add_middleware(HTTPSProxyMiddleware)


# --- HELPERS ---
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

def save_upload(file: UploadFile, subfolder: str) -> str:
    folder = os.path.join(UPLOAD_DIR, subfolder)
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return f"/uploads/{subfolder}/{filename}"


# --- FRONTEND ROUTES ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    produce = db.query(Produce).filter(Produce.is_available == True).all()
    listings = [{"id": p.id, "title": p.title, "category": p.category, "price": p.price,
                 "unit": p.unit, "location": p.location, "image_path": p.image_path,
                 "sellerVerified": True} for p in produce] or [
        {"id": 1, "title": "Maize (100kg bags)", "category": "grains", "price": 43000, "unit": "bag", "location": "Kaduna", "sellerVerified": True},
        {"id": 2, "title": "Tomatoes (25kg crates)", "category": "vegetables", "price": 12000, "unit": "crate", "location": "Kano", "sellerVerified": True},
    ]
    return templates.TemplateResponse("index.html", {"request": request, "listings": listings,
        "equipment": [], "coldRooms": [], "categories": [{"key": "grains", "label": "Grains"}, {"key": "vegetables", "label": "Vegetables"}],
        "cities": ["Lagos", "Abuja", "Kano", "Port Harcourt", "Kaduna"], "query": "", "cat": None, "cart_count": 0, "year": 2025, "city": "Lagos", "forecast": []})

@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard_redirect.html", {"request": request})

@app.get("/farmer-dashboard", response_class=HTMLResponse)
def farmer_dashboard(request: Request):
    return templates.TemplateResponse("farmer_dashboard.html", {"request": request})

@app.get("/consumer-dashboard", response_class=HTMLResponse)
def consumer_dashboard(request: Request):
    return templates.TemplateResponse("consumer_dashboard.html", {"request": request})

@app.get("/investor-dashboard", response_class=HTMLResponse)
def investor_dashboard(request: Request):
    return templates.TemplateResponse("investor_dashboard.html", {"request": request})

@app.get("/vet-dashboard", response_class=HTMLResponse)
def vet_dashboard(request: Request):
    return templates.TemplateResponse("vet_dashboard.html", {"request": request})

@app.get("/verify-otp", response_class=HTMLResponse)
def verify_otp_page(request: Request):
    return templates.TemplateResponse("verify_otp.html", {"request": request})


# --- AUTH ---
@app.post("/auth/register")
async def register(
    full_name: str = Form(...), email: str = Form(...), phone: str = Form(...),
    password: str = Form(...), role: str = Form(...),
    nin: UploadFile = File(None), cac: UploadFile = File(None),
    farm_photo: UploadFile = File(None), bank_details: UploadFile = File(None),
    vet_license: UploadFile = File(None), db: Session = Depends(get_db)
):
    if role not in ["farmer", "vet", "consumer", "investor", "vendor"]:
        raise HTTPException(400, "Invalid role")
    phone = normalize_phone(phone)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email already registered")
    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(400, "Phone already registered")
    otp = generate_otp()
    user = User(full_name=full_name, email=email, phone=phone,
                password_hash=get_password_hash(password), role=role,
                otp_code=otp, otp_expires=datetime.utcnow() + timedelta(minutes=10))
    db.add(user); db.commit(); db.refresh(user)
    for doc_type, file in [("nin", nin), ("cac", cac), ("farm_photo", farm_photo), ("bank_details", bank_details), ("vet_license", vet_license)]:
        if file and file.filename:
            path = save_upload(file, f"docs/{user.id}")
            db.add(UserDocument(user_id=user.id, doc_type=doc_type, file_path=path))
    db.commit()
    sent = send_otp_sms(phone, otp)
    msg = "Registration successful. OTP sent." if sent else "Account created, but the SMS could not be sent. Tap Resend OTP."
    return JSONResponse({"message": msg, "user_id": user.id, "sms_sent": sent})

@app.post("/auth/verify-otp")
def verify_otp(user_id: int = Form(...), otp: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    if user.otp_code != otp: raise HTTPException(400, "Invalid OTP")
    if user.otp_expires < datetime.utcnow(): raise HTTPException(400, "OTP expired")
    user.is_phone_verified = True; user.otp_code = None; user.otp_expires = None
    db.commit()
    token = create_access_token({"user_id": user.id, "role": user.role})
    return JSONResponse({"message": "Phone verified!", "token": token, "role": user.role})

@app.post("/auth/resend-otp")
def resend_otp(user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    otp = generate_otp()
    user.otp_code = otp; user.otp_expires = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    if not send_otp_sms(user.phone, otp):
        raise HTTPException(502, "Could not send SMS. Please try again shortly.")
    return {"message": "OTP resent"}

@app.post("/auth/login")
def login(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(400, "Invalid email or password")
    if not user.is_phone_verified:
        raise HTTPException(400, "Please verify your phone first")
    token = create_access_token({"user_id": user.id, "role": user.role})
    return JSONResponse({"token": token, "role": user.role, "name": user.full_name})

@app.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "full_name": current_user.full_name, "email": current_user.email,
            "phone": current_user.phone, "role": current_user.role, "is_verified": current_user.is_verified,
            "verification_status": current_user.verification_status, "bio": current_user.bio,
            "farm_location": current_user.farm_location, "farm_lat": current_user.farm_lat, "farm_lng": current_user.farm_lng}

class ProfileUpdate(BaseModel):
    bio: Optional[str] = None

@app.put("/auth/update-profile")
def update_profile(data: ProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.bio is not None: current_user.bio = data.bio
    db.commit()
    return {"message": "Profile updated"}


# --- PRODUCE ---
@app.post("/produce/add")
async def add_produce(
    title: str = Form(...), category: str = Form(...), price: int = Form(...),
    unit: str = Form(...), quantity: int = Form(...), location: str = Form(...),
    description: str = Form(None), image: UploadFile = File(None),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if current_user.role != "farmer": raise HTTPException(403, "Only farmers can add produce")
    image_path = save_upload(image, "produce") if image and image.filename else None
    produce = Produce(farmer_id=current_user.id, title=title, category=category, price=price,
                      unit=unit, quantity=quantity, location=location, description=description, image_path=image_path)
    db.add(produce); db.commit(); db.refresh(produce)
    return {"message": "Produce listed!", "id": produce.id}

@app.get("/produce")
def get_produce(category: Optional[str] = None, query: Optional[str] = None, db: Session = Depends(get_db)):
    results = db.query(Produce).filter(Produce.is_available == True)
    if category: results = results.filter(Produce.category == category)
    if query: results = results.filter(Produce.title.ilike(f"%{query}%"))
    return [{"id": p.id, "title": p.title, "category": p.category, "price": p.price,
             "unit": p.unit, "quantity": p.quantity, "location": p.location,
             "image_path": p.image_path, "farmer_id": p.farmer_id} for p in results.all()]

@app.get("/farmer/my-produce")
def my_produce(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "farmer": raise HTTPException(403, "Farmers only")
    produce = db.query(Produce).filter(Produce.farmer_id == current_user.id, Produce.is_available == True).all()
    return [{"id": p.id, "title": p.title, "category": p.category, "price": p.price,
             "unit": p.unit, "quantity": p.quantity, "location": p.location, "image_path": p.image_path} for p in produce]

@app.delete("/produce/{produce_id}")
def delete_produce(produce_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    produce = db.query(Produce).filter(Produce.id == produce_id).first()
    if not produce: raise HTTPException(404, "Not found")
    if produce.farmer_id != current_user.id: raise HTTPException(403, "Not your listing")
    produce.is_available = False; db.commit()
    return {"message": "Removed"}


# --- FARMER LOCATION ---
class LocationUpdate(BaseModel):
    farm_location: str
    farm_lat: Optional[float] = None
    farm_lng: Optional[float] = None

@app.put("/farmer/location")
def update_location(data: LocationUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "farmer": raise HTTPException(403, "Farmers only")
    current_user.farm_location = data.farm_location
    current_user.farm_lat = data.farm_lat
    current_user.farm_lng = data.farm_lng
    db.commit()
    return {"message": "Location saved"}


# --- ORDERS ---
class OrderPlace(BaseModel):
    produce_id: int
    quantity: int
    delivery_address: str

@app.post("/orders/place")
def place_order(data: OrderPlace, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "consumer": raise HTTPException(403, "Buyers only")
    produce = db.query(Produce).filter(Produce.id == data.produce_id).first()
    if not produce: raise HTTPException(404, "Produce not found")
    total = produce.price * data.quantity
    order = Order(buyer_id=current_user.id, farmer_id=produce.farmer_id, produce_id=data.produce_id,
                  quantity=data.quantity, total_price=total, delivery_address=data.delivery_address)
    db.add(order); db.commit(); db.refresh(order)
    notify_farmer_new_order(produce.farmer_id, produce.title, data.quantity, current_user.full_name)
    return {"message": "Order placed!", "order_id": order.id}

@app.get("/buyer/orders")
def buyer_orders(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "consumer": raise HTTPException(403, "Buyers only")
    orders = db.query(Order).filter(Order.buyer_id == current_user.id).all()
    return [{"id": o.id, "produce_title": o.produce.title if o.produce else "", "quantity": o.quantity,
             "total_price": o.total_price, "status": o.status, "payment_status": o.payment_status,
             "created_at": str(o.created_at)} for o in orders]

@app.get("/farmer/orders")
def farmer_orders(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "farmer": raise HTTPException(403, "Farmers only")
    orders = db.query(Order).filter(Order.farmer_id == current_user.id).all()
    return [{"id": o.id, "produce_title": o.produce.title if o.produce else "", "quantity": o.quantity,
             "total_price": o.total_price, "farmer_amount": o.farmer_amount, "status": o.status,
             "payment_status": o.payment_status, "buyer_name": o.buyer.full_name if o.buyer else "",
             "delivery_address": o.delivery_address, "created_at": str(o.created_at)} for o in orders]

class StatusUpdate(BaseModel):
    status: str

@app.put("/orders/{order_id}/status")
def update_order_status(order_id: int, data: StatusUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order: raise HTTPException(404, "Order not found")
    if order.farmer_id != current_user.id: raise HTTPException(403, "Not your order")
    order.status = data.status; db.commit()
    if data.status == "shipped":
        notify_buyer_order_shipped(order.buyer_id, order.produce.title if order.produce else "your order")
    return {"message": "Status updated"}


# --- INVESTMENTS ---
class InvestmentPledge(BaseModel):
    crop: str
    amount: int
    tenor: str
    expected_return: Optional[float] = None

@app.post("/investments/pledge")
def pledge_investment(data: InvestmentPledge, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "investor": raise HTTPException(403, "Investors only")
    investment = Investment(investor_id=current_user.id, crop=data.crop, amount=data.amount,
                            tenor=data.tenor, expected_return=data.expected_return)
    db.add(investment); db.commit()
    return {"message": "Investment pledged!", "id": investment.id}

@app.get("/investments/my")
def my_investments(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "investor": raise HTTPException(403, "Investors only")
    investments = db.query(Investment).filter(Investment.investor_id == current_user.id).all()
    return [{"id": i.id, "crop": i.crop, "amount": i.amount, "tenor": i.tenor,
             "expected_return": i.expected_return, "status": i.status, "created_at": str(i.created_at)} for i in investments]

@app.get("/farmers/profiles")
def farmer_profiles(db: Session = Depends(get_db)):
    farmers = db.query(User).filter(User.role == "farmer", User.is_phone_verified == True).all()
    return [{"id": f.id, "full_name": f.full_name, "farm_location": f.farm_location,
             "produce_count": len([p for p in f.produce if p.is_available])} for f in farmers]


# --- VET ---
class VetQuestionCreate(BaseModel):
    question: str

@app.post("/vet/ask")
def ask_vet(data: VetQuestionCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = VetQuestion(user_id=current_user.id, question=data.question)
    db.add(q); db.commit()
    return {"message": "Question submitted"}

@app.get("/vet/my-questions")
def my_questions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    questions = db.query(VetQuestion).filter(VetQuestion.user_id == current_user.id).all()
    return [{"id": q.id, "question": q.question, "answer": q.answer, "status": q.status,
             "created_at": str(q.created_at), "answered_at": str(q.answered_at) if q.answered_at else None} for q in questions]

@app.get("/vet/questions")
def all_questions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "vet": raise HTTPException(403, "Vets only")
    questions = db.query(VetQuestion).all()
    return [{"id": q.id, "question": q.question, "answer": q.answer, "status": q.status,
             "user_name": q.user.full_name if q.user else "", "created_at": str(q.created_at),
             "answered_at": str(q.answered_at) if q.answered_at else None} for q in questions]

class AnswerUpdate(BaseModel):
    answer: str

@app.put("/vet/answer/{question_id}")
def answer_question(question_id: int, data: AnswerUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "vet": raise HTTPException(403, "Vets only")
    q = db.query(VetQuestion).filter(VetQuestion.id == question_id).first()
    if not q: raise HTTPException(404, "Question not found")
    q.answer = data.answer; q.vet_id = current_user.id; q.status = "answered"; q.answered_at = datetime.utcnow()
    db.commit()
    return {"message": "Answer submitted"}


# --- CONSULTATIONS ---
class ConsultationCreate(BaseModel):
    topic: str
    scheduled_at: str
    notes: Optional[str] = None

@app.post("/vet/consultations")
def create_consultation(data: ConsultationCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "vet": raise HTTPException(403, "Vets only")
    c = Consultation(vet_id=current_user.id, farmer_id=current_user.id,
                     scheduled_at=datetime.fromisoformat(data.scheduled_at),
                     topic=data.topic, notes=data.notes)
    db.add(c); db.commit()
    return {"message": "Consultation scheduled"}

@app.get("/vet/consultations")
def get_consultations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "vet": raise HTTPException(403, "Vets only")
    consultations = db.query(Consultation).filter(Consultation.vet_id == current_user.id).all()
    return [{"id": c.id, "topic": c.topic, "scheduled_at": str(c.scheduled_at),
             "status": c.status, "notes": c.notes} for c in consultations]


# --- PASSWORD RESET ---
@app.post("/auth/request-reset")
def request_reset(email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "Email not found")
    otp = generate_otp()
    user.otp_code = otp
    user.otp_expires = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    send_otp_sms(user.phone, otp)
    return JSONResponse({"message": "OTP sent", "user_id": user.id})

@app.post("/auth/reset-password")
def reset_password(
    user_id: int = Form(...), otp: str = Form(...),
    new_password: str = Form(...), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.otp_code != otp:
        raise HTTPException(400, "Invalid OTP")
    if user.otp_expires < datetime.utcnow():
        raise HTTPException(400, "OTP expired")
    user.password_hash = get_password_hash(new_password)
    user.otp_code = None
    user.otp_expires = None
    db.commit()
    return {"message": "Password reset successfully"}


# --- ADMIN: Verify Users ---
@app.put("/admin/verify-user/{user_id}")
def verify_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.is_verified = True
    user.verification_status = "verified"
    db.commit()
    return {"message": f"{user.full_name} verified successfully"}

@app.get("/admin/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": u.id, "full_name": u.full_name, "email": u.email,
             "role": u.role, "is_verified": u.is_verified,
             "verification_status": u.verification_status} for u in users]


# --- ADMIN ROUTES ---
@app.get("/admin-dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin_dashboard.html", {"request": request})

def get_admin_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access only")
    return user

@app.get("/admin/analytics")
def admin_analytics(current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    users = db.query(User).all()
    produce = db.query(Produce).all()
    orders = db.query(Order).all()
    investments = db.query(Investment).all()
    questions = db.query(VetQuestion).all()
    return {
        "total_users": len(users),
        "farmers": len([u for u in users if u.role == "farmer"]),
        "consumers": len([u for u in users if u.role == "consumer"]),
        "investors": len([u for u in users if u.role == "investor"]),
        "vets": len([u for u in users if u.role == "vet"]),
        "pending_verification": len([u for u in users if u.verification_status == "pending"]),
        "verified_users": len([u for u in users if u.verification_status == "verified"]),
        "suspended_users": len([u for u in users if u.verification_status == "suspended"]),
        "total_produce": len([p for p in produce if p.is_available]),
        "total_orders": len(orders),
        "total_invested": sum(i.amount for i in investments),
        "total_questions": len(questions),
    }

@app.get("/admin/users")
def admin_list_users(current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone,
             "role": u.role, "is_verified": u.is_verified, "verification_status": u.verification_status,
             "created_at": str(u.created_at)} for u in users]

@app.put("/admin/verify-user/{user_id}")
def admin_verify_user(user_id: int, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    user.is_verified = True
    user.verification_status = "verified"
    db.commit()
    return {"message": f"{user.full_name} verified"}

@app.put("/admin/reject-user/{user_id}")
def admin_reject_user(user_id: int, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    user.is_verified = False
    user.verification_status = "rejected"
    db.commit()
    return {"message": f"{user.full_name} rejected"}

@app.put("/admin/suspend-user/{user_id}")
def admin_suspend_user(user_id: int, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    user.verification_status = "suspended"
    user.is_verified = False
    db.commit()
    return {"message": f"{user.full_name} suspended"}

@app.delete("/admin/delete-user/{user_id}")
def admin_delete_user(user_id: int, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

@app.get("/admin/produce")
def admin_list_produce(current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    produce = db.query(Produce).all()
    return [{"id": p.id, "title": p.title, "category": p.category, "price": p.price,
             "quantity": p.quantity, "location": p.location, "is_available": p.is_available,
             "farmer_name": p.farmer.full_name if p.farmer else ""} for p in produce]

@app.put("/admin/remove-produce/{produce_id}")
def admin_remove_produce(produce_id: int, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    produce = db.query(Produce).filter(Produce.id == produce_id).first()
    if not produce: raise HTTPException(404, "Not found")
    produce.is_available = False
    db.commit()
    return {"message": "Produce removed"}

@app.get("/admin/orders")
def admin_list_orders(current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    return [{"id": o.id, "produce_title": o.produce.title if o.produce else "",
             "buyer_name": o.buyer.full_name if o.buyer else "",
             "farmer_name": o.farmer.full_name if o.farmer else "",
             "quantity": o.quantity, "total_price": o.total_price,
             "status": o.status, "created_at": str(o.created_at)} for o in orders]

@app.get("/admin/investments")
def admin_list_investments(current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    investments = db.query(Investment).all()
    return [{"id": i.id, "investor_name": i.investor.full_name if i.investor else "",
             "crop": i.crop, "amount": i.amount, "expected_return": i.expected_return,
             "tenor": i.tenor, "status": i.status, "created_at": str(i.created_at)} for i in investments]

@app.get("/admin/vet-questions")
def admin_list_questions(current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    questions = db.query(VetQuestion).all()
    return [{"id": q.id, "question": q.question, "answer": q.answer,
             "user_name": q.user.full_name if q.user else "",
             "status": q.status, "created_at": str(q.created_at)} for q in questions]


# --- WALLET PAGE ---
@app.get("/wallet", response_class=HTMLResponse)
def wallet_page(request: Request):
    return templates.TemplateResponse("wallet.html", {"request": request})


# --- PAYSTACK CALLBACK ---
@app.get("/payments/callback", response_class=HTMLResponse)
async def payment_callback(request: Request, reference: str = None):
    """Paystack redirects here after payment"""
    return templates.TemplateResponse("payment_callback.html", {"request": request, "reference": reference})


# --- NOTIFICATIONS ---
@app.get("/notifications")
def get_notifications(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notifications = db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).order_by(Notification.created_at.desc()).limit(50).all()
    return [{"id": n.id, "title": n.title, "message": n.message,
             "type": n.type, "is_read": n.is_read,
             "created_at": str(n.created_at)} for n in notifications]

@app.put("/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notif = db.query(Notification).filter(
        Notification.id == notif_id, Notification.user_id == current_user.id
    ).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"message": "Marked as read"}

@app.put("/notifications/read-all")
def mark_all_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(
        Notification.user_id == current_user.id, Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"message": "All marked as read"}


# --- COLD ROOMS ---
@app.get("/cold-rooms")
def get_cold_rooms(state: Optional[str] = None, db: Session = Depends(get_db)):
    rooms = db.query(ColdRoom).filter(ColdRoom.is_active == True)
    if state:
        rooms = rooms.filter(ColdRoom.state == state)
    return [{"id": r.id, "name": r.name, "city": r.city, "state": r.state,
             "temperature": r.temperature, "rate_per_day": r.rate_per_day,
             "total_slots": r.total_slots, "available_slots": r.available_slots,
             "address": r.address, "image_path": r.image_path} for r in rooms.all()]


class ColdRoomBookingCreate(BaseModel):
    cold_room_id: int
    produce_description: str
    quantity_tons: float
    start_date: str
    end_date: str


@app.post("/cold-rooms/book")
def book_cold_room(
    data: ColdRoomBookingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role not in ["farmer", "consumer"]:
        raise HTTPException(403, "Only farmers and consumers can book cold rooms")
    if not current_user.is_phone_verified:
        raise HTTPException(403, "Please verify your phone number first")
    cold_room = db.query(ColdRoom).filter(ColdRoom.id == data.cold_room_id).first()
    if not cold_room:
        raise HTTPException(404, "Cold room not found")
    if cold_room.available_slots <= 0:
        raise HTTPException(400, "No slots available")

    start = datetime.fromisoformat(data.start_date)
    end = datetime.fromisoformat(data.end_date)
    days = max(1, (end - start).days)
    total_cost = days * cold_room.rate_per_day
    commission = total_cost * 0.05

    booking = ColdRoomBooking(
        user_id=current_user.id,
        cold_room_id=data.cold_room_id,
        produce_description=data.produce_description,
        quantity_tons=data.quantity_tons,
        start_date=start,
        end_date=end,
        days=days,
        total_cost=total_cost,
        commission=commission,
        status="pending",
        payment_status="unpaid"
    )
    db.add(booking)
    cold_room.available_slots -= 1
    db.commit()
    db.refresh(booking)

    from notifications import send_notification
    send_notification(current_user.id, "❄️ Cold Room Booking Requested",
                     f"Your booking at {cold_room.name} for {days} days has been submitted. Total cost: ₦{total_cost:,.0f}. Proceed to payment.",
                     "info")
    return {"message": "Booking created!", "booking_id": booking.id, "total_cost": total_cost, "days": days}


@app.get("/cold-rooms/my-bookings")
def my_cold_room_bookings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bookings = db.query(ColdRoomBooking).filter(ColdRoomBooking.user_id == current_user.id).all()
    return [{"id": b.id, "cold_room_name": b.cold_room.name if b.cold_room else "",
             "cold_room_city": b.cold_room.city if b.cold_room else "",
             "produce_description": b.produce_description, "quantity_tons": b.quantity_tons,
             "start_date": str(b.start_date), "end_date": str(b.end_date),
             "days": b.days, "total_cost": b.total_cost, "status": b.status,
             "payment_status": b.payment_status, "created_at": str(b.created_at)} for b in bookings]


@app.get("/cold-room-booking", response_class=HTMLResponse)
def cold_room_booking_page(request: Request):
    return templates.TemplateResponse("cold_room_booking.html", {"request": request})


# --- VENDOR ROUTES ---
@app.get("/vendor-dashboard", response_class=HTMLResponse)
def vendor_dashboard(request: Request):
    return templates.TemplateResponse("vendor_dashboard.html", {"request": request})


# --- EQUIPMENT ---
@app.post("/equipment/add")
async def add_equipment(
    title: str = Form(...), description: str = Form(None),
    category: str = Form(...), listing_type: str = Form(...),
    price: float = Form(...), rent_period: str = Form(None),
    condition: str = Form("good"), location: str = Form(...),
    state: str = Form(...), image: UploadFile = File(None),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if current_user.role not in ["vendor", "farmer", "admin"]:
        raise HTTPException(403, "Not authorized to list equipment")
    if not current_user.is_verified:
        raise HTTPException(403, "Account must be verified first")
    image_path = save_upload(image, "equipment") if image and image.filename else None
    eq = Equipment(vendor_id=current_user.id, title=title, description=description,
                   category=category, listing_type=listing_type, price=price,
                   rent_period=rent_period, condition=condition, location=location,
                   state=state, image_path=image_path)
    db.add(eq); db.commit(); db.refresh(eq)
    return {"message": "Equipment listed!", "id": eq.id}


@app.get("/equipment")
def get_equipment(state: Optional[str] = None, listing_type: Optional[str] = None,
                  db: Session = Depends(get_db)):
    results = db.query(Equipment).filter(Equipment.is_available == True)
    if state: results = results.filter(Equipment.state == state)
    if listing_type: results = results.filter(Equipment.listing_type == listing_type)
    return [{"id": e.id, "title": e.title, "description": e.description,
             "category": e.category, "listing_type": e.listing_type, "price": e.price,
             "rent_period": e.rent_period, "condition": e.condition, "location": e.location,
             "state": e.state, "image_path": e.image_path,
             "vendor_name": e.vendor.full_name if e.vendor else ""} for e in results.all()]


@app.get("/vendor/my-equipment")
def my_equipment(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Equipment).filter(Equipment.vendor_id == current_user.id).all()
    return [{"id": e.id, "title": e.title, "category": e.category, "listing_type": e.listing_type,
             "price": e.price, "condition": e.condition, "location": e.location,
             "state": e.state, "image_path": e.image_path, "is_available": e.is_available} for e in items]


@app.delete("/equipment/{equipment_id}")
def delete_equipment(equipment_id: int, current_user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    eq = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not eq: raise HTTPException(404, "Not found")
    if eq.vendor_id != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Not your listing")
    eq.is_available = False; db.commit()
    return {"message": "Removed"}


class EquipmentBookingCreate(BaseModel):
    equipment_id: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@app.post("/equipment/book")
def book_equipment(data: EquipmentBookingCreate, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if current_user.role not in ["farmer", "consumer"]:
        raise HTTPException(403, "Only farmers and consumers can book equipment")
    if not current_user.is_phone_verified:
        raise HTTPException(403, "Please verify your phone number first")
    eq = db.query(Equipment).filter(Equipment.id == data.equipment_id).first()
    if not eq: raise HTTPException(404, "Equipment not found")
    total_cost = eq.price
    if eq.listing_type == "rent" and data.start_date and data.end_date:
        start = datetime.fromisoformat(data.start_date)
        end = datetime.fromisoformat(data.end_date)
        days = max(1, (end - start).days)
        total_cost = eq.price * days
    commission = total_cost * COMMISSION_RATES.get("equipment_rent", 0.08)
    booking = EquipmentBooking(user_id=current_user.id, equipment_id=data.equipment_id,
                               start_date=datetime.fromisoformat(data.start_date) if data.start_date else None,
                               end_date=datetime.fromisoformat(data.end_date) if data.end_date else None,
                               total_cost=total_cost, commission=commission)
    db.add(booking); db.commit(); db.refresh(booking)
    from notifications import send_notification
    send_notification(eq.vendor_id, "🚜 New Equipment Booking!",
                     f"{current_user.full_name} booked your {eq.title}. Total: ₦{total_cost:,.0f}", "order")
    return {"message": "Equipment booked!", "booking_id": booking.id, "total_cost": total_cost}


@app.get("/equipment/my-bookings")
def my_equipment_bookings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bookings = db.query(EquipmentBooking).filter(EquipmentBooking.user_id == current_user.id).all()
    return [{"id": b.id, "equipment_title": b.equipment.title if b.equipment else "",
             "total_cost": b.total_cost, "status": b.status, "payment_status": b.payment_status,
             "created_at": str(b.created_at)} for b in bookings]


# --- FARMLAND ---
@app.post("/farmland/add")
async def add_farmland(
    title: str = Form(...), description: str = Form(None),
    size_hectares: float = Form(...), soil_type: str = Form(None),
    water_source: str = Form(None), location: str = Form(...),
    state: str = Form(...), address: str = Form(None),
    lat: float = Form(None), lng: float = Form(None),
    price_per_season: float = Form(...), rent_period: str = Form("season"),
    image: UploadFile = File(None),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if current_user.role not in ["vendor", "farmer", "admin"]:
        raise HTTPException(403, "Not authorized to list farmland")
    if not current_user.is_verified:
        raise HTTPException(403, "Account must be verified first")
    image_path = save_upload(image, "farmland") if image and image.filename else None
    land = Farmland(vendor_id=current_user.id, title=title, description=description,
                    size_hectares=size_hectares, soil_type=soil_type, water_source=water_source,
                    location=location, state=state, address=address, lat=lat, lng=lng,
                    price_per_season=price_per_season, rent_period=rent_period, image_path=image_path)
    db.add(land); db.commit(); db.refresh(land)
    return {"message": "Farmland listed!", "id": land.id}


@app.get("/farmland")
def get_farmland(state: Optional[str] = None, db: Session = Depends(get_db)):
    results = db.query(Farmland).filter(Farmland.is_available == True)
    if state: results = results.filter(Farmland.state == state)
    return [{"id": l.id, "title": l.title, "description": l.description,
             "size_hectares": l.size_hectares, "soil_type": l.soil_type,
             "water_source": l.water_source, "location": l.location, "state": l.state,
             "address": l.address, "lat": l.lat, "lng": l.lng,
             "price_per_season": l.price_per_season, "rent_period": l.rent_period,
             "image_path": l.image_path, "vendor_name": l.vendor.full_name if l.vendor else ""} for l in results.all()]


@app.get("/vendor/my-farmland")
def my_farmland(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Farmland).filter(Farmland.vendor_id == current_user.id).all()
    return [{"id": l.id, "title": l.title, "size_hectares": l.size_hectares,
             "location": l.location, "state": l.state, "price_per_season": l.price_per_season,
             "rent_period": l.rent_period, "image_path": l.image_path,
             "is_available": l.is_available} for l in items]


class FarmlandBookingCreate(BaseModel):
    farmland_id: int
    start_date: str
    end_date: str


@app.post("/farmland/book")
def book_farmland(data: FarmlandBookingCreate, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if current_user.role not in ["farmer", "consumer"]:
        raise HTTPException(403, "Only farmers and consumers can book farmland")
    if not current_user.is_phone_verified:
        raise HTTPException(403, "Please verify your phone number first")
    land = db.query(Farmland).filter(Farmland.id == data.farmland_id).first()
    if not land: raise HTTPException(404, "Farmland not found")
    if not land.is_available: raise HTTPException(400, "Farmland not available")
    total_cost = land.price_per_season
    commission = total_cost * 0.06
    booking = FarmlandBooking(user_id=current_user.id, farmland_id=data.farmland_id,
                              start_date=datetime.fromisoformat(data.start_date),
                              end_date=datetime.fromisoformat(data.end_date),
                              total_cost=total_cost, commission=commission)
    db.add(booking); db.commit(); db.refresh(booking)
    from notifications import send_notification
    send_notification(land.vendor_id, "🌱 New Farmland Booking!",
                     f"{current_user.full_name} wants to rent your land: {land.title}. Total: ₦{total_cost:,.0f}", "order")
    return {"message": "Farmland booking submitted!", "booking_id": booking.id, "total_cost": total_cost}


# --- VENDOR: Add cold room ---
@app.post("/vendor/cold-rooms/add")
async def vendor_add_cold_room(
    name: str = Form(...), city: str = Form(...), state: str = Form(...),
    temperature: str = Form(...), rate_per_day: float = Form(...),
    total_slots: int = Form(...), address: str = Form(None),
    image: UploadFile = File(None),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if current_user.role not in ["vendor", "admin"]:
        raise HTTPException(403, "Only vendors can add cold rooms")
    if not current_user.is_verified:
        raise HTTPException(403, "Account must be verified first")
    image_path = save_upload(image, "cold_rooms") if image and image.filename else None
    room = ColdRoom(name=name, city=city, state=state, temperature=temperature,
                    rate_per_day=rate_per_day, total_slots=total_slots,
                    available_slots=total_slots, address=address, image_path=image_path)
    db.add(room); db.commit()
    return {"message": "Cold room listed successfully!"}


@app.get("/vendor/my-cold-rooms")
def my_cold_rooms(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["vendor", "admin"]:
        raise HTTPException(403, "Vendors only")
    # For now return all rooms if admin, or ones matching vendor name
    rooms = db.query(ColdRoom).all()
    return [{"id": r.id, "name": r.name, "city": r.city, "state": r.state,
             "temperature": r.temperature, "rate_per_day": r.rate_per_day,
             "total_slots": r.total_slots, "available_slots": r.available_slots,
             "is_active": r.is_active} for r in rooms]


# Admin endpoints for equipment and farmland
@app.get("/admin/equipment")
def admin_equipment(current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    items = db.query(Equipment).all()
    return [{"id": e.id, "title": e.title, "vendor_name": e.vendor.full_name if e.vendor else "",
             "category": e.category, "listing_type": e.listing_type, "price": e.price,
             "state": e.state, "is_available": e.is_available} for e in items]


@app.get("/admin/farmland")
def admin_farmland(current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    items = db.query(Farmland).all()
    return [{"id": l.id, "title": l.title, "vendor_name": l.vendor.full_name if l.vendor else "",
             "size_hectares": l.size_hectares, "state": l.state,
             "price_per_season": l.price_per_season, "is_available": l.is_available} for l in items]


# --- FARMLAND PAGE ---
@app.get("/farmland-listing", response_class=HTMLResponse)
def farmland_listing_page(request: Request):
    return templates.TemplateResponse("farmland_listing.html", {"request": request})

@app.get("/equipment-listing", response_class=HTMLResponse)
def equipment_listing_page(request: Request):
    return templates.TemplateResponse("equipment_listing.html", {"request": request})