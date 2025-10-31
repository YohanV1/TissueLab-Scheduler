import asyncio
import json
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from .schemas import CreateWorkflowRequest, CreateWorkflowResponse, WorkflowInfo, WorkflowState
from .workflow_store import workflow_store


router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/", response_model=CreateWorkflowResponse)
async def create_workflow_endpoint(payload: CreateWorkflowRequest, x_user_id: str = Header(alias="X-User-ID")) -> CreateWorkflowResponse:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    wf = await workflow_store.create_workflow(user_id=x_user_id, name=payload.name)
    return CreateWorkflowResponse(workflow=wf)


@router.get("/{workflow_id}", response_model=WorkflowInfo)
async def get_workflow_endpoint(workflow_id: str, x_user_id: str = Header(alias="X-User-ID")) -> WorkflowInfo:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    # Enforce ownership
    if not await workflow_store.owned_by(workflow_id, x_user_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf = await workflow_store.get_workflow_info(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.get("/{workflow_id}/jobs", response_model=list)
async def get_workflow_jobs(workflow_id: str, x_user_id: str = Header(alias="X-User-ID")) -> list:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    if not await workflow_store.owned_by(workflow_id, x_user_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    from .store import job_store
    all_jobs = await job_store.list_jobs_for_user(x_user_id)
    workflow_jobs = [j for j in all_jobs if j.workflow_id == workflow_id]
    return [{"job_id": j.job_id, "state": j.state, "progress": j.progress, "tiles_processed": j.tiles_processed, "tiles_total": j.tiles_total, "branch": j.branch} for j in workflow_jobs]


@router.get("/{workflow_id}/events")
async def workflow_events(workflow_id: str, user_id: str = Query(...)) -> StreamingResponse:
    # EventSource cannot set custom headers, so we pass user_id as query param.
    if not await workflow_store.owned_by(workflow_id, user_id):
        raise HTTPException(status_code=404, detail="Workflow not found")

    async def event_stream():
        last_payload: dict | None = None
        while True:
            wf = await workflow_store.get_workflow_info(workflow_id)
            if wf is None or wf.user_id != user_id:
                break
            # Also get all jobs in the workflow
            from .store import job_store
            all_jobs = await job_store.list_jobs_for_user(user_id)
            workflow_jobs = [j for j in all_jobs if j.workflow_id == workflow_id]
            jobs_data = [{"job_id": j.job_id, "state": j.state, "progress": j.progress, "tiles_processed": j.tiles_processed, "tiles_total": j.tiles_total} for j in workflow_jobs]
            payload = {"state": wf.state, "percent_complete": wf.percent_complete, "jobs": jobs_data}
            if payload != last_payload:
                yield f"data: {json.dumps(payload)}\n\n"
                last_payload = payload
            if wf.state in (WorkflowState.SUCCEEDED, WorkflowState.FAILED):
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


