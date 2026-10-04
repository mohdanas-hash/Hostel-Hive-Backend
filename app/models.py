import enum
from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String,
                        Table, Text, UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def enum_col(e: type[enum.Enum]) -> Enum:
    # Stored as plain varchar (no native PG enum) so Drizzle migrations stay simple.
    return Enum(e, native_enum=False, length=30, create_constraint=False)


def utcnow():
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    visitor = "visitor"          # browses / compares
    student = "student"          # can pay
    central_admin = "central_admin"  # central college: posts daily updates for all colleges


class Location(str, enum.Enum):
    on_campus = "on_campus"      # inside the college
    off_campus = "off_campus"    # outside the college (main price-comparison focus)


class Gender(str, enum.Enum):
    boys = "boys"
    girls = "girls"
    co_ed = "co_ed"


class FoodType(str, enum.Enum):
    veg = "veg"
    non_veg = "non_veg"
    both = "both"


class PostKind(str, enum.Enum):
    mess_menu = "mess_menu"
    cafeteria_menu = "cafeteria_menu"
    hostel_update = "hostel_update"
    notice = "notice"


class AdmissionStatus(str, enum.Enum):
    draft = "draft"            # documents being uploaded
    submitted = "submitted"    # all documents in -> student may pay
    approved = "approved"      # admin verified documents
    rejected = "rejected"      # admin rejected; student can re-upload and resubmit


class DocType(str, enum.Enum):
    passport_photo = "passport_photo"
    fee_receipt = "fee_receipt"      # university fee receipt
    aadhaar = "aadhaar"
    pan = "pan"


REQUIRED_DOCS = list(DocType)


class PaymentKind(str, enum.Enum):
    hostel_rent = "hostel_rent"
    mess_fee = "mess_fee"


class PaymentStatus(str, enum.Enum):
    created = "created"
    paid = "paid"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_col(Role), default=Role.student)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        # At most ONE central admin row can exist.
        Index("one_central_admin", "role", unique=True,
              postgresql_where=text("role = 'central_admin'"),
              sqlite_where=text("role = 'central_admin'")),
    )


class College(Base):
    __tablename__ = "colleges"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    city: Mapped[str] = mapped_column(String(100), index=True)
    address: Mapped[str] = mapped_column(String(300), default="")
    is_central: Mapped[bool] = mapped_column(Boolean, default=False)

    hostels: Mapped[list["Hostel"]] = relationship(back_populates="college")
    messes: Mapped[list["Mess"]] = relationship(back_populates="college")


class Amenity(Base):
    """Admin-managed catalog (wifi, ac, laundry, ro_water, ...). category: hostel | mess | cafeteria."""
    __tablename__ = "amenities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    category: Mapped[str] = mapped_column(String(10), index=True)


