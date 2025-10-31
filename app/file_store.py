import asyncio
import os
import uuid
from typing import Dict, Optional

from fastapi import UploadFile

from .schemas import FileInfo


UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
RESULTS_DIR = os.path.join(UPLOAD_DIR, "results")


class FileStore:
    def __init__(self) -> None:
        self._files: Dict[str, tuple[str, str, str | None]] = {}
        # file_id -> (user_id, filepath, content_type)
        self._lock = asyncio.Lock()
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(RESULTS_DIR, exist_ok=True)

    async def save_upload(self, *, user_id: str, upload: UploadFile) -> FileInfo:
        # Create a stable file id and path
        file_id = str(uuid.uuid4())
        ext = os.path.splitext(upload.filename or "")[1]
        disk_name = f"{file_id}{ext}"
        filepath = os.path.join(UPLOAD_DIR, disk_name)
        # Stream to disk (file write doesn't need lock, only metadata update does)
        with open(filepath, "wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        # Only lock for metadata update (quick operation)
        async with self._lock:
            self._files[file_id] = (user_id, filepath, upload.content_type)
        return FileInfo(file_id=file_id, user_id=user_id, filename=upload.filename or disk_name, content_type=upload.content_type)

    async def get_info(self, file_id: str) -> Optional[FileInfo]:
        # Read-only operation - safe without lock since dict reads are atomic
        meta = self._files.get(file_id)
        if meta is None:
            return None
        user_id, filepath, content_type = meta
        filename = os.path.basename(filepath)
        return FileInfo(file_id=file_id, user_id=user_id, filename=filename, content_type=content_type)

    async def owned_by(self, file_id: str, user_id: str) -> bool:
        # Read-only operation - safe without lock since dict reads are atomic
        meta = self._files.get(file_id)
        return meta is not None and meta[0] == user_id

    async def get_disk_path(self, file_id: str) -> Optional[str]:
        # Fast read-only operation - can be done without lock since dict reads are atomic in CPython
        # The dict won't be modified during job execution, only during file upload
        meta = self._files.get(file_id)
        return None if meta is None else meta[1]

    def get_results_dir(self) -> str:
        return RESULTS_DIR

    def get_job_dir(self, job_id: str) -> str:
        job_dir = os.path.join(RESULTS_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        return job_dir


file_store = FileStore()


