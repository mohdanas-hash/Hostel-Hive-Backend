"""Hostel admission: apply -> upload documents -> submit -> (pay) ; admin can review."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import (AdmissionApplication, AdmissionDocument, AdmissionStatus, DocType, Hostel, Role,
                      User)
from ..schemas import AdmissionIn, AdmissionOut, AdmissionReviewIn
from ..security import get_current_user, require_role
from ..storage import LocalStorage, get_storage

router = APIRouter(prefix="/admissions", tags=["hostel admission"])

# magic bytes -> (content type, extension)
SIGNATURES = {
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
    b"%PDF-": ("application/pdf", ".pdf"),
}
IMAGE_ONLY = {DocType.passport_photo}


def sniff(data: bytes) -> tuple[str, str] | None:
    for sig, info in SIGNATURES.items():
        if data.startswith(sig):
            return info
    return None


def load(db: Session, application_id: int, user: User) -> AdmissionApplication:
    app = db.get(AdmissionApplication, application_id)
    # 404 (not 403) for other people's applications so ids can't be probed
    if not app or (user.role != Role.central_admin and app.user_id != user.id):
        raise HTTPException(404, "Application not found")
    return app


@router.post("", response_model=AdmissionOut, status_code=201)
def apply(data: AdmissionIn, db: Session = Depends(get_db),
          user: User = Depends(require_role(Role.student, Role.visitor))):
    """Start an admission application for a hostel. Returns the existing one if already started."""
    hostel = db.get(Hostel, data.hostel_id)
    if not hostel or not hostel.is_active:
        raise HTTPException(404, "Hostel not found")
    existing = db.scalar(select(AdmissionApplication).where(
        AdmissionApplication.user_id == user.id, AdmissionApplication.hostel_id == data.hostel_id))
    if existing:
        return existing
    if hostel.available_beds <= 0:
        raise HTTPException(409, "No beds available in this hostel")
    application = AdmissionApplication(user_id=user.id, hostel_id=data.hostel_id)
    db.add(application)
    db.commit()
    return application


@router.get("", response_model=list[AdmissionOut])
def list_applications(status: AdmissionStatus | None = None, hostel_id: int | None = None,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Students see their own; the admin sees everyone's."""
    q = select(AdmissionApplication).order_by(AdmissionApplication.created_at.desc())
    if user.role != Role.central_admin:
        q = q.where(AdmissionApplication.user_id == user.id)
    if status:
        q = q.where(AdmissionApplication.status == status)
    if hostel_id:
        q = q.where(AdmissionApplication.hostel_id == hostel_id)
    return db.scalars(q).all()


@router.get("/{application_id}", response_model=AdmissionOut)
def get_application(application_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return load(db, application_id, user)


@router.put("/{application_id}/documents/{doc_type}", response_model=AdmissionOut)
async def upload_document(application_id: int, doc_type: DocType, file: UploadFile = File(...),
                          db: Session = Depends(get_db), user: User = Depends(get_current_user),
                          storage: LocalStorage = Depends(get_storage)):
    """Upload (or replace) one document. JPEG/PNG/PDF, max MAX_UPLOAD_MB. Passport photo: image only."""
    application = load(db, application_id, user)
    if application.user_id != user.id:
        raise HTTPException(403, "Only the applicant can upload documents")
    if application.status not in (AdmissionStatus.draft, AdmissionStatus.rejected):
        raise HTTPException(409, f"Documents are locked while application is {application.status.value}")

    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File too large (max {settings.max_upload_mb} MB)")
    if not data:
        raise HTTPException(422, "Empty file")
    kind = sniff(data)  # trust file contents, not the client-sent content type/extension
    if not kind or (doc_type in IMAGE_ONLY and kind[0] == "application/pdf"):
        allowed = "JPEG or PNG" if doc_type in IMAGE_ONLY else "JPEG, PNG or PDF"
        raise HTTPException(422, f"{doc_type.value} must be a {allowed} file")
    content_type, ext = kind

    key = storage.save(data, ext)
    doc = next((d for d in application.documents if d.doc_type == doc_type), None)
    if doc:
        storage.delete(doc.storage_key)
        doc.storage_key, doc.content_type, doc.size_bytes = key, content_type, len(data)
        doc.original_name = (file.filename or "upload")[:255]
        doc.uploaded_at = datetime.now(timezone.utc)
    else:
        application.documents.append(AdmissionDocument(
            doc_type=doc_type, storage_key=key, original_name=(file.filename or "upload")[:255],
            content_type=content_type, size_bytes=len(data)))
    db.commit()
    return application


@router.get("/{application_id}/documents/{doc_type}")
def download_document(application_id: int, doc_type: DocType, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user), storage: LocalStorage = Depends(get_storage)):
    """Owner or admin only (identity documents are never public)."""
    application = load(db, application_id, user)
    doc = next((d for d in application.documents if d.doc_type == doc_type), None)
    if not doc:
        raise HTTPException(404, "Document not uploaded")
    return FileResponse(storage.path(doc.storage_key), media_type=doc.content_type,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{application_id}/submit", response_model=AdmissionOut)
def submit(application_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    application = load(db, application_id, user)
    if application.user_id != user.id:
        raise HTTPException(403, "Only the applicant can submit")
    if application.status not in (AdmissionStatus.draft, AdmissionStatus.rejected):
        raise HTTPException(409, f"Application is already {application.status.value}")
    if application.missing_documents:
        raise HTTPException(409, {"message": "Upload all required documents first",
                                  "missing": [d.value for d in application.missing_documents]})
    application.status = AdmissionStatus.submitted
    application.submitted_at = datetime.now(timezone.utc)
    application.reject_reason = None
    db.commit()
    return application


@router.post("/{application_id}/review", response_model=AdmissionOut)
def review(application_id: int, data: AdmissionReviewIn, db: Session = Depends(get_db),
           user: User = Depends(require_role(Role.central_admin))):
    application = load(db, application_id, user)
    if application.status != AdmissionStatus.submitted:
        raise HTTPException(409, "Only submitted applications can be reviewed")
    if not data.approve and not (data.reason and data.reason.strip()):
        raise HTTPException(422, "A reason is required when rejecting")
    application.status = AdmissionStatus.approved if data.approve else AdmissionStatus.rejected
    application.reject_reason = None if data.approve else data.reason.strip()
    application.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return application
