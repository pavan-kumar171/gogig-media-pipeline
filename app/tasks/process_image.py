import logging
from datetime import datetime, timezone
from celery.exceptions import SoftTimeLimitExceeded
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models.models import ImageJob, AnalysisCheck, JobStatus
from app.analysis.registry import build_context, run_all_checks, compute_overall_confidence
from app.analysis.duplicate import compute_phash

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(
    bind=True,
    name="process_image",
    autoretry_for=(Exception,),
    retry_backoff=settings.retry_backoff_seconds,
    retry_kwargs={"max_retries": settings.max_task_retries},
)
def process_image(self, job_id: str):
    """
    Worker entrypoint. Runs in its own DB session (never shares the API
    request's session - workers and API processes are separate processes).

    State machine: pending -> processing -> (completed | failed)
    Transitions are committed as separate statements so a status API call
    mid-processing correctly shows "processing", not "pending" the whole
    time the task runs.
    """
    db = SessionLocal()
    try:
        job = db.query(ImageJob).filter(ImageJob.id == job_id).first()
        if job is None:
            logger.error("process_image: job %s not found - dropping task", job_id)
            return

        job.status = JobStatus.PROCESSING
        job.processing_started_at = datetime.now(timezone.utc)
        job.retry_count = self.request.retries
        db.commit()

        ctx = build_context(job_id=job_id, image_path=job.stored_path, db_session=db)

        # store the perceptual hash on the job row up front so subsequent
        # uploads can be compared against this one for duplicate detection
        job.perceptual_hash = compute_phash(ctx.pil_image)
        db.commit()

        results = run_all_checks(ctx)
        overall_confidence, has_issues = compute_overall_confidence(results)

        # wipe any partial results from a prior failed attempt before writing fresh ones
        db.query(AnalysisCheck).filter(AnalysisCheck.job_id == job_id).delete()
        for r in results:
            db.add(AnalysisCheck(
                job_id=job_id, check_name=r.check_name, passed=r.passed,
                severity=r.severity, confidence=r.confidence,
                message=r.message, details=r.details,
            ))

        job.overall_confidence = overall_confidence
        job.has_issues = has_issues
        job.status = JobStatus.COMPLETED
        job.processing_completed_at = datetime.now(timezone.utc)
        job.failure_reason = None
        db.commit()
        logger.info("process_image: job %s completed, has_issues=%s", job_id, has_issues)

    except SoftTimeLimitExceeded:
        _mark_failed(db, job_id, "Processing exceeded time limit (stuck OCR/decoding)")
        raise
    except Exception as exc:
        logger.exception("process_image: job %s failed", job_id)
        # on the FINAL retry (autoretry_for re-raises until max_retries is
        # hit), persist the failure so it's visible via the results API
        if self.request.retries >= self.max_retries:
            _mark_failed(db, job_id, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        db.close()


def _mark_failed(db, job_id: str, reason: str):
    job = db.query(ImageJob).filter(ImageJob.id == job_id).first()
    if job:
        job.status = JobStatus.FAILED
        job.failure_reason = reason
        job.processing_completed_at = datetime.now(timezone.utc)
        db.commit()
