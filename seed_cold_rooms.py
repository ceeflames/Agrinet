"""
Run once to seed cold rooms:
python3 seed_cold_rooms.py
"""
from database import SessionLocal, ColdRoom, init_db
from datetime import datetime

init_db()
db = SessionLocal()

cold_rooms = [
    {"name": "Lagos Mainland Cold Hub", "city": "Lagos", "state": "Lagos", "temperature": "2–4°C", "rate_per_day": 3500, "total_slots": 20, "available_slots": 12, "address": "10 Industrial Avenue, Ikeja, Lagos"},
    {"name": "Kano Produce Cold Store", "city": "Kano", "state": "Kano", "temperature": "0–2°C", "rate_per_day": 3000, "total_slots": 15, "available_slots": 5, "address": "Dawanau Market Road, Kano"},
    {"name": "Abuja Fresh Cold Store", "city": "Abuja", "state": "FCT Abuja", "temperature": "1–3°C", "rate_per_day": 4000, "total_slots": 25, "available_slots": 8, "address": "Wuse Zone 5, Abuja"},
    {"name": "Port Harcourt Cold Hub", "city": "Port Harcourt", "state": "Rivers", "temperature": "2–4°C", "rate_per_day": 3500, "total_slots": 18, "available_slots": 10, "address": "Trans-Amadi Industrial Layout, Port Harcourt"},
    {"name": "Ibadan Agricultural Cold Store", "city": "Ibadan", "state": "Oyo", "temperature": "1–3°C", "rate_per_day": 2800, "total_slots": 20, "available_slots": 15, "address": "Challenge Area, Ibadan"},
    {"name": "Kaduna Cold Storage Facility", "city": "Kaduna", "state": "Kaduna", "temperature": "2–4°C", "rate_per_day": 2500, "total_slots": 12, "available_slots": 7, "address": "Kakuri Industrial Estate, Kaduna"},
    {"name": "Enugu Fresh Produce Store", "city": "Enugu", "state": "Enugu", "temperature": "0–2°C", "rate_per_day": 2800, "total_slots": 10, "available_slots": 6, "address": "Independence Layout, Enugu"},
    {"name": "Benin City Cold Hub", "city": "Benin City", "state": "Edo", "temperature": "2–4°C", "rate_per_day": 3000, "total_slots": 15, "available_slots": 9, "address": "Sapele Road, Benin City"},
]

for cr in cold_rooms:
    existing = db.query(ColdRoom).filter(ColdRoom.name == cr["name"]).first()
    if not existing:
        cold_room = ColdRoom(**cr, created_at=datetime.utcnow())
        db.add(cold_room)
        print(f"Added: {cr['name']}")
    else:
        print(f"Already exists: {cr['name']}")

db.commit()
print("Done!")
db.close()