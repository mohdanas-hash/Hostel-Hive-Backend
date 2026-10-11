from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Cafeteria, College, DailyPost, Hostel, Mess, Role, User
from ..schemas import CollegeIn, CollegeOut
from ..security import require_role

router = APIRouter(prefix="/colleges", tags=["colleges"])


@router.get("", response_model=list[CollegeOut])
def list_colleges(city: str | None = None, db: Session = Depends(get_db)):
    q = select(College).order_by(College.name)
    if city:
        q = q.where(College.city.ilike(city))
    return db.scalars(q).all()


@router.get("/{college_id}", response_model=CollegeOut)
def get_college(college_id: int, db: Session = Depends(get_db)):
    college = db.get(College, college_id)
    if not college:
        raise HTTPException(404, "College not found")
    return college


@router.post("", response_model=CollegeOut, status_code=201,
             dependencies=[Depends(require_role(Role.central_admin))])
def create_college(data: CollegeIn, db: Session = Depends(get_db)):
    college = College(**data.model_dump())
    db.add(college)
    db.commit()
    return college


@router.put("/{college_id}", response_model=CollegeOut, dependencies=[Depends(require_role(Role.central_admin))])
def update_college(college_id: int, data: CollegeIn, db: Session = Depends(get_db)):
    college = db.get(College, college_id)
    if not college:
        raise HTTPException(404, "College not found")
    clash = db.scalar(select(College.id).where(College.name == data.name, College.id != college_id))
    if clash:
        raise HTTPException(409, "A college with this name already exists")
    for k, v in data.model_dump().items():
        setattr(college, k, v)
    db.commit()
    return college


@router.delete("/{college_id}", status_code=204, dependencies=[Depends(require_role(Role.central_admin))])
def delete_college(college_id: int, db: Session = Depends(get_db)):
    """Only allowed while nothing references the college (listings incl. deactivated, posts, users)."""
    college = db.get(College, college_id)
    if not college:
        raise HTTPException(404, "College not found")
    used = {name: db.scalar(select(func.count()).select_from(model).where(model.college_id == college_id))
            for name, model in (("hostels", Hostel), ("messes", Mess), ("cafeterias", Cafeteria),
                                ("posts", DailyPost), ("users", User))}
    used = {k: v for k, v in used.items() if v}
    if used:
        raise HTTPException(409, "College is still in use: " + ", ".join(f"{v} {k}" for k, v in used.items()))
    db.delete(college)
    db.commit()
