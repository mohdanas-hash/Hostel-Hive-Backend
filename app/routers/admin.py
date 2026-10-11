"""Central-admin back office: dashboard stats, users, all payments, review moderation, deactivated listings."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (AdmissionApplication, AdmissionStatus, Cafeteria, College, DailyPost, Hostel, Location, Mess,
                      Payment, PaymentKind, PaymentStatus, Review, Role, User)
from ..schemas import (AdminPaymentOut, AdminReviewOut, AdminUserOut, CafeteriaOut, HostelOut, MessOut, Page)
from ..security import require_role
from .listings import with_ratings

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(Role.central_admin))])

KINDS = {"hostels": (Hostel, HostelOut, "hostel"), "messes": (Mess, MessOut, "mess"),
         "cafeterias": (Cafeteria, CafeteriaOut, "cafeteria")}
Kind = Literal["hostels", "messes", "cafeterias"]
TARGETS = {"hostel": Hostel, "mess": Mess, "cafeteria": Cafeteria}


def count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def page_of(db: Session, q, limit: int, offset: int):
    total = db.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0
    return total, q.limit(limit).offset(offset)


# ---------------- stats ----------------
@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Everything the dashboard overview needs in one call."""
    beds_total, beds_free = db.execute(
        select(func.coalesce(func.sum(Hostel.total_beds), 0), func.coalesce(func.sum(Hostel.available_beds), 0))
        .where(Hostel.is_active)).one()
    paid = Payment.status == PaymentStatus.paid
    revenue = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(paid)) or 0
    by_kind = dict(db.execute(select(Payment.kind, func.coalesce(func.sum(Payment.amount), 0)).where(paid)
                              .group_by(Payment.kind)).all())
    pay_status = dict(db.execute(select(Payment.status, func.count()).group_by(Payment.status)).all())
    adm_status = dict(db.execute(select(AdmissionApplication.status, func.count())
                                 .group_by(AdmissionApplication.status)).all())
    return {
        "counts": {
            "colleges": count(db, College),
            "hostels": count(db, Hostel, Hostel.is_active), "hostels_inactive": count(db, Hostel, ~Hostel.is_active),
            "messes": count(db, Mess, Mess.is_active), "messes_inactive": count(db, Mess, ~Mess.is_active),
            "cafeterias": count(db, Cafeteria, Cafeteria.is_active),
            "cafeterias_inactive": count(db, Cafeteria, ~Cafeteria.is_active),
            "users": count(db, User, User.role != Role.central_admin),
            "reviews": count(db, Review),
            "posts_today": count(db, DailyPost, DailyPost.post_date == func.current_date()),
        },
        "beds": {"total": int(beds_total), "available": int(beds_free)},
        "admissions": {s.value: adm_status.get(s, 0) for s in AdmissionStatus},
        "payments": {
            "revenue": float(revenue),
            "revenue_hostel_rent": float(by_kind.get(PaymentKind.hostel_rent, 0)),
            "revenue_mess_fee": float(by_kind.get(PaymentKind.mess_fee, 0)),
            "by_status": {s.value: pay_status.get(s, 0) for s in PaymentStatus},
        },
        "locations": {
            loc.value: {"hostels": count(db, Hostel, Hostel.is_active, Hostel.location == loc),
                        "messes": count(db, Mess, Mess.is_active, Mess.location == loc),
                        "cafeterias": count(db, Cafeteria, Cafeteria.is_active, Cafeteria.location == loc)}
            for loc in Location},
        "monthly_revenue": monthly_revenue(db),
    }


def monthly_revenue(db: Session) -> list[dict]:
    """Paid revenue per calendar month (last 12 months that have payments). Grouped in Python: portable SQLite/PG."""
    rows = db.execute(select(Payment.paid_at, Payment.amount).where(
        Payment.status == PaymentStatus.paid, Payment.paid_at.is_not(None))).all()
    out: dict[str, float] = {}
    for paid_at, amount in rows:
        key = paid_at.strftime("%Y-%m")
        out[key] = out.get(key, 0.0) + amount
    return [{"month": k, "amount": round(v, 2)} for k, v in sorted(out.items())[-12:]]


# ---------------- users ----------------
@router.get("/users", response_model=Page[AdminUserOut])
def users(q: str | None = None, role: Role | None = None, limit: int = Query(20, le=200), offset: int = 0,
          db: Session = Depends(get_db)):
    query = select(User).order_by(User.created_at.desc(), User.id.desc())
    if role:
        query = query.where(User.role == role)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(User.name.ilike(like), User.email.ilike(like)))
    total, query = page_of(db, query, limit, offset)
    rows = db.scalars(query).all()
    ids = [u.id for u in rows]

    def counts(model):
        return dict(db.execute(select(model.user_id, func.count()).where(model.user_id.in_(ids))
                               .group_by(model.user_id)).all()) if ids else {}

    adm, pay, rev = counts(AdmissionApplication), counts(Payment), counts(Review)
    items = []
    for u in rows:
        o = AdminUserOut.model_validate(u)
        o.admissions, o.payments, o.reviews = adm.get(u.id, 0), pay.get(u.id, 0), rev.get(u.id, 0)
        items.append(o)
    return Page(items=items, total=total)


