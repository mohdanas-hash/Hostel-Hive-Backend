from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bootstrap import ensure_admin
from .config import settings
from .database import SessionLocal
from .routers import admissions, amenities, auth, cafeterias, colleges, compare, listings, payments, posts


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Drizzle migrations (see README) — no create_all here.
    with SessionLocal() as db:
        ensure_admin(db)
    yield


app = FastAPI(title="Hostel Hive", version="0.2.0",
              description="Compare hostels & mess across colleges (on-campus vs off-campus).",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, colleges.router, amenities.router, listings.router, cafeterias.router, admissions.router, posts.router,
          compare.router, payments.router):
    app.include_router(r)


@app.get("/", tags=["meta"])
def root():
    return {"app": "Hostel Hive", "docs": "/docs"}
