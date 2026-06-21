# main.py
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse


app = FastAPI(title="AgriNet API", version="2.0")
# Mount the static folder
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# --- CONFIG ---
SECRET_KEY = "super-secret-key"  # 🔐 replace with env var in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


# --- AUTH SETUP ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

users_db = {}  # {username: {username, password_hash, role}}

class User(BaseModel):
    username: str
    role: str  # buyer | seller

class UserInDB(User):
    password_hash: str

class Token(BaseModel):
    access_token: str
    token_type: str

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username not in users_db:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication")
        user_dict = users_db[username]
        return User(username=user_dict["username"], role=user_dict["role"])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# --- AUTH ENDPOINTS ---
@app.post("/auth/register", response_model=User)
def register(username: str, password: str, role: str):
    if username in users_db:
        raise HTTPException(400, "User already exists")
    if role not in ["buyer", "seller"]:
        raise HTTPException(400, "Invalid role")
    users_db[username] = {
        "username": username,
        "password_hash": get_password_hash(password),
        "role": role,
    }
    return {"username": username, "role": role}

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


# --- MOCK DATA ---
listings = [
    {"id": 1, "title": "Maize (100kg bags)", "category": "grains", "price": 43000, "unit": "bag", "location": "Kaduna", "sellerVerified": True, "coldStorageEligible": True},
    {"id": 2, "title": "Tomatoes (25kg crates)", "category": "vegetables", "price": 12000, "unit": "crate", "location": "Kano", "sellerVerified": True, "coldStorageEligible": True},
]
feeds = [
    {"id": 301, "name": "Broiler Starter (25kg)", "species": "poultry", "price": 10500},
]
cold_rooms = [
    {"id": 201, "name": "Lagos Cold Hub", "city": "Lagos", "slotsFree": 12, "temp": "2–4°C", "ratePerDay": 3500},
]
equipment = [
    {"id": 101, "title": "2 Water Pump", "type": "equipment", "price": 95000, "location": "Ibadan"}
]
coldRooms = [
    {"id": 201, "name": "Lagos Mainland Cold Hub", "city": "Lagos", "slotsFree": 12, "temp": "2–4°C", "ratePerDay": 3500}
]
categories = [
    {"key": "grains", "label": "Grains"},
    {"key": "vegetables", "label": "Vegetables"}
]
cities = ["Lagos", "Abuja", "Kano", "Port Harcourt", "Kaduna"]
cart: List[dict] = []


# --- MODELS ---
class CartItem(BaseModel):
    id: int
    type: str  # listing | feed
    quantity: int = 1

class Investment(BaseModel):
    crop: str
    amount: int
    tenor: str

class Seller(BaseModel):
    farmName: str
    state: str
    category: str
    phone: str

class VetQuestion(BaseModel):
    question: str


# --- ROOT ROUTE (serves HTML homepage) ---
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, query: str = "", cat: str = None):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "listings": listings,
        "equipment": equipment,
        "coldRooms": coldRooms,
        "categories": categories,
        "cities": cities,
        "query": query,
        "cat": cat,
        "cart_count": 0,
        "year": 2025,
        "city": "Lagos",
        "forecast": [
            {"day": "Mon", "temp": 31, "desc": "Partly cloudy"},
            {"day": "Tue", "temp": 29, "desc": "Showers"},
            {"day": "Wed", "temp": 30, "desc": "Sunny"},
        ]
    })


# --- PROTECTED ENDPOINTS ---
@app.get("/listings")
def get_listings(query: Optional[str] = None, category: Optional[str] = None):
    results = listings
    if category:
        results = [l for l in results if l["category"] == category]
    if query:
        results = [l for l in results if query.lower() in l["title"].lower()]
    return results

@app.post("/cart/add")
def add_to_cart(item: CartItem, user: User = Depends(get_current_user)):
    if user.role != "buyer":
        raise HTTPException(403, "Only buyers can add to cart")
    match = None
    if item.type == "listing":
        match = next((l for l in listings if l["id"] == item.id), None)
    elif item.type == "feed":
        match = next((f for f in feeds if f["id"] == item.id), None)
    if not match:
        raise HTTPException(404, "Item not found")
    cart.append({"item": match, "quantity": item.quantity, "buyer": user.username})
    return {"message": f"Added {match['title']} to cart", "cartSize": len(cart)}

@app.get("/cart")
def view_cart(user: User = Depends(get_current_user)):
    if user.role != "buyer":
        raise HTTPException(403, "Only buyers can view cart")
    return [c for c in cart if c["buyer"] == user.username]

@app.post("/invest")
def pledge_investment(invest: Investment, user: User = Depends(get_current_user)):
    if user.role != "buyer":
        raise HTTPException(403, "Only buyers can invest")
    return {"message": f"Pledge received: ₦{invest.amount:,} into {invest.crop} with tenor {invest.tenor}"}

@app.post("/seller/register")
def register_seller(seller: Seller, user: User = Depends(get_current_user)):
    if user.role != "seller":
        raise HTTPException(403, "Only sellers can register farm")
    return {"message": f"Seller {user.username} registered farm: {seller.farmName} ({seller.state}). Pending KYC."}

@app.post("/vet/ask")
def ask_vet(q: VetQuestion, user: User = Depends(get_current_user)):
    return {"message": f"Vet question from {user.username}: {q.question}"}


# --- FRONTEND ROUTES ---
@app.get("/home", response_class=HTMLResponse)
def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request, "message": "Welcome to AgroBridge API"})

@app.get("/view-listings", response_class=HTMLResponse)
def view_listings(request: Request):
    return templates.TemplateResponse("listings.html", {"request": request, "listings": listings})

@app.get("/view-cart", response_class=HTMLResponse)
def view_cart_page(request: Request, user: User = Depends(get_current_user)):
    user_cart = [c for c in cart if c["buyer"] == user.username]
    return templates.TemplateResponse("cart.html", {"request": request, "cart": user_cart, "username": user.username})