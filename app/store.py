import asyncio
import uuid
from typing import Dict, List, Optional

from .schemas import JobInfo, JobState


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobInfo] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, *, workflow_id: str, branch: Optional[str]) -> JobInfo:
        async with self._lock:
            job_id = str(uuid.uuid4())
            job = JobInfo(job_id=job_id, branch=branch, state=JobState.PENDING, progress=0.0)
            self._jobs[job_id] = job
            return job

    async def get_job(self, job_id: str) -> Optional[JobInfo]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_jobs(self) -> List[JobInfo]:
        async with self._lock:
            return list(self._jobs.values())


job_store = JobStore()


