"""
Run this once to create the admin account:
python3 create_admin.py
"""
from database import SessionLocal, User, init_db
from auth import get_password_hash

init_db()
db = SessionLocal()

# Change these credentials
ADMIN_EMAIL = "admin@agrinet.com"
ADMIN_PASSWORD = "Admin@1234"
ADMIN_NAME = "AgriNet Admin"
ADMIN_PHONE = "+2340000000000"

existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
if existing:
    print(f"Admin already exists: {existing.email}")
else:
    admin = User(
        full_name=ADMIN_NAME,
        email=ADMIN_EMAIL,
        phone=ADMIN_PHONE,
        password_hash=get_password_hash(ADMIN_PASSWORD),
        role="admin",
        created_at=__import__('datetime').datetime.utcnow(),
        is_phone_verified=True,
        is_verified=True,
        verification_status="verified"
    )
    db.add(admin)
    db.commit()
    print(f"Admin created successfully!")
    print(f"Email: {ADMIN_EMAIL}")
    print(f"Password: {ADMIN_PASSWORD}")

db.close()