# ---------------- payments ----------------
@router.get("/payments")
def payments(status: PaymentStatus | None = None, kind: PaymentKind | None = None, user_id: int | None = None,
             q: str | None = None, limit: int = Query(20, le=200), offset: int = 0, db: Session = Depends(get_db)):
    """Every payment, newest first. `total_amount` is the sum of *paid* payments matching the filters."""
    query = select(Payment).order_by(Payment.created_at.desc(), Payment.id.desc())
    if status:
        query = query.where(Payment.status == status)
    if kind:
        query = query.where(Payment.kind == kind)
    if user_id:
        query = query.where(Payment.user_id == user_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.join(User, User.id == Payment.user_id).where(
            or_(User.name.ilike(like), User.email.ilike(like), Payment.provider_order_id.ilike(like)))
    total, paged = page_of(db, query, limit, offset)
    paid = query.where(Payment.status == PaymentStatus.paid).order_by(None).with_only_columns(Payment.amount).subquery()
    total_amount = db.scalar(select(func.coalesce(func.sum(paid.c.amount), 0))) or 0
    rows = db.scalars(paged).all()
    users_ = {u.id: u for u in db.scalars(select(User).where(User.id.in_({p.user_id for p in rows}))).all()} if rows else {}
    hostels = {h.id: h.name for h in db.scalars(select(Hostel).where(Hostel.id.in_({p.hostel_id for p in rows if p.hostel_id}))).all()} if rows else {}
    messes = {m.id: m.name for m in db.scalars(select(Mess).where(Mess.id.in_({p.mess_id for p in rows if p.mess_id}))).all()} if rows else {}
    items = []
    for p in rows:
        o = AdminPaymentOut.model_validate(p)
        u = users_.get(p.user_id)
        o.user_name, o.user_email = (u.name, u.email) if u else (None, None)
        o.hostel_name, o.mess_name = hostels.get(p.hostel_id), messes.get(p.mess_id)
        items.append(o)
    return {"items": items, "total": total, "total_amount": float(total_amount)}


# ---------------- reviews ----------------
@router.get("/reviews", response_model=Page[AdminReviewOut])
def reviews(target_type: Literal["hostel", "mess", "cafeteria"] | None = None, target_id: int | None = None,
            rating: int | None = Query(None, ge=1, le=5), limit: int = Query(20, le=200), offset: int = 0,
            db: Session = Depends(get_db)):
    query = select(Review).order_by(Review.created_at.desc(), Review.id.desc())
    if target_type:
        query = query.where(Review.target_type == target_type)
    if target_id:
        query = query.where(Review.target_id == target_id)
    if rating:
        query = query.where(Review.rating == rating)
    total, query = page_of(db, query, limit, offset)
    rows = db.scalars(query).all()
    users_ = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in rows}))).all()} if rows else {}
    names: dict[tuple[str, int], str] = {}
    for t, model in TARGETS.items():
        ids = {r.target_id for r in rows if r.target_type == t}
        if ids:
            names.update({(t, i.id): i.name for i in db.scalars(select(model).where(model.id.in_(ids))).all()})
    items = []
    for r in rows:
        o = AdminReviewOut.model_validate(r)
        o.user_name, o.target_name = users_.get(r.user_id), names.get((r.target_type, r.target_id))
        items.append(o)
    return Page(items=items, total=total)


@router.delete("/reviews/{review_id}", status_code=204)
def delete_review(review_id: int, db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(404, "Review not found")
    db.delete(r)
    db.commit()


# ---------------- listings incl. deactivated ----------------
@router.get("/listings/{kind}")
def listings(kind: Kind, state: Literal["active", "inactive", "all"] = "all", q: str | None = None,
             college_id: int | None = None, location: Location | None = None,
             limit: int = Query(20, le=200), offset: int = 0, db: Session = Depends(get_db)):
    """Hostels / messes / cafeterias with a total count, searchable, and optionally only the deactivated ones."""
    model, schema, target = KINDS[kind]
    query = select(model).order_by(model.id.desc())
    if state != "all":
        query = query.where(model.is_active if state == "active" else ~model.is_active)
    if q:
        query = query.where(model.name.ilike(f"%{q.strip()}%"))
    if college_id:
        query = query.where(model.college_id == college_id)
    if location:
        query = query.where(model.location == location)
    total, query = page_of(db, query, limit, offset)
    return {"items": with_ratings(db, db.scalars(query).all(), target, schema), "total": total}


@router.post("/listings/{kind}/{item_id}/restore")
def restore_listing(kind: Kind, item_id: int, db: Session = Depends(get_db)):
    model, schema, target = KINDS[kind]
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(404, "Listing not found")
    item.is_active = True
    db.commit()
    return with_ratings(db, [item], target, schema)[0]
