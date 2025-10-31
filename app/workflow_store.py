import asyncio
import uuid
from typing import Dict, Optional

from .schemas import WorkflowInfo, WorkflowState
from .store import job_store


class WorkflowStore:
    def __init__(self) -> None:
        self._workflows: Dict[str, tuple[str, str]] = {}  # id -> (user_id, name)
        self._lock = asyncio.Lock()

    async def create_workflow(self, *, user_id: str, name: Optional[str]) -> WorkflowInfo:
        async with self._lock:
            workflow_id = str(uuid.uuid4())
            self._workflows[workflow_id] = (user_id, name or "")
            # New workflows start empty → PENDING, 0.0
            return WorkflowInfo(workflow_id=workflow_id, user_id=user_id, state=WorkflowState.PENDING, percent_complete=0.0)

    async def exists(self, workflow_id: str) -> bool:
        async with self._lock:
            return workflow_id in self._workflows

    async def owned_by(self, workflow_id: str, user_id: str) -> bool:
        async with self._lock:
            meta = self._workflows.get(workflow_id)
            return meta is not None and meta[0] == user_id

    async def get_workflow_info(self, workflow_id: str) -> Optional[WorkflowInfo]:
        # Aggregate from jobs to calculate state and percent complete
        if not await self.exists(workflow_id):
            return None
        # Determine owner
        async with self._lock:
            owner_user_id, _ = self._workflows[workflow_id]

        jobs = [j for j in await job_store.list_jobs() if j.workflow_id == workflow_id]
        if not jobs:
            return WorkflowInfo(workflow_id=workflow_id, user_id=owner_user_id, state=WorkflowState.PENDING, percent_complete=0.0)

        num_jobs = len(jobs)
        avg_progress = sum(j.progress for j in jobs) / num_jobs

        if any(j.state == j.state.FAILED for j in jobs):
            state = WorkflowState.FAILED
        elif all(j.state == j.state.SUCCEEDED for j in jobs):
            state = WorkflowState.SUCCEEDED
        elif any(j.state == j.state.RUNNING for j in jobs):
            state = WorkflowState.RUNNING
        else:
            state = WorkflowState.PENDING

        return WorkflowInfo(workflow_id=workflow_id, user_id=owner_user_id, state=state, percent_complete=avg_progress)


workflow_store = WorkflowStore()


