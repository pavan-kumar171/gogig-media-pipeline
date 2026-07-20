from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "gogig_pipeline",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.process_image"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,            # re-deliver if worker dies mid-task
    worker_prefetch_multiplier=1,   # don't hoard tasks - fairer across workers
    task_time_limit=120,            # hard kill runaway tasks (e.g. stuck OCR)
    task_soft_time_limit=90,
)
