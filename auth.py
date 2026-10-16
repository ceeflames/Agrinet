from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os
import secrets
import httpx
import string

SECRET_KEY = os.getenv("SECRET_KEY", "agrinet-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_otp() -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def normalize_phone(phone: str) -> str:
    """Convert Nigerian numbers like 0801... to E.164 (+234801...)."""
    p = ''.join(ch for ch in phone.strip() if ch.isdigit() or ch == '+')
    if p.startswith('+'):
        return p
    if p.startswith('234'):
        return '+' + p
    if p.startswith('0') and len(p) == 11:
        return '+234' + p[1:]
    if len(p) == 10:
        return '+234' + p
    return '+' + p


def send_otp_sms(phone: str, otp: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    sender = os.getenv("TWILIO_SENDER_ID") or os.getenv("TWILIO_PHONE_NUMBER")
    service = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
    to = normalize_phone(phone)
    body = f"Your AgriNet verification code is {otp}. It expires in 10 minutes. Do not share it."

    if not (sid and token and (sender or service)):
        if os.getenv("APP_ENV") == "production":
            print("[SMS ERROR] Twilio is not configured")
            return False
        print(f"[DEV MODE - Twilio not configured] OTP for {to}: {otp}")
        return True

    data = {"To": to, "Body": body}
    if service:
        data["MessagingServiceSid"] = service
    else:
        data["From"] = sender
    try:
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data=data, auth=(sid, token), timeout=15,
        )
        if r.status_code in (200, 201):
            return True
        print(f"[SMS ERROR] {r.status_code}: {r.text[:300]}")
        return False
    except Exception as e:
        print(f"[SMS ERROR] {e}")
        return False