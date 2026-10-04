"""Private file storage for identity documents. Local disk now; swap for S3/R2 by keeping this interface."""
import uuid
from pathlib import Path

from .config import settings


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, ext: str) -> str:
        key = f"{uuid.uuid4().hex}{ext}"   # random name; user-supplied filename is never used on disk
        (self.root / key).write_bytes(data)
        return key

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if p.parent != self.root:           # guard against path traversal
            raise ValueError("bad key")
        return p

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage(settings.storage_dir)
