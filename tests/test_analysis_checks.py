"""
Unit tests for the analysis heuristics. Deliberately DB/broker-free so they
run fast in CI without docker-compose - the checks are pure functions of
(image) -> CheckResult (duplicate_detection is the one exception, tested
separately with a stub session).
"""
import cv2
import numpy as np
from PIL import Image
import pytest

from app.analysis.types import AnalysisContext
from app.analysis.blur import check_blur
from app.analysis.brightness import check_brightness
from app.analysis.dimensions import check_dimensions


def _make_ctx(cv_image: np.ndarray, job_id="test-job") -> AnalysisContext:
    rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb)
    return AnalysisContext(job_id=job_id, image_path="in-memory", cv_image=cv_image, pil_image=pil_image)


def test_blur_detection_flags_uniform_image_as_blurry():
    # A flat, single-color image has zero edge content -> should read as blurry
    flat = np.full((600, 800, 3), 128, dtype=np.uint8)
    result = check_blur(_make_ctx(flat))
    assert result.passed is False
    assert result.severity == "critical"


def test_blur_detection_passes_high_frequency_image():
    # Random noise has lots of high-frequency content -> should NOT be flagged blurry
    rng = np.random.default_rng(42)
    noisy = rng.integers(0, 255, (600, 800, 3), dtype=np.uint8)
    result = check_blur(_make_ctx(noisy))
    assert result.passed is True


def test_brightness_flags_dark_image():
    dark = np.full((600, 800, 3), 10, dtype=np.uint8)
    result = check_brightness(_make_ctx(dark))
    assert result.passed is False
    assert result.details["issue"] == "low_light"


def test_brightness_flags_overexposed_image():
    bright = np.full((600, 800, 3), 250, dtype=np.uint8)
    result = check_brightness(_make_ctx(bright))
    assert result.passed is False
    assert result.details["issue"] == "overexposed"


def test_brightness_passes_mid_range_image():
    mid = np.full((600, 800, 3), 130, dtype=np.uint8)
    result = check_brightness(_make_ctx(mid))
    assert result.passed is True


def test_dimension_validation_flags_small_image():
    small = np.full((100, 100, 3), 128, dtype=np.uint8)
    result = check_dimensions(_make_ctx(small))
    assert result.passed is False


def test_dimension_validation_passes_normal_image():
    normal = np.full((720, 1280, 3), 128, dtype=np.uint8)
    result = check_dimensions(_make_ctx(normal))
    assert result.passed is True


def test_overall_confidence_aggregation():
    from app.analysis.registry import compute_overall_confidence
    from app.analysis.types import CheckResult

    results = [
        CheckResult(check_name="a", passed=True, confidence=0.9),
        CheckResult(check_name="b", passed=False, severity="warning", confidence=0.5),
    ]
    avg, has_issues = compute_overall_confidence(results)
    assert avg == pytest.approx(0.7)
    assert has_issues is True
