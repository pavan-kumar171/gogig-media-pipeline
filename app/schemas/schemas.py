import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class UploadResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str = "Upload accepted, processing queued."


class AnalysisCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_name: str
    passed: bool
    severity: str
    confidence: float
    message: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    status: str
    retry_count: int
    created_at: datetime
    updated_at: datetime
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None


class JobResultResponse(JobStatusResponse):
    overall_confidence: Optional[float] = None
    has_issues: Optional[bool] = None
    checks: list[AnalysisCheckOut] = []