hostel_amenities = Table(
    "hostel_amenities", Base.metadata,
    Column("hostel_id", ForeignKey("hostels.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)
mess_amenities = Table(
    "mess_amenities", Base.metadata,
    Column("mess_id", ForeignKey("messes.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)

cafeteria_amenities = Table(
    "cafeteria_amenities", Base.metadata,
    Column("cafeteria_id", ForeignKey("cafeterias.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)


class Hostel(Base):
    __tablename__ = "hostels"
    id: Mapped[int] = mapped_column(primary_key=True)
    # The college this hostel belongs to (on_campus) or is nearest to (off_campus).
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    location: Mapped[Location] = mapped_column(enum_col(Location), index=True)
    gender: Mapped[Gender] = mapped_column(enum_col(Gender), default=Gender.co_ed)
    address: Mapped[str] = mapped_column(String(300), default="")
    distance_from_college_km: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_rent: Mapped[float] = mapped_column(Float)
    security_deposit: Mapped[float] = mapped_column(Float, default=0.0)
    room_type: Mapped[str] = mapped_column(String(50), default="double")  # single/double/triple/dorm
    total_beds: Mapped[int] = mapped_column(Integer, default=0)
    available_beds: Mapped[int] = mapped_column(Integer, default=0)
    # Infrastructure
    wifi_mbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_ac: Mapped[bool] = mapped_column(Boolean, default=False)
    attached_bathroom: Mapped[bool] = mapped_column(Boolean, default=False)
    power_backup: Mapped[bool] = mapped_column(Boolean, default=False)
    cctv: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_mess: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    college: Mapped[College] = relationship(back_populates="hostels")
    amenity_items: Mapped[list[Amenity]] = relationship(secondary=hostel_amenities, lazy="selectin")

    @property
    def amenities(self) -> list[str]:
        return sorted(a.name for a in self.amenity_items)


class Mess(Base):
    __tablename__ = "messes"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    location: Mapped[Location] = mapped_column(enum_col(Location), index=True)
    address: Mapped[str] = mapped_column(String(300), default="")
    distance_from_college_km: Mapped[float] = mapped_column(Float, default=0.0)
    food_type: Mapped[FoodType] = mapped_column(enum_col(FoodType), default=FoodType.both)
    monthly_price: Mapped[float] = mapped_column(Float)          # full plan
    price_per_meal: Mapped[float | None] = mapped_column(Float, nullable=True)
    meals_per_day: Mapped[int] = mapped_column(Integer, default=2)
    hygiene_rating: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-5 (inspected)
    seating_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    college: Mapped[College] = relationship(back_populates="messes")
    amenity_items: Mapped[list[Amenity]] = relationship(secondary=mess_amenities, lazy="selectin")

    @property
    def amenities(self) -> list[str]:
        return sorted(a.name for a in self.amenity_items)


class Cafeteria(Base):
    """Snacks / tea / quick meals outlet, pay-per-item (unlike a mess, which is a monthly plan)."""
    __tablename__ = "cafeterias"
    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    location: Mapped[Location] = mapped_column(enum_col(Location), index=True)
    address: Mapped[str] = mapped_column(String(300), default="")
    distance_from_college_km: Mapped[float] = mapped_column(Float, default=0.0)
    food_type: Mapped[FoodType] = mapped_column(enum_col(FoodType), default=FoodType.both)
    cuisine: Mapped[str] = mapped_column(String(100), default="")   # "North Indian, Snacks"
    avg_meal_price: Mapped[float] = mapped_column(Float)            # typical spend for one meal
    min_item_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # e.g. cutting chai
    opens_at: Mapped[str | None] = mapped_column(String(5), nullable=True)      # "08:00"
    closes_at: Mapped[str | None] = mapped_column(String(5), nullable=True)     # "22:30"
    hygiene_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    seating_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_delivery: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    college: Mapped[College] = relationship()
    amenity_items: Mapped[list[Amenity]] = relationship(secondary=cafeteria_amenities, lazy="selectin")

    @property
    def amenities(self) -> list[str]:
        return sorted(a.name for a in self.amenity_items)


class DailyPost(Base):
    """Posted every day by the central college about other colleges' mess/hostel."""
    __tablename__ = "daily_posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), index=True)
    kind: Mapped[PostKind] = mapped_column(enum_col(PostKind), index=True)
    mess_id: Mapped[int | None] = mapped_column(ForeignKey("messes.id"), nullable=True)
    hostel_id: Mapped[int | None] = mapped_column(ForeignKey("hostels.id"), nullable=True)
    cafeteria_id: Mapped[int | None] = mapped_column(ForeignKey("cafeterias.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    post_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_type: Mapped[str] = mapped_column(String(10))  # hostel | mess | cafeteria
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdmissionApplication(Base):
    __tablename__ = "admission_applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    hostel_id: Mapped[int] = mapped_column(ForeignKey("hostels.id"), index=True)
    status: Mapped[AdmissionStatus] = mapped_column(enum_col(AdmissionStatus), default=AdmissionStatus.draft)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents: Mapped[list["AdmissionDocument"]] = relationship(
        back_populates="application", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("user_id", "hostel_id", name="uq_admission_user_hostel"),)

    @property
    def missing_documents(self) -> list[DocType]:
        have = {d.doc_type for d in self.documents}
        return [t for t in REQUIRED_DOCS if t not in have]


class AdmissionDocument(Base):
    """Metadata only; the file itself lives in private storage (see app/storage.py)."""
    __tablename__ = "admission_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("admission_applications.id", ondelete="CASCADE"),
                                                index=True)
    doc_type: Mapped[DocType] = mapped_column(enum_col(DocType))
    storage_key: Mapped[str] = mapped_column(String(100))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[AdmissionApplication] = relationship(back_populates="documents")

    __table_args__ = (UniqueConstraint("application_id", "doc_type", name="uq_admission_doc_type"),)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[PaymentKind] = mapped_column(enum_col(PaymentKind))
    hostel_id: Mapped[int | None] = mapped_column(ForeignKey("hostels.id"), nullable=True)
    mess_id: Mapped[int | None] = mapped_column(ForeignKey("messes.id"), nullable=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("admission_applications.id"), nullable=True)
    months: Mapped[int] = mapped_column(Integer, default=1)
    include_deposit: Mapped[bool] = mapped_column(Boolean, default=False)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[PaymentStatus] = mapped_column(enum_col(PaymentStatus), default=PaymentStatus.created)
    provider: Mapped[str] = mapped_column(String(30), default="mock")
    provider_order_id: Mapped[str] = mapped_column(String(100), default="")
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
