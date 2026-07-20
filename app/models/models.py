import uuid
import enum
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Float, Boolean, Integer, Enum, JSON, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImageJob(Base):
    """
    One row per uploaded image. This is the aggregate root - status lives
    here so a single indexed lookup answers "what's the state of job X".
    Analysis detail is normalized into AnalysisCheck (1:N) rather than a
    single blob column, so individual checks are queryable/reportable
    (e.g. "how many jobs failed duplicate detection this week").
    """
    __tablename__ = "image_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)

    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING, index=True)
    failure_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    # perceptual hash stored on the job itself so duplicate-detection can do
    # a cheap lookup against prior jobs without re-reading every image file
    perceptual_hash = Column(String, nullable=True, index=True)

    overall_confidence = Column(Float, nullable=True)  # 0-1, aggregated from checks
    has_issues = Column(Boolean, nullable=True)         # convenience flag for quick filtering

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at = Column(DateTime(timezone=True), nullable=True)

    checks = relationship("AnalysisCheck", back_populates="job", cascade="all, delete-orphan")


class AnalysisCheck(Base):
    """
    One row per heuristic check run against a job (blur, brightness,
    duplicate, ocr_plate, screenshot, dimensions, ...). Storing checks
    individually (vs one JSON blob) makes each check independently
    auditable and lets us add new checks without a schema migration
    touching existing data.
    """
    __tablename__ = "analysis_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("image_jobs.id"), nullable=False, index=True)

    check_name = Column(String, nullable=False)   # e.g. "blur_detection"
    passed = Column(Boolean, nullable=False)       # True = no issue found
    severity = Column(String, nullable=False, default="info")  # info | warning | critical
    confidence = Column(Float, nullable=False, default=1.0)     # heuristic's self-reported confidence
    message = Column(String, nullable=True)         # human-readable summary
    details = Column(JSON, nullable=True)            # raw metrics (e.g. {"laplacian_variance": 42.1})

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("ImageJob", back_populates="checks")
