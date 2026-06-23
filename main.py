from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List
import os
import shutil
import uuid

from database import get_db, init_db, User, UserDocument, Produce
from auth import (
    verify_password, get_password_hash, create_access_token,
    decode_token, generate_otp, send_otp_sms
)

# --- APP SETUP ---
app = FastAPI(title="AgriNet API", version="3.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

# Initialize database on startup
@app.on_event("startup")
def startup():
    init_db()


# --- HTTPS PROXY MIDDLEWARE ---
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
    listings = [
        {
            "id": p.id,
            "title": p.title,
            "category": p.category,
            "price": p.price,
            "unit": p.unit,
            "location": p.location,
            "image": p.image_path,
            "sellerVerified": True,
            "coldStorageEligible": p.category in ["vegetables", "fruits", "dairy"],
        }
        for p in produce
    ] or [
        {"id": 1, "title": "Maize (100kg bags)", "category": "grains", "price": 43000, "unit": "bag", "location": "Kaduna", "sellerVerified": True, "coldStorageEligible": True},
        {"id": 2, "title": "Tomatoes (25kg crates)", "category": "vegetables", "price": 12000, "unit": "crate", "location": "Kano", "sellerVerified": True, "coldStorageEligible": True},
    ]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "listings": listings,
        "equipment": [{"id": 101, "title": "2 Water Pump", "type": "equipment", "price": 95000, "location": "Ibadan"}],
        "coldRooms": [{"id": 201, "name": "Lagos Mainland Cold Hub", "city": "Lagos", "slotsFree": 12, "temp": "2–4°C", "ratePerDay": 3500}],
        "categories": [{"key": "grains", "label": "Grains"}, {"key": "vegetables", "label": "Vegetables"}],
        "cities": ["Lagos", "Abuja", "Kano", "Port Harcourt", "Kaduna"],
        "query": "",
        "cat": None,
        "cart_count": 0,
        "year": 2025,
        "city": "Lagos",
        "forecast": [
            {"day": "Mon", "temp": 31, "desc": "Partly cloudy"},
            {"day": "Tue", "temp": 29, "desc": "Showers"},
            {"day": "Wed", "temp": 30, "desc": "Sunny"},
        ]
    })


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/verify-otp", response_class=HTMLResponse)
def verify_otp_page(request: Request):
    return templates.TemplateResponse("verify_otp.html", {"request": request})


# --- AUTH ENDPOINTS ---
@app.post("/auth/register")
async def register(
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    # Farmer docs
    nin: UploadFile = File(None),
    cac: UploadFile = File(None),
    farm_photo: UploadFile = File(None),
    bank_details: UploadFile = File(None),
    # Vet docs
    vet_license: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Validate role
    valid_roles = ["farmer", "vet", "consumer", "investor"]
    if role not in valid_roles:
        raise HTTPException(400, "Invalid role")

    # Check existing user
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email already registered")
    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(400, "Phone already registered")

    # Create user
    otp = generate_otp()
    otp_expires = datetime.utcnow() + timedelta(minutes=10)

    user = User(
        full_name=full_name,
        email=email,
        phone=phone,
        password_hash=get_password_hash(password),
        role=role,
        otp_code=otp,
        otp_expires=otp_expires,
        verification_status="pending"
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Save documents based on role
    doc_map = {
        "nin": nin,
        "cac": cac,
        "farm_photo": farm_photo,
        "bank_details": bank_details,
        "vet_license": vet_license,
    }
    for doc_type, file in doc_map.items():
        if file and file.filename:
            path = save_upload(file, f"docs/{user.id}")
            doc = UserDocument(user_id=user.id, doc_type=doc_type, file_path=path)
            db.add(doc)
    db.commit()

    # Send OTP
    send_otp_sms(phone, otp)

    return JSONResponse({"message": "Registration successful. OTP sent to your phone.", "user_id": user.id})


@app.post("/auth/verify-otp")
def verify_otp(
    user_id: int = Form(...),
    otp: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.otp_code != otp:
        raise HTTPException(400, "Invalid OTP")
    if user.otp_expires < datetime.utcnow():
        raise HTTPException(400, "OTP expired")

    user.is_phone_verified = True
    user.otp_code = None
    user.otp_expires = None
    db.commit()

    token = create_access_token({"user_id": user.id, "role": user.role})
    return JSONResponse({"message": "Phone verified!", "token": token, "role": user.role})


@app.post("/auth/resend-otp")
def resend_otp(user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    otp = generate_otp()
    user.otp_code = otp
    user.otp_expires = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    send_otp_sms(user.phone, otp)
    return {"message": "OTP resent"}


@app.post("/auth/login")
def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(400, "Invalid email or password")
    if not user.is_phone_verified:
        raise HTTPException(400, "Please verify your phone number first")

    token = create_access_token({"user_id": user.id, "role": user.role})
    return JSONResponse({"token": token, "role": user.role, "name": user.full_name})


@app.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
        "verification_status": current_user.verification_status,
    }


# --- PRODUCE ENDPOINTS (Farmers only) ---
@app.post("/produce/add")
async def add_produce(
    title: str = Form(...),
    category: str = Form(...),
    price: int = Form(...),
    unit: str = Form(...),
    quantity: int = Form(...),
    location: str = Form(...),
    description: str = Form(None),
    image: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "farmer":
        raise HTTPException(403, "Only farmers can add produce")
    if not current_user.is_phone_verified:
        raise HTTPException(403, "Please verify your phone first")

    image_path = None
    if image and image.filename:
        image_path = save_upload(image, "produce")

    produce = Produce(
        farmer_id=current_user.id,
        title=title,
        category=category,
        price=price,
        unit=unit,
        quantity=quantity,
        location=location,
        description=description,
        image_path=image_path,
    )
    db.add(produce)
    db.commit()
    db.refresh(produce)
    return {"message": "Produce listed successfully!", "id": produce.id}


@app.get("/produce")
def get_produce(
    category: Optional[str] = None,
    query: Optional[str] = None,
    db: Session = Depends(get_db)
):
    results = db.query(Produce).filter(Produce.is_available == True)
    if category:
        results = results.filter(Produce.category == category)
    if query:
        results = results.filter(Produce.title.ilike(f"%{query}%"))
    return results.all()


@app.delete("/produce/{produce_id}")
def delete_produce(
    produce_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    produce = db.query(Produce).filter(Produce.id == produce_id).first()
    if not produce:
        raise HTTPException(404, "Produce not found")
    if produce.farmer_id != current_user.id:
        raise HTTPException(403, "Not your listing")
    produce.is_available = False
    db.commit()
    return {"message": "Listing removed"}