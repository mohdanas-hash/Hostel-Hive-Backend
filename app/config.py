from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Same DATABASE_URL is used by Drizzle (drizzle.config.ts) and the app.
    database_url: str = "sqlite:///./hostel_hive.db"
    secret_key: str = "change-me-in-production-use-a-32-byte-secret-key"
    access_token_minutes: int = 60 * 24
    payment_provider: str = "mock"  # swap for razorpay/stripe
    # The single admin is created on startup if missing.
    admin_email: str | None = None
    admin_password: str | None = None
    admin_name: str = "Central Admin"
    storage_dir: str = "./storage"        # private; never served statically
    max_upload_mb: int = 5
    cors_origins: str = "*"  # comma separated
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        # Neon gives postgresql://...; SQLAlchemy needs the driver spelled out.
        for prefix in ("postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v


settings = Settings()
