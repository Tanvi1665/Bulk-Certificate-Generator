"""Database tables: a Job has many Certificates (one per recipient row)."""
import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class JobStatus(str, enum.Enum):
    PENDING = "pending"                          # accepted, not started
    PROCESSING = "processing"                    # background task is running
    COMPLETED = "completed"                      # every certificate succeeded
    COMPLETED_WITH_ERRORS = "completed_with_errors"  # some succeeded, some failed
    FAILED = "failed"                            # nothing succeeded


class CertificateStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    course_name: Mapped[str] = mapped_column(String(150))
    organization: Mapped[str] = mapped_column(String(100))
    issue_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default=JobStatus.PENDING.value, index=True)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    certificates: Mapped[list["Certificate"]] = relationship(back_populates="job")


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (Index("ix_certificates_job_status", "job_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    # Position of this recipient in the submitted list (0-based), so clients can
    # map a failure back to the exact row they sent.
    row_index: Mapped[int] = mapped_column(Integer)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=CertificateStatus.PENDING.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Path relative to STORAGE_DIR (so the storage folder can be moved freely).
    file_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship(back_populates="certificates")
