from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Amenity, Role
from ..schemas import AmenityIn, AmenityOut
from ..security import require_role

router = APIRouter(prefix="/amenities", tags=["amenities"])
admin_only = Depends(require_role(Role.central_admin))


@router.get("", response_model=list[AmenityOut])
def list_amenities(category: str | None = Query(None, pattern="^(hostel|mess|cafeteria)$"), db: Session = Depends(get_db)):
    q = select(Amenity).order_by(Amenity.category, Amenity.name)
    if category:
        q = q.where(Amenity.category == category)
    return db.scalars(q).all()


@router.post("", response_model=AmenityOut, status_code=201, dependencies=[admin_only])
def create_amenity(data: AmenityIn, db: Session = Depends(get_db)):
    name = data.name.strip().lower()
    if db.scalar(select(Amenity).where(Amenity.name == name)):
        raise HTTPException(409, "Amenity already exists")
    a = Amenity(name=name, category=data.category)
    db.add(a)
    db.commit()
    return a


@router.delete("/{amenity_id}", status_code=204, dependencies=[admin_only])
def delete_amenity(amenity_id: int, db: Session = Depends(get_db)):
    a = db.get(Amenity, amenity_id)
    if not a:
        raise HTTPException(404, "Amenity not found")
    db.delete(a)  # links cascade
    db.commit()
