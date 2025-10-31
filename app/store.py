import asyncio
import uuid
from typing import Dict, List, Optional

from .schemas import JobInfo, JobState, JobType


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobInfo] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, *, workflow_id: str, branch: Optional[str], user_id: str, file_id: str, job_type: JobType) -> JobInfo:
        async with self._lock:
            job_id = str(uuid.uuid4())
            job = JobInfo(
                job_id=job_id,
                workflow_id=workflow_id,
                user_id=user_id,
                file_id=file_id,
                job_type=job_type,
                branch=branch,
                state=JobState.PENDING,
                progress=0.0,
                tiles_processed=0,
                tiles_total=0,
                result_path=None,
            )
            self._jobs[job_id] = job
            return job

    async def get_job(self, job_id: str) -> Optional[JobInfo]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_jobs(self) -> List[JobInfo]:
        async with self._lock:
            return list(self._jobs.values())

    async def list_jobs_for_user(self, user_id: str) -> List[JobInfo]:
        async with self._lock:
            return [j for j in self._jobs.values() if j.user_id == user_id]

    async def update_job_state(self, job_id: str, state: JobState) -> Optional[JobInfo]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.state = state
            return job

    async def set_job_progress(self, job_id: str, progress: float, tiles_processed: int = 0, tiles_total: int = 0) -> Optional[JobInfo]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.progress = progress
            if tiles_total > 0:
                job.tiles_total = tiles_total
            if tiles_processed >= 0:
                job.tiles_processed = tiles_processed
            return job

    async def set_job_result_path(self, job_id: str, path: str) -> Optional[JobInfo]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.result_path = path
            return job

    async def reset_for_retry(self, job_id: str) -> Optional[JobInfo]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.state == JobState.RUNNING:
                return job
            job.state = JobState.PENDING
            job.progress = 0.0
            job.result_path = None
            return job

    async def cancel_job_if_pending(self, job_id: str) -> Optional[JobInfo]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.state != JobState.PENDING:
                return job
            job.state = JobState.CANCELED
            return job


job_store = JobStore()


