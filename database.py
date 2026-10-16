from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agrinet.db")
# Some providers give "postgres://", SQLAlchemy needs "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # farmer | vet | consumer | investor | admin
    is_phone_verified = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    verification_status = Column(String, default="pending")
    otp_code = Column(String, nullable=True)
    otp_expires = Column(DateTime, nullable=True)
    bio = Column(Text, nullable=True)
    farm_location = Column(String, nullable=True)
    farm_lat = Column(Float, nullable=True)
    farm_lng = Column(Float, nullable=True)
    # Wallet
    wallet_balance = Column(Float, default=0.0)
    wallet_pending = Column(Float, default=0.0)
    total_earned = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("UserDocument", back_populates="user")
    produce = relationship("Produce", back_populates="farmer")
    investments = relationship("Investment", foreign_keys="Investment.investor_id", back_populates="investor")
    vet_questions = relationship("VetQuestion", foreign_keys="VetQuestion.user_id", back_populates="user")
    consultations = relationship("Consultation", foreign_keys="Consultation.vet_id", back_populates="vet")
    withdrawals = relationship("Withdrawal", back_populates="user")


class UserDocument(Base):
    __tablename__ = "user_documents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    doc_type = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="documents")


class Produce(Base):
    __tablename__ = "produce"
    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    unit = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    location = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    image_path = Column(String, nullable=True)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    farmer = relationship("User", back_populates="produce")
    orders = relationship("Order", back_populates="produce")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"))
    farmer_id = Column(Integer, ForeignKey("users.id"))
    produce_id = Column(Integer, ForeignKey("produce.id"))
    quantity = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    farmer_amount = Column(Float, default=0.0)
    delivery_address = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending|confirmed|shipped|delivered|cancelled
    payment_status = Column(String, default="unpaid")  # unpaid|paid|refunded
    paystack_reference = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    buyer = relationship("User", foreign_keys=[buyer_id])
    farmer = relationship("User", foreign_keys=[farmer_id])
    produce = relationship("Produce", back_populates="orders")


class Investment(Base):
    __tablename__ = "investments"
    id = Column(Integer, primary_key=True, index=True)
    investor_id = Column(Integer, ForeignKey("users.id"))
    crop = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    expected_return = Column(Float, nullable=True)
    tenor = Column(String, nullable=False)
    status = Column(String, default="active")
    payment_status = Column(String, default="unpaid")
    paystack_reference = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    investor = relationship("User", foreign_keys=[investor_id], back_populates="investments")


class VetQuestion(Base):
    __tablename__ = "vet_questions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    vet_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)
    user = relationship("User", foreign_keys=[user_id], back_populates="vet_questions")
    vet = relationship("User", foreign_keys=[vet_id])


class Consultation(Base):
    __tablename__ = "consultations"
    id = Column(Integer, primary_key=True, index=True)
    vet_id = Column(Integer, ForeignKey("users.id"))
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    topic = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    fee = Column(Float, default=0.0)
    commission = Column(Float, default=0.0)
    status = Column(String, default="scheduled")
    payment_status = Column(String, default="unpaid")
    paystack_reference = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    vet = relationship("User", foreign_keys=[vet_id], back_populates="consultations")
    farmer = relationship("User", foreign_keys=[farmer_id])


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float, nullable=False)
    bank_name = Column(String, nullable=False)
    account_number = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending|approved|rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="withdrawals")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    reference = Column(String, unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)  # order|investment|consultation|withdrawal
    related_id = Column(Integer, nullable=True)
    status = Column(String, default="pending")  # pending|success|failed
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String, default="info")  # info | order | payment | vet | investment
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", foreign_keys=[user_id])


class ColdRoom(Base):
    __tablename__ = "cold_rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    temperature = Column(String, nullable=False)
    rate_per_day = Column(Float, nullable=False)
    total_slots = Column(Integer, nullable=False)
    available_slots = Column(Integer, nullable=False)
    address = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    bookings = relationship("ColdRoomBooking", back_populates="cold_room")


class ColdRoomBooking(Base):
    __tablename__ = "cold_room_bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    cold_room_id = Column(Integer, ForeignKey("cold_rooms.id"))
    produce_description = Column(String, nullable=False)
    quantity_tons = Column(Float, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    days = Column(Integer, nullable=False)
    total_cost = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    status = Column(String, default="pending")  # pending|confirmed|active|completed|cancelled
    payment_status = Column(String, default="unpaid")
    paystack_reference = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", foreign_keys=[user_id])
    cold_room = relationship("ColdRoom", back_populates="bookings")


class Equipment(Base):
    __tablename__ = "equipment"
    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=False)  # tractor|pump|sprayer|harvester|other
    listing_type = Column(String, nullable=False)  # sale|rent
    price = Column(Float, nullable=False)
    rent_period = Column(String, nullable=True)  # daily|weekly|monthly
    condition = Column(String, default="good")  # new|good|fair
    location = Column(String, nullable=False)
    state = Column(String, nullable=False)
    image_path = Column(String, nullable=True)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    vendor = relationship("User", foreign_keys=[vendor_id])


class Farmland(Base):
    __tablename__ = "farmland"
    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    size_hectares = Column(Float, nullable=False)
    soil_type = Column(String, nullable=True)
    water_source = Column(String, nullable=True)
    location = Column(String, nullable=False)
    state = Column(String, nullable=False)
    address = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    price_per_season = Column(Float, nullable=False)
    rent_period = Column(String, default="season")  # season|year|month
    image_path = Column(String, nullable=True)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    vendor = relationship("User", foreign_keys=[vendor_id])


class EquipmentBooking(Base):
    __tablename__ = "equipment_bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    equipment_id = Column(Integer, ForeignKey("equipment.id"))
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    total_cost = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    status = Column(String, default="pending")
    payment_status = Column(String, default="unpaid")
    paystack_reference = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", foreign_keys=[user_id])
    equipment = relationship("Equipment")


class FarmlandBooking(Base):
    __tablename__ = "farmland_bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    farmland_id = Column(Integer, ForeignKey("farmland.id"))
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    total_cost = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    status = Column(String, default="pending")
    payment_status = Column(String, default="unpaid")
    paystack_reference = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", foreign_keys=[user_id])
    farmland = relationship("Farmland")