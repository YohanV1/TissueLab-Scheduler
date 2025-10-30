from fastapi import APIRouter, Header, HTTPException

from .schemas import CreateJobRequest, CreateJobResponse, JobInfo
from .store import job_store


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/", response_model=CreateJobResponse)
async def create_job_endpoint(payload: CreateJobRequest, x_user_id: str = Header(alias="X-User-ID")) -> CreateJobResponse:
    # For now we just require the header but don't enforce limits yet.
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    job = await job_store.create_job(workflow_id=payload.workflow_id, branch=payload.branch)
    return CreateJobResponse(job=job)


@router.get("/", response_model=list[JobInfo])
async def list_jobs_endpoint(x_user_id: str = Header(alias="X-User-ID")) -> list[JobInfo]:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    return await job_store.list_jobs()


@router.get("/{job_id}", response_model=JobInfo)
async def get_job_endpoint(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> JobInfo:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


