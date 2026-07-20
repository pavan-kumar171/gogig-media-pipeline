import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import ImageJob, JobStatus
from app.schemas.schemas import UploadResponse, JobStatusResponse, JobResultResponse
from app.storage.local_storage import storage
from app.tasks.process_image import process_image

router = APIRouter()
settings = get_settings()


@router.post("/uploads", response_model=UploadResponse, status_code=202)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {settings.allowed_extensions}",
        )

    # size guard - read content-length header if present; otherwise the
    # storage layer's chunked write plus this check afterward catches it
    file.file.seek(0, 2)
    size_bytes = file.file.tell()
    file.file.seek(0)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_size_mb}MB limit")
    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    job_id = uuid.uuid4()
    stored_path = storage.save(file, job_id)

    job = ImageJob(
        id=job_id,
        original_filename=file.filename,
        stored_path=stored_path,
        content_type=file.content_type or "application/octet-stream",
        file_size_bytes=size_bytes,
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()

    # Queue AFTER commit - if the queue enqueue fails we want the job row
    # to exist already (visible as "pending" forever) rather than losing
    # the record entirely. A background reconciler could sweep stuck
    # "pending" jobs older than N minutes and re-enqueue (see README).
    process_image.delay(str(job_id))

    return UploadResponse(job_id=job_id, status=JobStatus.PENDING.value)


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.query(ImageJob).filter(ImageJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job.id, status=job.status.value, retry_count=job.retry_count,
        created_at=job.created_at, updated_at=job.updated_at,
        processing_started_at=job.processing_started_at,
        processing_completed_at=job.processing_completed_at,
        failure_reason=job.failure_reason,
    )


@router.get("/jobs/{job_id}/results", response_model=JobResultResponse)
def get_job_results(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.query(ImageJob).filter(ImageJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job is '{job.status.value}', results not ready yet. "
                    f"Poll GET /jobs/{job_id}/status until 'completed'.",
        )
    return JobResultResponse(
        job_id=job.id, status=job.status.value, retry_count=job.retry_count,
        created_at=job.created_at, updated_at=job.updated_at,
        processing_started_at=job.processing_started_at,
        processing_completed_at=job.processing_completed_at,
        failure_reason=job.failure_reason,
        overall_confidence=job.overall_confidence, has_issues=job.has_issues,
        checks=job.checks,
    )
