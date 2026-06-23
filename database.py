from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum

DATABASE_URL = "sqlite:///./agrinet.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UserRole(str, enum.Enum):
    farmer = "farmer"
    vet = "vet"
    consumer = "consumer"
    investor = "investor"


class VerificationStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # farmer | vet | consumer | investor
    is_phone_verified = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)  # admin approved
    verification_status = Column(String, default="pending")
    otp_code = Column(String, nullable=True)
    otp_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    documents = relationship("UserDocument", back_populates="user")
    produce = relationship("Produce", back_populates="farmer")


class UserDocument(Base):
    __tablename__ = "user_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    doc_type = Column(String, nullable=False)  # NIN, CAC, farm_photo, bank_details, vet_license
    file_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="documents")


class Produce(Base):
    __tablename__ = "produce"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)  # grains | vegetables | fruits | livestock | dairy
    price = Column(Integer, nullable=False)
    unit = Column(String, nullable=False)  # bag | crate | kg | litre
    quantity = Column(Integer, nullable=False)
    location = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    image_path = Column(String, nullable=True)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer = relationship("User", back_populates="produce")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)