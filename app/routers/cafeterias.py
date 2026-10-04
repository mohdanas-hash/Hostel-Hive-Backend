from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Amenity, Cafeteria, College, FoodType, Location, Role
from ..schemas import CafeteriaIn, CafeteriaOut
from ..security import require_role
from .listings import resolve_amenities, with_ratings

router = APIRouter(prefix="/cafeterias", tags=["cafeterias"])
admin_only = Depends(require_role(Role.central_admin))


@router.get("", response_model=list[CafeteriaOut])
def list_cafeterias(
    college_id: int | None = None,
    city: str | None = None,
    location: Location | None = None,
    food_type: FoodType | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_hygiene: float | None = None,
    home_delivery: bool | None = None,
    amenity: list[str] | None = Query(None),
    sort: str = Query("price", pattern="^(price|distance|hygiene)$"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = select(Cafeteria).where(Cafeteria.is_active)
    if city:
        q = q.join(College, College.id == Cafeteria.college_id).where(College.city.ilike(city))
    if college_id:
        q = q.where(Cafeteria.college_id == college_id)
    if location:
        q = q.where(Cafeteria.location == location)
    if food_type:
        q = q.where(Cafeteria.food_type == food_type)
    if min_price is not None:
        q = q.where(Cafeteria.avg_meal_price >= min_price)
    if max_price is not None:
        q = q.where(Cafeteria.avg_meal_price <= max_price)
    if min_hygiene is not None:
        q = q.where(Cafeteria.hygiene_rating >= min_hygiene)
    if home_delivery is not None:
        q = q.where(Cafeteria.home_delivery == home_delivery)
    for name in amenity or []:
        q = q.where(Cafeteria.amenity_items.any(Amenity.name == name.strip().lower()))
    order = {"price": Cafeteria.avg_meal_price, "distance": Cafeteria.distance_from_college_km,
             "hygiene": Cafeteria.hygiene_rating.desc()}[sort]
    rows = db.scalars(q.order_by(order).limit(limit).offset(offset)).all()
    return with_ratings(db, rows, "cafeteria", CafeteriaOut)


@router.get("/{cafeteria_id}", response_model=CafeteriaOut)
def get_cafeteria(cafeteria_id: int, db: Session = Depends(get_db)):
    c = db.get(Cafeteria, cafeteria_id)
    if not c:
        raise HTTPException(404, "Cafeteria not found")
    return with_ratings(db, [c], "cafeteria", CafeteriaOut)[0]


@router.post("", response_model=CafeteriaOut, status_code=201, dependencies=[admin_only])
def create_cafeteria(data: CafeteriaIn, db: Session = Depends(get_db)):
    if not db.get(College, data.college_id):
        raise HTTPException(404, "College not found")
    c = Cafeteria(**data.model_dump(exclude={"amenities"}),
                  amenity_items=resolve_amenities(db, data.amenities, "cafeteria"))
    db.add(c)
    db.commit()
    return c


@router.put("/{cafeteria_id}", response_model=CafeteriaOut, dependencies=[admin_only])
def update_cafeteria(cafeteria_id: int, data: CafeteriaIn, db: Session = Depends(get_db)):
    c = db.get(Cafeteria, cafeteria_id)
    if not c:
        raise HTTPException(404, "Cafeteria not found")
    for k, v in data.model_dump(exclude={"amenities"}).items():
        setattr(c, k, v)
    c.amenity_items = resolve_amenities(db, data.amenities, "cafeteria")
    db.commit()
    return c


@router.delete("/{cafeteria_id}", status_code=204, dependencies=[admin_only])
def delete_cafeteria(cafeteria_id: int, db: Session = Depends(get_db)):
    c = db.get(Cafeteria, cafeteria_id)
    if not c:
        raise HTTPException(404, "Cafeteria not found")
    c.is_active = False
    db.commit()
