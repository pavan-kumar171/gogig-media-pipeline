import cv2
from PIL import Image
from app.analysis.types import AnalysisContext, CheckResult
from app.analysis.blur import check_blur
from app.analysis.brightness import check_brightness
from app.analysis.dimensions import check_dimensions
from app.analysis.duplicate import check_duplicate, compute_phash
from app.analysis.screenshot import check_screenshot
from app.analysis.metadata_tamper import check_metadata_tamper
from app.analysis.plate_ocr import check_plate_ocr

# Ordered registry - order matters only for readability of results, not
# correctness, since each check is independent and stateless (reads ctx,
# returns a CheckResult, no shared mutable state between checks).
CHECK_REGISTRY = [
    check_blur,
    check_brightness,
    check_dimensions,
    check_duplicate,
    check_screenshot,
    check_metadata_tamper,
    check_plate_ocr,
]


def build_context(job_id: str, image_path: str, db_session=None) -> AnalysisContext:
    cv_image = cv2.imread(image_path)
    if cv_image is None:
        raise ValueError(f"OpenCV could not decode image at {image_path} (corrupt or unsupported format)")
    pil_image = Image.open(image_path)
    return AnalysisContext(
        job_id=job_id, image_path=image_path, cv_image=cv_image,
        pil_image=pil_image, db_session=db_session,
    )


def run_all_checks(ctx: AnalysisContext) -> list[CheckResult]:
    """
    Runs every registered check independently and never lets one check's
    failure kill the others - a bug in the OCR check shouldn't stop us
    reporting blur/brightness results. Each check failure becomes its own
    CheckResult with severity="critical" so it's visible in the report
    rather than silently swallowed.
    """
    results = []
    for check_fn in CHECK_REGISTRY:
        try:
            results.append(check_fn(ctx))
        except Exception as exc:  # noqa: BLE001 - intentionally broad, see docstring
            results.append(CheckResult(
                check_name=check_fn.__name__.replace("check_", ""),
                passed=False,
                severity="critical",
                confidence=0.0,
                message=f"Check raised an exception: {exc}",
                details={"error_type": type(exc).__name__},
            ))
    return results


def compute_overall_confidence(results: list[CheckResult]) -> tuple[float, bool]:
    """
    Aggregate confidence = mean of individual check confidences.
    has_issues = True if ANY check with severity 'warning' or 'critical' failed.
    This is intentionally simple (mean, not weighted) - see README for why
    a weighted/learned aggregation is future work, not in-scope here.
    """
    if not results:
        return 0.0, False
    avg_confidence = sum(r.confidence for r in results) / len(results)
    has_issues = any((not r.passed) and r.severity in ("warning", "critical") for r in results)
    return round(avg_confidence, 3), has_issues
