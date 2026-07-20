"""
Storage is deliberately behind a tiny interface so swapping local disk for
S3/GCS later is a one-file change, not a rewrite. Only local disk is
implemented here (see README trade-offs for why).
"""
import os
import uuid
from pathlib import Path
from fastapi import UploadFile
from app.core.config import get_settings

settings = get_settings()


class LocalStorage:
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir or settings.upload_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, file: UploadFile, job_id: uuid.UUID) -> str:
        ext = Path(file.filename).suffix.lower()
        dest = self.base_dir / f"{job_id}{ext}"
        with open(dest, "wb") as out:
            # stream in chunks rather than reading the whole upload into
            # memory at once - matters once images get large
            while chunk := file.file.read(1024 * 1024):
                out.write(chunk)
        return str(dest)

    def path_for(self, stored_path: str) -> Path:
        return Path(stored_path)


storage = LocalStorage()
