from dataclasses import dataclass, field
from typing import Any, Optional
import numpy as np
from PIL import Image


@dataclass
class CheckResult:
    check_name: str
    passed: bool                 # True = no issue detected
    severity: str = "info"        # info | warning | critical
    confidence: float = 1.0       # heuristic's self-reported confidence (0-1)
    message: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisContext:
    """Bundles everything a check needs so we only decode the image once."""
    job_id: str
    image_path: str
    cv_image: np.ndarray          # BGR, OpenCV
    pil_image: Image.Image        # for EXIF / format-level metadata
    db_session: Any = None        # used by duplicate_detection to query prior hashes
