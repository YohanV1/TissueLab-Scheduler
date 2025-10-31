import asyncio
import json
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from .schemas import CreateJobRequest, CreateJobResponse, JobInfo, JobState
from .store import job_store
from .scheduler import enqueue_job
from .workflow_store import workflow_store
from .file_store import file_store


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/", response_model=CreateJobResponse)
async def create_job_endpoint(payload: CreateJobRequest, x_user_id: str = Header(alias="X-User-ID")) -> CreateJobResponse:
    # For now we just require the header but don't enforce limits yet.
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    if not await workflow_store.owned_by(payload.workflow_id, x_user_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not await file_store.owned_by(payload.file_id, x_user_id):
        raise HTTPException(status_code=404, detail="File not found")
    job = await job_store.create_job(
        workflow_id=payload.workflow_id,
        branch=payload.branch,
        user_id=x_user_id,
        file_id=payload.file_id,
        job_type=payload.job_type,
    )
    return CreateJobResponse(job=job)


@router.get("/", response_model=list[JobInfo])
async def list_jobs_endpoint(x_user_id: str = Header(alias="X-User-ID")) -> list[JobInfo]:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    return await job_store.list_jobs_for_user(x_user_id)


@router.get("/{job_id}", response_model=JobInfo)
async def get_job_endpoint(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> JobInfo:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/start")
async def start_job(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> dict[str, str]:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state != JobState.PENDING:
        raise HTTPException(status_code=409, detail="Job is not in PENDING state")
    await enqueue_job(job_id)
    return {"status": "started"}


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> dict[str, str]:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state != JobState.PENDING:
        raise HTTPException(status_code=409, detail="Only PENDING jobs can be canceled")
    await job_store.cancel_job_if_pending(job_id)
    return {"status": "canceled"}


@router.get("/{job_id}/result")
async def download_result(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> FileResponse:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state != JobState.SUCCEEDED or not job.result_path:
        raise HTTPException(status_code=404, detail="Result not ready")
    return FileResponse(job.result_path, filename=f"{job.job_id}_result.json")


@router.get("/{job_id}/events")
async def job_events(job_id: str, user_id: str = Query(...)) -> StreamingResponse:
    # EventSource cannot set custom headers, so we pass user_id as query param.
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        last_payload: dict | None = None
        while True:
            j = await job_store.get_job(job_id)
            if j is None or j.user_id != user_id:
                break
            payload = {"state": j.state, "progress": j.progress, "tiles_processed": j.tiles_processed, "tiles_total": j.tiles_total}
            if payload != last_payload:
                yield f"data: {json.dumps(payload)}\n\n"
                last_payload = payload
            if j.state in (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELED):
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{job_id}/retry")
async def retry_job(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> dict[str, str]:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state == JobState.RUNNING:
        raise HTTPException(status_code=409, detail="Cannot retry a RUNNING job")
    await job_store.reset_for_retry(job_id)
    return {"status": "ready"}


@router.get("/{job_id}/preview")
async def preview_image(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> FileResponse:
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    # Manifest holds preview path
    import json as _json
    if not job.result_path:
        raise HTTPException(status_code=404, detail="Result not ready")
    try:
        with open(job.result_path) as f:
            manifest = _json.load(f)
        preview_path = manifest.get("preview")
        if not preview_path:
            raise FileNotFoundError
        return FileResponse(preview_path, filename=f"{job.job_id}_preview.png")
    except Exception:
        raise HTTPException(status_code=404, detail="Preview not available")


@router.get("/{job_id}/artifacts.zip")
async def download_artifacts(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> FileResponse:
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.result_path:
        raise HTTPException(status_code=404, detail="Result not ready")
    import json as _json
    import os as _os
    import zipfile as _zipfile
    try:
        with open(job.result_path) as f:
            manifest = _json.load(f)
        files = list(manifest.get("artifacts", []))
        if manifest.get("preview"):
            files.append(manifest["preview"])  # include preview too
        # Create zip alongside manifest
        job_dir = _os.path.dirname(job.result_path)
        zip_path = _os.path.join(job_dir, "artifacts.zip")
        with _zipfile.ZipFile(zip_path, "w", compression=_zipfile.ZIP_DEFLATED) as zf:
            for p in files:
                if p and _os.path.exists(p):
                    zf.write(p, arcname=_os.path.basename(p))
        return FileResponse(zip_path, filename=f"{job.job_id}_artifacts.zip")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to build artifacts zip")



@router.get("/{job_id}/queue_status")
async def get_queue_status(job_id: str, x_user_id: str = Header(alias="X-User-ID")) -> dict:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    job = await job_store.get_job(job_id)
    if job is None or job.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    from .scheduler import get_queue_status_for_job
    status = await get_queue_status_for_job(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return status

