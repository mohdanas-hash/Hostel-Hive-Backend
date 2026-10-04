from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AdmissionApplication, AdmissionStatus, Hostel, Mess, Payment, PaymentKind, PaymentStatus, User
from ..payments import get_gateway
from ..schemas import PaymentConfirmIn, PaymentIn, PaymentOut
from ..security import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", response_model=PaymentOut, status_code=201)
def create_payment(data: PaymentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Creates a payment order. Amount is always computed server-side from the listing price."""
    application_id = None  # set for hostel rent (admission must be submitted first)
    if data.kind == PaymentKind.hostel_rent:
        h = db.get(Hostel, data.hostel_id) if data.hostel_id else None
        if not h or not h.is_active:
            raise HTTPException(404, "Hostel not found")
        application = db.scalar(select(AdmissionApplication).where(
            AdmissionApplication.user_id == user.id, AdmissionApplication.hostel_id == h.id))
        if not application or application.status not in (AdmissionStatus.submitted, AdmissionStatus.approved):
            raise HTTPException(403, {
                "message": "Complete hostel admission (all documents submitted) before paying rent",
                "application_id": application.id if application else None,
                "missing": [d.value for d in application.missing_documents] if application else None})
        application_id = application.id
        amount = h.monthly_rent * data.months
        if data.include_deposit:
            amount += h.security_deposit
    else:
        m = db.get(Mess, data.mess_id) if data.mess_id else None
        if not m or not m.is_active:
            raise HTTPException(404, "Mess not found")
        if data.include_deposit:
            raise HTTPException(422, "include_deposit applies to hostel rent only")
        amount = m.monthly_price * data.months

    gw = get_gateway()
    payment = Payment(user_id=user.id, kind=data.kind, hostel_id=data.hostel_id, mess_id=data.mess_id,
                      application_id=application_id,
                      months=data.months, include_deposit=data.include_deposit, amount=amount, provider=gw.name)
    db.add(payment)
    db.flush()
    payment.provider_order_id = gw.create_order(amount, payment.currency, f"pay_{payment.id}")
    db.commit()
    return payment


@router.post("/{payment_id}/confirm", response_model=PaymentOut)
def confirm_payment(payment_id: int, data: PaymentConfirmIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Mock confirmation. With a real gateway, verify the signature / use a webhook instead."""
    p = db.get(Payment, payment_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Payment not found")
    if p.status != PaymentStatus.created:
        raise HTTPException(409, f"Payment already {p.status.value}")
    if data.success:
        p.status = PaymentStatus.paid
        p.provider_payment_id = data.provider_payment_id
        p.paid_at = datetime.now(timezone.utc)
        if p.hostel_id:
            # A bed is taken only on the student's first paid rent for this hostel, not on renewals.
            earlier = db.scalar(select(Payment.id).where(
                Payment.user_id == user.id, Payment.hostel_id == p.hostel_id,
                Payment.status == PaymentStatus.paid, Payment.id != p.id))
            h = db.get(Hostel, p.hostel_id)
            if earlier is None and h.available_beds > 0:
                h.available_beds -= 1
    else:
        p.status = PaymentStatus.failed
    db.commit()
    return p


@router.get("", response_model=list[PaymentOut])
def my_payments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Payment).where(Payment.user_id == user.id)
                      .order_by(Payment.created_at.desc())).all()
