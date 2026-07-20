from app.analysis.types import AnalysisContext, CheckResult
from app.core.config import get_settings

settings = get_settings()


def check_dimensions(ctx: AnalysisContext) -> CheckResult:
    """Rejects images too small to be useful field photos (vs. thumbnails/icons)."""
    h, w = ctx.cv_image.shape[:2]
    is_too_small = w < settings.min_width or h < settings.min_height

    return CheckResult(
        check_name="dimension_validation",
        passed=not is_too_small,
        severity="warning" if is_too_small else "info",
        confidence=1.0,  # this is a deterministic check, not a heuristic
        message=(
            f"Image resolution too low ({w}x{h}), minimum is "
            f"{settings.min_width}x{settings.min_height}"
            if is_too_small else
            f"Resolution OK ({w}x{h})"
        ),
        details={"width": w, "height": h},
    )
