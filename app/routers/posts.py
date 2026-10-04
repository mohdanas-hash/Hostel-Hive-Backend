"""Daily feed. The central college posts every day about other colleges' mess/hostel."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Cafeteria, College, DailyPost, Hostel, Mess, PostKind, Role, User
from ..schemas import PostIn, PostOut
from ..security import require_role

router = APIRouter(prefix="/posts", tags=["daily posts"])


@router.get("", response_model=list[PostOut])
def feed(
    college_id: int | None = None,
    kind: PostKind | None = None,
    on: date | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = select(DailyPost)
    if college_id:
        q = q.where(DailyPost.college_id == college_id)
    if kind:
        q = q.where(DailyPost.kind == kind)
    if on:
        q = q.where(DailyPost.post_date == on)
    q = q.order_by(DailyPost.post_date.desc(), DailyPost.id.desc()).limit(min(limit, 200)).offset(offset)
    return db.scalars(q).all()


@router.get("/today", response_model=list[PostOut])
def today(db: Session = Depends(get_db)):
    return db.scalars(select(DailyPost).where(DailyPost.post_date == date.today())
                      .order_by(DailyPost.id.desc())).all()


@router.post("", response_model=PostOut, status_code=201)
def create_post(data: PostIn, db: Session = Depends(get_db),
                user: User = Depends(require_role(Role.central_admin))):
    if not db.get(College, data.college_id):
        raise HTTPException(404, "College not found")
    if data.mess_id and not db.get(Mess, data.mess_id):
        raise HTTPException(404, "Mess not found")
    if data.hostel_id and not db.get(Hostel, data.hostel_id):
        raise HTTPException(404, "Hostel not found")
    if data.cafeteria_id and not db.get(Cafeteria, data.cafeteria_id):
        raise HTTPException(404, "Cafeteria not found")
    payload = data.model_dump()
    payload["post_date"] = payload["post_date"] or date.today()
    post = DailyPost(author_id=user.id, **payload)
    db.add(post)
    db.commit()
    return post


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db),
                _: User = Depends(require_role(Role.central_admin))):
    post = db.get(DailyPost, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    db.delete(post)
    db.commit()
