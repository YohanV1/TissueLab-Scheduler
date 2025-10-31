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


class JobType(str, Enum):
    SEGMENT_CELLS = "SEGMENT_CELLS"
    TISSUE_MASK = "TISSUE_MASK"


class JobInfo(BaseModel):
    job_id: str
    workflow_id: str
    user_id: str
    file_id: str
    job_type: JobType
    branch: Optional[str] = Field(default=None, description="Branch identifier for serial execution grouping")
    state: JobState
    progress: float = Field(0.0, ge=0.0, le=1.0, description="0.0 to 1.0 fraction complete")
    tiles_processed: int = Field(0, description="Number of tiles processed")
    tiles_total: int = Field(0, description="Total number of tiles")
    result_path: Optional[str] = Field(default=None, description="Server path to job result file (internal)")


class WorkflowInfo(BaseModel):
    workflow_id: str
    user_id: str
    state: WorkflowState
    percent_complete: float = Field(0.0, ge=0.0, le=1.0)


class CreateJobRequest(BaseModel):
    workflow_id: str
    file_id: str
    job_type: JobType
    branch: str | None = None


class CreateJobResponse(BaseModel):
    job: JobInfo


class CreateWorkflowRequest(BaseModel):
    name: str | None = None


class CreateWorkflowResponse(BaseModel):
    workflow: WorkflowInfo


class FileInfo(BaseModel):
    file_id: str
    user_id: str
    filename: str
    content_type: str | None = None


class UploadFileResponse(BaseModel):
    file: FileInfo

