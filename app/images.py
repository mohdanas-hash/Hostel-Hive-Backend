"""Public image hosting on Cloudinary (listing photos etc.). Identity documents stay in private storage."""
import cloudinary
import cloudinary.uploader

from .config import settings


def configured() -> bool:
    return bool(settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret)


def upload_image(data: bytes, folder: str) -> dict:
    cloudinary.config(cloud_name=settings.cloudinary_cloud_name, api_key=settings.cloudinary_api_key,
                      api_secret=settings.cloudinary_api_secret, secure=True)
    return cloudinary.uploader.upload(data, folder=f"hostel-hive/{folder}", resource_type="image")


def delete_image(public_id: str) -> None:
    cloudinary.config(cloud_name=settings.cloudinary_cloud_name, api_key=settings.cloudinary_api_key,
                      api_secret=settings.cloudinary_api_secret, secure=True)
    cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
