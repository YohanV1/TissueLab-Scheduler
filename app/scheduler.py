import asyncio
from typing import Dict, Tuple, Optional

from .settings import MAX_WORKERS, MAX_ACTIVE_USERS
from .store import job_store
from .schemas import JobState
from .executor import run_job


_workers = asyncio.Semaphore(MAX_WORKERS)
_active_workers: int = 0
_branch_locks: Dict[Tuple[str, str], asyncio.Lock] = {}
_branch_locks_guard = asyncio.Lock()
_scheduled: set[str] = set()
_scheduled_guard = asyncio.Lock()

# Active users gate (max distinct users with RUNNING jobs)
_active_user_ids: set[str] = set()
_active_user_counts: dict[str, int] = {}
_user_gate = asyncio.Condition()


async def _acquire_user_slot(user_id: str) -> None:
    async with _user_gate:
        while user_id not in _active_user_ids and len(_active_user_ids) >= MAX_ACTIVE_USERS:
            await _user_gate.wait()
        if user_id not in _active_user_ids:
            _active_user_ids.add(user_id)
            _active_user_counts[user_id] = 0
        _active_user_counts[user_id] += 1


async def _release_user_slot(user_id: str) -> None:
    async with _user_gate:
        if user_id in _active_user_counts:
            _active_user_counts[user_id] -= 1
            if _active_user_counts[user_id] <= 0:
                _active_user_counts.pop(user_id, None)
                _active_user_ids.discard(user_id)
                _user_gate.notify_all()


async def _get_branch_lock(workflow_id: str, branch: str) -> asyncio.Lock:
    key = (workflow_id, branch)
    async with _branch_locks_guard:
        lock = _branch_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _branch_locks[key] = lock
        return lock


async def _worker(job_id: str) -> None:
    user_id: str | None = None
    acquired_user_slot = False
    try:
        job = await job_store.get_job(job_id)
        if job is None:
            return

        user_id = job.user_id
        branch = job.branch or "__default__"
        branch_lock = await _get_branch_lock(job.workflow_id, branch)

        async with branch_lock:
            current = await job_store.get_job(job_id)
            if current is None or current.state == JobState.CANCELED:
                return

            await _acquire_user_slot(user_id)
            acquired_user_slot = True

            current = await job_store.get_job(job_id)
            if current is None or current.state == JobState.CANCELED:
                return

            async with _workers:
                fresh = await job_store.get_job(job_id)
                if fresh is None or fresh.state == JobState.CANCELED:
                    return
                try:
                    global _active_workers
                    _active_workers += 1
                    await run_job(job_id)
                finally:
                    _active_workers -= 1
    finally:
        if acquired_user_slot and user_id is not None:
            await _release_user_slot(user_id)
        async with _scheduled_guard:
            _scheduled.discard(job_id)


async def enqueue_job(job_id: str) -> None:
    async with _scheduled_guard:
        if job_id in _scheduled:
            return
        _scheduled.add(job_id)
    asyncio.create_task(_worker(job_id))



# -------------------- Queue status helpers (for UX) --------------------
def snapshot_queue() -> dict:
    return {
        "active_users": len(_active_user_ids),
        "max_active_users": MAX_ACTIVE_USERS,
        "active_workers": _active_workers,
        "max_workers": MAX_WORKERS,
    }


async def get_queue_status_for_job(job_id: str) -> Optional[dict]:
    """Return a best-effort queue status for a job.

    waiting_for may include: "USER_SLOT", "BRANCH", "WORKER".
    """
    job = await job_store.get_job(job_id)
    if job is None:
        return None

    status = snapshot_queue()
    queued = job.state == JobState.PENDING
    waiting_for: list[str] = []

    if queued:
        # Branch serial lock: another job in same workflow+branch is RUNNING
        eff_branch = job.branch or "__default__"
        same_branch_running = any(
            (j.workflow_id == job.workflow_id) and ((j.branch or "__default__") == eff_branch) and (j.job_id != job.job_id) and (j.state == JobState.RUNNING)
            for j in await job_store.list_jobs()
        )
        if same_branch_running:
            waiting_for.append("BRANCH")

        # Active user gate full and this user not active yet
        if job.user_id not in _active_user_ids and len(_active_user_ids) >= MAX_ACTIVE_USERS:
            waiting_for.append("USER_SLOT")

        # Worker capacity is full
        if _active_workers >= MAX_WORKERS:
            waiting_for.append("WORKER")

    status.update({
        "queued": queued,
        "waiting_for": waiting_for,
    })
    return status

