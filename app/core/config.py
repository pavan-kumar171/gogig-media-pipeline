"""
Central configuration. All tunables live here so the rest of the codebase
never hardcodes paths/thresholds - makes the heuristics easy to defend/tune
in an interview ("why 100.0 for blur?" -> "it's a config constant, here's why").
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://gogig:gogig@localhost:5432/gogig_pipeline"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Storage
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 15
    allowed_extensions: tuple = (".jpg", ".jpeg", ".png", ".webp")

    # Analysis thresholds (tuned heuristically, documented in README)
    blur_laplacian_threshold: float = 100.0       # below this variance -> blurry
    low_light_mean_threshold: float = 60.0        # mean pixel intensity (0-255)
    over_exposed_mean_threshold: float = 235.0    # too bright / washed out
    duplicate_hash_distance: int = 5              # perceptual hash hamming distance
    # Deliberately excludes 4:3 (3,4) even though many phone screenshots use
    # it, because it's ALSO the standard camera sensor ratio - including it
    # caused false positives on every normal photo during testing. Kept
    # narrow (tall, notch-era phone ratios) to bias toward precision over
    # recall, per the "combine with missing-EXIF" logic in the check itself.
    screenshot_aspect_ratios: tuple = (
        (9, 19.5), (9, 20), (9, 16)
    )
    min_width: int = 400
    min_height: int = 400

    # Retry policy
    max_task_retries: int = 3
    retry_backoff_seconds: int = 5

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
