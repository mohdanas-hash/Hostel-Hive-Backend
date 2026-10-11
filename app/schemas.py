from datetime import date, datetime

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from .models import AdmissionStatus, DocType, FoodType, Gender, Location, PaymentKind, PaymentStatus, PostKind, Role


# Only images hosted on our Cloudinary (returned by POST /images) may be attached.
ImageUrl = Annotated[str, StringConstraints(pattern=r"^https://res\.cloudinary\.com/", max_length=500)]

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6)
    # Public signup can only be visitor/student. Central admins are created by seed/admin.
    role: Role = Role.student
    college_id: int | None = None


class UserOut(ORM):
    id: int
    name: str
    email: EmailStr
    role: Role
    college_id: int | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- colleges ----
class CollegeIn(BaseModel):
    name: str
    city: str
    address: str = ""
    is_central: bool = False


class CollegeOut(ORM, CollegeIn):
    id: int


# ---- amenities ----
class AmenityIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    category: str = Field(pattern="^(hostel|mess|cafeteria)$")


class AmenityOut(ORM, AmenityIn):
    id: int


# ---- hostels ----
class HostelIn(BaseModel):
    college_id: int
    name: str
    location: Location
    gender: Gender = Gender.co_ed
    address: str = ""
    distance_from_college_km: float = 0.0
    monthly_rent: float = Field(gt=0)
    security_deposit: float = 0.0
    room_type: str = "double"
    total_beds: int = 0
    available_beds: int = 0
    amenities: list[str] = []
    wifi_mbps: int | None = None
    has_ac: bool = False
    attached_bathroom: bool = False
    power_backup: bool = False
    cctv: bool = False
    includes_mess: bool = False
    image_url: ImageUrl | None = None


class HostelOut(ORM, HostelIn):
    id: int
    is_active: bool
    avg_rating: float | None = None


# ---- mess ----
class MessIn(BaseModel):
    college_id: int
    name: str
    location: Location
    address: str = ""
    distance_from_college_km: float = 0.0
    food_type: FoodType = FoodType.both
    monthly_price: float = Field(gt=0)
    price_per_meal: float | None = None
    meals_per_day: int = 2
    hygiene_rating: float | None = Field(default=None, ge=0, le=5)
    seating_capacity: int | None = None
    image_url: ImageUrl | None = None
    amenities: list[str] = []


class MessOut(ORM, MessIn):
    id: int
    is_active: bool
    avg_rating: float | None = None


# ---- cafeteria ----
class CafeteriaIn(BaseModel):
    college_id: int
    name: str
    location: Location
    address: str = ""
    distance_from_college_km: float = 0.0
    food_type: FoodType = FoodType.both
    cuisine: str = ""
    avg_meal_price: float = Field(gt=0)
    min_item_price: float | None = Field(default=None, ge=0)
    opens_at: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    closes_at: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    hygiene_rating: float | None = Field(default=None, ge=0, le=5)
    seating_capacity: int | None = None
    home_delivery: bool = False
    image_url: ImageUrl | None = None
    amenities: list[str] = []


class CafeteriaOut(ORM, CafeteriaIn):
    id: int
    is_active: bool
    avg_rating: float | None = None


# ---- daily posts ----
class PostIn(BaseModel):
    college_id: int
    kind: PostKind
    mess_id: int | None = None
    hostel_id: int | None = None
    cafeteria_id: int | None = None
    title: str
    body: str = ""
    image_url: ImageUrl | None = None
    post_date: date | None = None  # defaults to today


class PostOut(ORM):
    id: int
    college_id: int
    kind: PostKind
    mess_id: int | None
    hostel_id: int | None
    cafeteria_id: int | None
    title: str
    body: str
    image_url: str | None = None
    post_date: date
    created_at: datetime


# ---- reviews ----
class ReviewIn(BaseModel):
    target_type: str = Field(pattern="^(hostel|mess|cafeteria)$")
    target_id: int
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class ReviewOut(ORM, ReviewIn):
    id: int
    user_id: int
    created_at: datetime


# ---- payments ----
class PaymentIn(BaseModel):
    kind: PaymentKind
    hostel_id: int | None = None
    mess_id: int | None = None
    months: int = Field(default=1, ge=1, le=12)
    include_deposit: bool = False  # hostel_rent only: add the security deposit to this payment


class PaymentOut(ORM):
    id: int
    kind: PaymentKind
    hostel_id: int | None
    mess_id: int | None
    application_id: int | None
    months: int
    include_deposit: bool
    amount: float
    currency: str
    status: PaymentStatus
    provider: str
    provider_order_id: str
    provider_payment_id: str | None
    created_at: datetime
    paid_at: datetime | None


class PaymentConfirmIn(BaseModel):
    provider_payment_id: str
    success: bool = True


# ---- hostel admission ----
class AdmissionIn(BaseModel):
    hostel_id: int


class DocumentOut(ORM):
    doc_type: DocType
    original_name: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class AdmissionOut(ORM):
    id: int
    user_id: int
    hostel_id: int
    student_name: str | None = None
    student_email: str | None = None
    status: AdmissionStatus
    reject_reason: str | None
    created_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    documents: list[DocumentOut]
    missing_documents: list[DocType]


class AdmissionReviewIn(BaseModel):
    approve: bool
    reason: str | None = None  # required when rejecting


# ---- admin ----
class Page(BaseModel, Generic[T]):
    """Paged admin list: `items` is one page, `total` counts every match."""
    items: list[T]
    total: int


class AdminUserOut(ORM):
    id: int
    name: str
    email: EmailStr
    role: Role
    college_id: int | None
    created_at: datetime
    admissions: int = 0
    payments: int = 0
    reviews: int = 0


class AdminPaymentOut(PaymentOut):
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    hostel_name: str | None = None
    mess_name: str | None = None


class AdminReviewOut(ReviewOut):
    user_name: str | None = None
    target_name: str | None = None
