from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class WorkflowState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class JobInfo(BaseModel):
    job_id: str
    branch: Optional[str] = Field(default=None, description="Branch identifier for serial execution grouping")
    state: JobState
    progress: float = Field(0.0, ge=0.0, le=1.0, description="0.0 to 1.0 fraction complete")


class WorkflowInfo(BaseModel):
    workflow_id: str
    state: WorkflowState
    percent_complete: float = Field(0.0, ge=0.0, le=1.0)


class CreateJobRequest(BaseModel):
    workflow_id: str
    branch: str | None = None


class CreateJobResponse(BaseModel):
    job: JobInfo

