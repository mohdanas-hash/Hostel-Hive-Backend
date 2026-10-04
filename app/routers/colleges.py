from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import College, Role
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
