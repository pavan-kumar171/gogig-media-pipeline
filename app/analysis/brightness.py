import cv2
import numpy as np
from app.analysis.types import AnalysisContext, CheckResult
from app.core.config import get_settings

settings = get_settings()


def check_brightness(ctx: AnalysisContext) -> CheckResult:
    """
    Mean pixel intensity on the grayscale image (0=black, 255=white).
    Flags two distinct field-photo failure modes:
      - low light: vehicle shot at night/indoors without flash
      - overexposed: washed out by direct sun/flash glare
    Both make downstream detail (plate numbers, damage, etc.) unreadable,
    which is the actual business reason to flag them.
    """
    gray = cv2.cvtColor(ctx.cv_image, cv2.COLOR_BGR2GRAY)
    mean_intensity = float(np.mean(gray))

    if mean_intensity < settings.low_light_mean_threshold:
        return CheckResult(
            check_name="brightness_analysis",
            passed=False,
            severity="warning",
            confidence=0.8,
            message=f"Image is too dark (mean intensity {mean_intensity:.1f}/255)",
            details={"mean_intensity": round(mean_intensity, 2), "issue": "low_light"},
        )
    if mean_intensity > settings.over_exposed_mean_threshold:
        return CheckResult(
            check_name="brightness_analysis",
            passed=False,
            severity="warning",
            confidence=0.8,
            message=f"Image is overexposed/washed out (mean intensity {mean_intensity:.1f}/255)",
            details={"mean_intensity": round(mean_intensity, 2), "issue": "overexposed"},
        )
    return CheckResult(
        check_name="brightness_analysis",
        passed=True,
        confidence=0.85,
        message=f"Brightness OK (mean intensity {mean_intensity:.1f}/255)",
        details={"mean_intensity": round(mean_intensity, 2)},
    )
