from PIL import ExifTags
from app.analysis.types import AnalysisContext, CheckResult

_EXIF_TAGS = {v: k for k, v in ExifTags.TAGS.items()}

# Editing tools whose signature commonly appears in the EXIF "Software" tag.
# Not exhaustive - this is a known-editor allowlist-of-suspects, not a
# forensic tamper detector (see README trade-offs).
_EDITING_SOFTWARE_MARKERS = (
    "photoshop", "gimp", "snapseed", "lightroom", "picsart",
    "facetune", "canva", "pixlr", "affinity photo",
)


def check_metadata_tamper(ctx: AnalysisContext) -> CheckResult:
    """
    Reads the EXIF `Software` tag (if present) and flags known photo-editing
    tool signatures. This is intentionally shallow: it catches the common,
    lazy case (editor writes its name into EXIF and the field isn't
    stripped) and says nothing about pixel-level manipulation. A vehicle
    photo edited in an app that doesn't tag EXIF, or with EXIF stripped
    afterward, will pass this check silently - flagged explicitly in the
    confidence score and the README.
    """
    exif = ctx.pil_image.getexif()
    software = exif.get(_EXIF_TAGS.get("Software"), "")
    software_lower = str(software).lower()

    matched = next((m for m in _EDITING_SOFTWARE_MARKERS if m in software_lower), None)

    return CheckResult(
        check_name="suspicious_editing_heuristic",
        passed=matched is None,
        severity="warning" if matched else "info",
        confidence=0.4 if matched else 0.3,  # low confidence either way - weak signal
        message=(
            f"EXIF Software tag indicates editing tool: '{software}'"
            if matched else
            "No known editing-tool signature found in EXIF (inconclusive - "
            "EXIF is frequently stripped or absent)"
        ),
        details={"exif_software_tag": software or None, "matched_marker": matched},
    )
