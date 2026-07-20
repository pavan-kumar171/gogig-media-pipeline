from PIL import ExifTags
from app.analysis.types import AnalysisContext, CheckResult
from app.core.config import get_settings

settings = get_settings()

_EXIF_TAGS = {v: k for k, v in ExifTags.TAGS.items()}


def check_screenshot(ctx: AnalysisContext) -> CheckResult:
    """
    Heuristic combining two independent signals, neither reliable alone:

      1. Aspect ratio match against common phone-screen/monitor ratios
         (e.g. 9:19.5 for modern phones). A real camera photo of a vehicle
         is very unlikely to naturally land on these exact ratios.
      2. Missing camera EXIF (Make/Model/FNumber/ExposureTime). Real camera
         shots carry this; screenshots and re-saved/re-compressed images
         (photo-of-photo via WhatsApp forward, etc.) typically strip it.

    We only flag when BOTH signals agree, to keep false positives down -
    plenty of legitimate camera photos also lack EXIF (stripped by the
    upload pipeline, messaging apps, etc.), so ratio alone or EXIF-absence
    alone is too noisy on its own.
    """
    width, height = ctx.pil_image.size
    ratio = width / height if width < height else height / width  # normalize to <1

    ratio_matches = any(
        abs(ratio - (w / h)) < 0.02 for w, h in settings.screenshot_aspect_ratios
    )

    exif = ctx.pil_image.getexif()
    has_camera_metadata = any(
        exif.get(_EXIF_TAGS.get(tag)) for tag in ("Make", "Model", "FNumber", "ExposureTime")
    )

    is_suspected_screenshot = ratio_matches and not has_camera_metadata

    return CheckResult(
        check_name="screenshot_detection",
        passed=not is_suspected_screenshot,
        severity="warning" if is_suspected_screenshot else "info",
        confidence=0.55 if is_suspected_screenshot else 0.6,  # deliberately low - weak heuristic
        message=(
            "Image resembles a screenshot or re-saved photo (screen-like aspect "
            "ratio + no camera metadata)"
            if is_suspected_screenshot else
            "No screenshot indicators detected"
        ),
        details={
            "aspect_ratio": round(ratio, 3),
            "ratio_matches_screen": ratio_matches,
            "has_camera_metadata": has_camera_metadata,
        },
    )
