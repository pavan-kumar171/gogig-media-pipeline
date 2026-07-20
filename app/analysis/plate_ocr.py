import re
import cv2
import pytesseract
from app.analysis.types import AnalysisContext, CheckResult

# Indian plate format: 2 letters (state code) + 1-2 digits (RTO code) +
# 1-3 letters (series) + 4 digits (unique number), e.g. "KA19EF1234".
# We normalize OCR output (strip spaces/hyphens, uppercase) before matching
# since real plates are photographed with varying spacing/fonts.
_PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")


def _preprocess_for_ocr(cv_image):
    """Grayscale + adaptive threshold generally improves Tesseract accuracy
    on plate-style high-contrast text vs feeding it the raw photo."""
    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    return thresh


def check_plate_ocr(ctx: AnalysisContext) -> CheckResult:
    """
    Runs Tesseract OCR across the whole frame (no plate-localization model
    in scope for this assignment - see README) and searches the extracted
    text for a substring matching the Indian plate format.

    This is a deliberately blunt approach: whole-image OCR instead of first
    cropping to a detected plate region. It works when the plate text is
    reasonably legible and un-occluded, and fails when the plate is small,
    angled, or plate detection would be needed first. That trade-off is
    called out explicitly rather than hidden behind a high confidence score.
    """
    try:
        processed = _preprocess_for_ocr(ctx.cv_image)
        raw_text = pytesseract.image_to_string(processed, config="--psm 11")
    except pytesseract.TesseractNotFoundError:
        return CheckResult(
            check_name="plate_format_validation",
            passed=True,
            severity="info",
            confidence=0.0,
            message="Tesseract binary not available - OCR skipped (see README setup)",
            details={"error": "tesseract_not_found"},
        )

    candidates = re.split(r"[^A-Za-z0-9]+", raw_text.upper())
    matches = [c for c in candidates if _PLATE_REGEX.match(c)]

    if matches:
        return CheckResult(
            check_name="plate_format_validation",
            passed=True,
            confidence=0.7,
            message=f"Valid-format plate text detected: {matches[0]}",
            details={"matched_plate": matches[0], "all_matches": matches, "raw_ocr_text": raw_text.strip()[:300]},
        )

    return CheckResult(
        check_name="plate_format_validation",
        passed=False,
        severity="warning",
        confidence=0.45,  # low - absence of a match could mean bad OCR, not bad plate
        message="No text matching Indian plate format found in image",
        details={"raw_ocr_text": raw_text.strip()[:300]},
    )
