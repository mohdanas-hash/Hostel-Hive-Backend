"""Sample data (run AFTER `npm run db:migrate`): python seed.py
Needs ADMIN_EMAIL / ADMIN_PASSWORD in .env — the single admin is created from them."""
from sqlalchemy import select

from app.bootstrap import ensure_admin
from app.database import SessionLocal
from app.models import (Amenity, Cafeteria, College, DailyPost, FoodType, Gender, Hostel, Location, Mess, PostKind,
                        Role, User)

db = SessionLocal()
ensure_admin(db)
admin = db.scalar(select(User).where(User.role == Role.central_admin))
if not admin:
    raise SystemExit("Set ADMIN_EMAIL and ADMIN_PASSWORD in .env first")
if db.query(College).count():
    raise SystemExit("Already seeded")

central = College(name="Central University", city="Bhopal", is_central=True)
a = College(name="ABC Engineering College", city="Bhopal")
b = College(name="XYZ Institute of Technology", city="Bhopal")
db.add_all([central, a, b]); db.flush()

admin.college_id = central.id

catalog = {
    "hostel": ["wifi", "ac", "laundry", "gym", "power_backup", "cctv", "geyser", "parking", "study_room"],
    "mess": ["ro_water", "tiffin", "buffet", "jain_food", "home_style"],
    "cafeteria": ["wifi", "ac", "late_night", "ro_water", "outdoor_seating", "card_payment"],
}
am = {(c, n): Amenity(name=n, category=c) for c, names in catalog.items() for n in names}
db.add_all(am.values()); db.flush()
H = lambda *n: [am[("hostel", x)] for x in n]   # hostel amenities
M = lambda *n: [am[("mess", x)] for x in n]
C = lambda *n: [am[("cafeteria", x)] for x in n]

on, off = Location.on_campus, Location.off_campus
hostels = [
    Hostel(college_id=a.id, name="ABC Boys Hostel", location=on, gender=Gender.boys, monthly_rent=4500,
           total_beds=200, available_beds=20, amenity_items=H("wifi", "laundry", "gym"), wifi_mbps=100, cctv=True),
    Hostel(college_id=a.id, name="Sunrise PG", location=off, gender=Gender.boys, monthly_rent=6500,
           distance_from_college_km=1.2, total_beds=40, available_beds=6, has_ac=True, attached_bathroom=True,
           amenity_items=H("wifi", "ac", "power_backup"), wifi_mbps=200, power_backup=True, cctv=True),
    Hostel(college_id=a.id, name="Budget Stay", location=off, gender=Gender.boys, monthly_rent=3800,
           distance_from_college_km=2.5, total_beds=60, available_beds=15, amenity_items=H("wifi"), wifi_mbps=50),
    Hostel(college_id=b.id, name="XYZ Hostel Block A", location=on, gender=Gender.co_ed, monthly_rent=5200,
           total_beds=150, available_beds=10, amenity_items=H("wifi", "laundry"), wifi_mbps=80, includes_mess=True),
    Hostel(college_id=b.id, name="Green Nest", location=off, gender=Gender.girls, monthly_rent=7000,
           distance_from_college_km=0.8, total_beds=30, available_beds=4, has_ac=True,
           amenity_items=H("wifi", "ac", "laundry"), wifi_mbps=150, cctv=True),
]
messes = [
    Mess(college_id=a.id, name="ABC Central Mess", location=on, monthly_price=3000, hygiene_rating=4.0,
         food_type=FoodType.both, amenity_items=M("ro_water"), seating_capacity=300),
    Mess(college_id=a.id, name="Annapurna Tiffin", location=off, monthly_price=2600, hygiene_rating=3.6,
         distance_from_college_km=0.6, food_type=FoodType.veg, amenity_items=M("tiffin")),
    Mess(college_id=b.id, name="XYZ Dining Hall", location=on, monthly_price=3400, hygiene_rating=4.3,
         food_type=FoodType.both, amenity_items=M("ro_water", "buffet"), seating_capacity=400),
    Mess(college_id=b.id, name="Spice Garden Mess", location=off, monthly_price=3200, hygiene_rating=4.1,
         distance_from_college_km=1.0, food_type=FoodType.non_veg, amenity_items=M("ro_water", "tiffin")),
]
cafes = [
    Cafeteria(college_id=a.id, name="ABC Canteen", location=on, avg_meal_price=70, min_item_price=10,
              opens_at="08:00", closes_at="20:00", food_type=FoodType.veg, cuisine="Snacks, Thali",
              hygiene_rating=3.9, seating_capacity=120, amenity_items=C("ro_water")),
    Cafeteria(college_id=a.id, name="Chai Tapri", location=off, avg_meal_price=50, min_item_price=10,
              opens_at="07:00", closes_at="23:30", distance_from_college_km=0.2, cuisine="Chai, Maggi",
              hygiene_rating=3.4, home_delivery=True, amenity_items=C("late_night")),
    Cafeteria(college_id=b.id, name="XYZ Food Court", location=on, avg_meal_price=130, min_item_price=20,
              opens_at="09:00", closes_at="21:00", cuisine="Multi-cuisine", hygiene_rating=4.4,
              seating_capacity=250, amenity_items=C("wifi", "ac", "card_payment")),
    Cafeteria(college_id=b.id, name="Brew & Bites", location=off, avg_meal_price=160, min_item_price=40,
              opens_at="10:00", closes_at="23:00", distance_from_college_km=0.7, cuisine="Cafe, Fast food",
              hygiene_rating=4.2, home_delivery=True, amenity_items=C("wifi", "ac", "outdoor_seating")),
]
db.add_all(hostels + messes + cafes); db.flush()
db.add(DailyPost(author_id=admin.id, college_id=a.id, kind=PostKind.mess_menu, mess_id=messes[0].id,
                 title="Today's menu", body="Lunch: Dal, Rice, Paneer. Dinner: Roti, Mix Veg."))
db.commit()
print("Seeded.")
