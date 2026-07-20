import cv2
from app.analysis.types import AnalysisContext, CheckResult
from app.core.config import get_settings

settings = get_settings()


def check_blur(ctx: AnalysisContext) -> CheckResult:
    """
    Variance-of-Laplacian blur detector. Standard, well-understood heuristic:
    convolve with a Laplacian kernel (captures edges/high-frequency detail)
    and take the variance of the response. Sharp images have lots of
    high-frequency edge content -> high variance. Blurry images smear edges
    -> low variance.

    This is a coarse heuristic, not a classifier - it's cheap (single
    convolution), explainable, and good enough to flag obviously unusable
    field photos, which is the actual goal here (see assignment: "not
    perfect ML accuracy").
    """
    gray = cv2.cvtColor(ctx.cv_image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()

    is_blurry = variance < settings.blur_laplacian_threshold
    # confidence scales with how far we are from the threshold, capped at 0.95
    # (never claim full certainty from a single scalar heuristic)
    distance_ratio = abs(variance - settings.blur_laplacian_threshold) / settings.blur_laplacian_threshold
    confidence = min(0.5 + distance_ratio * 0.4, 0.95)

    return CheckResult(
        check_name="blur_detection",
        passed=not is_blurry,
        severity="critical" if is_blurry else "info",
        confidence=round(confidence, 2),
        message=(
            f"Image appears blurry (sharpness score {variance:.1f}, "
            f"threshold {settings.blur_laplacian_threshold})"
            if is_blurry else
            f"Image sharpness OK (score {variance:.1f})"
        ),
        details={"laplacian_variance": round(variance, 2), "threshold": settings.blur_laplacian_threshold},
    )
