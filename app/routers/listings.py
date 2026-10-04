"""Hostels & messes: browse/filter (public), manage (central admin)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Amenity, Cafeteria, College, FoodType, Gender, Hostel, Location, Mess, Review, Role, User
from ..schemas import HostelIn, HostelOut, MessIn, MessOut, ReviewIn, ReviewOut
from ..security import get_current_user, require_role

router = APIRouter(tags=["listings"])
admin_only = Depends(require_role(Role.central_admin))


def ratings_for(db: Session, target_type: str, ids: list[int]) -> dict[int, float]:
    if not ids:
        return {}
    rows = db.execute(
        select(Review.target_id, func.avg(Review.rating))
        .where(Review.target_type == target_type, Review.target_id.in_(ids))
        .group_by(Review.target_id)
    ).all()
    return {tid: round(float(avg), 2) for tid, avg in rows}


def resolve_amenities(db: Session, names: list[str], category: str) -> list[Amenity]:
    names = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    if not names:
        return []
    found = db.scalars(select(Amenity).where(Amenity.name.in_(names), Amenity.category == category)).all()
    missing = set(names) - {a.name for a in found}
    if missing:
        raise HTTPException(422, f"Unknown {category} amenities: {sorted(missing)}. Create them via POST /amenities")
    return list(found)


def with_ratings(db, items, target_type, schema):
    ratings = ratings_for(db, target_type, [i.id for i in items])
    out = []
    for i in items:
        o = schema.model_validate(i)
        o.avg_rating = ratings.get(i.id)
        out.append(o)
    return out


# ---------------- hostels ----------------
@router.get("/hostels", response_model=list[HostelOut])
def list_hostels(
    college_id: int | None = None,
    city: str | None = None,
    location: Location | None = None,
    gender: Gender | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    has_ac: bool | None = None,
    includes_mess: bool | None = None,
    amenity: list[str] | None = Query(None, description="repeat to require several: ?amenity=wifi&amenity=laundry"),
    sort: str = Query("price", pattern="^(price|distance)$"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = select(Hostel).where(Hostel.is_active)
    if city:
        q = q.join(College, College.id == Hostel.college_id).where(College.city.ilike(city))
    if college_id:
        q = q.where(Hostel.college_id == college_id)
    if location:
        q = q.where(Hostel.location == location)
    if gender:
        q = q.where(Hostel.gender == gender)
    if min_price is not None:
        q = q.where(Hostel.monthly_rent >= min_price)
    if max_price is not None:
        q = q.where(Hostel.monthly_rent <= max_price)
    if has_ac is not None:
        q = q.where(Hostel.has_ac == has_ac)
    if includes_mess is not None:
        q = q.where(Hostel.includes_mess == includes_mess)
    for name in amenity or []:
        q = q.where(Hostel.amenity_items.any(Amenity.name == name.strip().lower()))
    q = q.order_by(Hostel.monthly_rent if sort == "price" else Hostel.distance_from_college_km)
    return with_ratings(db, db.scalars(q.limit(limit).offset(offset)).all(), "hostel", HostelOut)


@router.get("/hostels/{hostel_id}", response_model=HostelOut)
def get_hostel(hostel_id: int, db: Session = Depends(get_db)):
    h = db.get(Hostel, hostel_id)
    if not h:
        raise HTTPException(404, "Hostel not found")
    return with_ratings(db, [h], "hostel", HostelOut)[0]


@router.post("/hostels", response_model=HostelOut, status_code=201, dependencies=[admin_only])
def create_hostel(data: HostelIn, db: Session = Depends(get_db)):
    if not db.get(College, data.college_id):
        raise HTTPException(404, "College not found")
    payload = data.model_dump(exclude={"amenities"})
    h = Hostel(**payload, amenity_items=resolve_amenities(db, data.amenities, "hostel"))
    db.add(h)
    db.commit()
    return h


@router.put("/hostels/{hostel_id}", response_model=HostelOut, dependencies=[admin_only])
def update_hostel(hostel_id: int, data: HostelIn, db: Session = Depends(get_db)):
    h = db.get(Hostel, hostel_id)
    if not h:
        raise HTTPException(404, "Hostel not found")
    for k, v in data.model_dump(exclude={"amenities"}).items():
        setattr(h, k, v)
    h.amenity_items = resolve_amenities(db, data.amenities, "hostel")
    db.commit()
    return h


@router.delete("/hostels/{hostel_id}", status_code=204, dependencies=[admin_only])
def delete_hostel(hostel_id: int, db: Session = Depends(get_db)):
    h = db.get(Hostel, hostel_id)
    if not h:
        raise HTTPException(404, "Hostel not found")
    h.is_active = False
    db.commit()


# ---------------- messes ----------------
@router.get("/messes", response_model=list[MessOut])
def list_messes(
    college_id: int | None = None,
    city: str | None = None,
    location: Location | None = None,
    food_type: FoodType | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_hygiene: float | None = None,
    amenity: list[str] | None = Query(None),
    sort: str = Query("price", pattern="^(price|distance|hygiene)$"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = select(Mess).where(Mess.is_active)
    if city:
        q = q.join(College, College.id == Mess.college_id).where(College.city.ilike(city))
    if college_id:
        q = q.where(Mess.college_id == college_id)
    if location:
        q = q.where(Mess.location == location)
    if food_type:
        q = q.where(Mess.food_type == food_type)
    if min_price is not None:
        q = q.where(Mess.monthly_price >= min_price)
    if max_price is not None:
        q = q.where(Mess.monthly_price <= max_price)
    if min_hygiene is not None:
        q = q.where(Mess.hygiene_rating >= min_hygiene)
    for name in amenity or []:
        q = q.where(Mess.amenity_items.any(Amenity.name == name.strip().lower()))
    order = {"price": Mess.monthly_price, "distance": Mess.distance_from_college_km,
             "hygiene": Mess.hygiene_rating.desc()}[sort]
    return with_ratings(db, db.scalars(q.order_by(order).limit(limit).offset(offset)).all(), "mess", MessOut)


@router.get("/messes/{mess_id}", response_model=MessOut)
def get_mess(mess_id: int, db: Session = Depends(get_db)):
    m = db.get(Mess, mess_id)
    if not m:
        raise HTTPException(404, "Mess not found")
    return with_ratings(db, [m], "mess", MessOut)[0]


@router.post("/messes", response_model=MessOut, status_code=201, dependencies=[admin_only])
def create_mess(data: MessIn, db: Session = Depends(get_db)):
    if not db.get(College, data.college_id):
        raise HTTPException(404, "College not found")
    payload = data.model_dump(exclude={"amenities"})
    m = Mess(**payload, amenity_items=resolve_amenities(db, data.amenities, "mess"))
    db.add(m)
    db.commit()
    return m


@router.put("/messes/{mess_id}", response_model=MessOut, dependencies=[admin_only])
def update_mess(mess_id: int, data: MessIn, db: Session = Depends(get_db)):
    m = db.get(Mess, mess_id)
    if not m:
        raise HTTPException(404, "Mess not found")
    for k, v in data.model_dump(exclude={"amenities"}).items():
        setattr(m, k, v)
    m.amenity_items = resolve_amenities(db, data.amenities, "mess")
    db.commit()
    return m


@router.delete("/messes/{mess_id}", status_code=204, dependencies=[admin_only])
def delete_mess(mess_id: int, db: Session = Depends(get_db)):
    m = db.get(Mess, mess_id)
    if not m:
        raise HTTPException(404, "Mess not found")
    m.is_active = False
    db.commit()


# ---------------- reviews ----------------
@router.post("/reviews", response_model=ReviewOut, status_code=201)
def add_review(data: ReviewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    model = {"hostel": Hostel, "mess": Mess, "cafeteria": Cafeteria}[data.target_type]
    if not db.get(model, data.target_id):
        raise HTTPException(404, f"{data.target_type} not found")
    r = Review(user_id=user.id, **data.model_dump())
    db.add(r)
    db.commit()
    return r


@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(target_type: str = Query(pattern="^(hostel|mess|cafeteria)$"), target_id: int = 0,
                 db: Session = Depends(get_db)):
    q = select(Review).where(Review.target_type == target_type, Review.target_id == target_id)
    return db.scalars(q.order_by(Review.created_at.desc())).all()
