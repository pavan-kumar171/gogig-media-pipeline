import imagehash
from app.analysis.types import AnalysisContext, CheckResult
from app.core.config import get_settings
from app.models.models import ImageJob

settings = get_settings()


def compute_phash(pil_image) -> str:
    """Exposed separately so the Celery task can store the hash on the job
    row even when the duplicate check itself isn't run standalone."""
    return str(imagehash.phash(pil_image))


def check_duplicate(ctx: AnalysisContext) -> CheckResult:
    """
    Perceptual hashing (pHash), not byte-for-byte hashing (MD5/SHA256).
    Field uploads are frequently re-compressed, resized, or re-saved by the
    phone/app before reaching us, so exact-byte duplicates are rare; pHash
    is robust to that because it hashes on downsampled/DCT structure rather
    than raw bytes. Hamming distance between hashes approximates visual
    similarity - small distance = likely the same photo.

    Trade-off: this is O(n) against all prior jobs (see README). Fine for
    an assignment; would need a proper nearest-neighbor index (e.g. a
    vector/LSH index) at real scale.
    """
    current_hash_str = compute_phash(ctx.pil_image)
    current_hash = imagehash.hex_to_hash(current_hash_str)

    if ctx.db_session is None:
        return CheckResult(
            check_name="duplicate_detection",
            passed=True,
            confidence=0.0,
            message="Skipped - no database session available",
            details={"phash": current_hash_str},
        )

    prior_jobs = (
        ctx.db_session.query(ImageJob)
        .filter(ImageJob.perceptual_hash.isnot(None), ImageJob.id != ctx.job_id)
        .all()
    )

    closest_distance = None
    closest_job_id = None
    for job in prior_jobs:
        try:
            other_hash = imagehash.hex_to_hash(job.perceptual_hash)
        except (TypeError, ValueError):
            continue
        distance = current_hash - other_hash
        if closest_distance is None or distance < closest_distance:
            closest_distance = distance
            closest_job_id = str(job.id)

    is_duplicate = closest_distance is not None and closest_distance <= settings.duplicate_hash_distance

    return CheckResult(
        check_name="duplicate_detection",
        passed=not is_duplicate,
        severity="warning" if is_duplicate else "info",
        confidence=0.75 if is_duplicate else 0.9,
        message=(
            f"Likely duplicate of job {closest_job_id} (hash distance {closest_distance})"
            if is_duplicate else
            "No duplicate found among prior uploads"
        ),
        details={
            "phash": current_hash_str,
            "closest_match_job_id": closest_job_id,
            "closest_distance": closest_distance,
            "threshold": settings.duplicate_hash_distance,
        },
    )
