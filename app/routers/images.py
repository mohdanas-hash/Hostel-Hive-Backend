"""Image posting: upload to Cloudinary and get back a public URL to store on a hostel/cafeteria/post."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .. import images
from ..config import settings
from ..models import Role, User
from ..security import get_current_user
from .admissions import sniff

router = APIRouter(prefix="/images", tags=["images"])

ALLOWED_FOLDERS = {"hostels", "messes", "cafeterias", "posts", "colleges", "misc"}


class ImageOut(BaseModel):
    url: str
    public_id: str
    width: int | None = None
    height: int | None = None
    format: str | None = None
    bytes: int | None = None


@router.post("", response_model=ImageOut, status_code=201)
def upload_image(file: UploadFile = File(...), folder: str = Form("misc"), user: User = Depends(get_current_user)):
    """Upload a JPEG/PNG image (max MAX_UPLOAD_MB). Returns the Cloudinary URL."""
    if not images.configured():
        raise HTTPException(503, "Image hosting is not configured")
    if folder not in ALLOWED_FOLDERS:
        raise HTTPException(422, f"folder must be one of {sorted(ALLOWED_FOLDERS)}")
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File too large (max {settings.max_upload_mb} MB)")
    kind = sniff(data)
    if not kind or not kind[0].startswith("image/"):   # content sniffed, client content-type is not trusted
        raise HTTPException(415, "Only JPEG or PNG images are allowed")
    try:
        r = images.upload_image(data, folder)
    except Exception:
        raise HTTPException(502, "Image upload failed")
    return ImageOut(url=r["secure_url"], public_id=r["public_id"], width=r.get("width"),
                    height=r.get("height"), format=r.get("format"), bytes=r.get("bytes"))


@router.delete("", status_code=204)
def delete_image(public_id: str, user: User = Depends(get_current_user)):
    """Delete an image. Only the central admin may do this since uploads aren't tracked per user."""
    if user.role != Role.central_admin:
        raise HTTPException(403, "Admin only")
    if not images.configured():
        raise HTTPException(503, "Image hosting is not configured")
    if not public_id.startswith("hostel-hive/"):
        raise HTTPException(422, "Not a Hostel Hive image")
    images.delete_image(public_id)
