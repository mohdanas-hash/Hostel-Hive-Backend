from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Role, User
from .security import hash_password


def ensure_admin(db: Session) -> None:
    """Create the single central admin from ADMIN_EMAIL / ADMIN_PASSWORD if none exists."""
    if db.scalar(select(User).where(User.role == Role.central_admin)):
        return
    if not (settings.admin_email and settings.admin_password):
        return
    db.add(User(name=settings.admin_name, email=settings.admin_email, role=Role.central_admin,
                password_hash=hash_password(settings.admin_password)))
    db.commit()
