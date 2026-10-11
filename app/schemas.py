"""Request / response shapes of the API."""
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings
from app.validation import ensure_supported_text


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    course_name: str = Field(min_length=1, max_length=150, examples=["Python Backend Workshop"])
    organization: str = Field(default="Example Organization", min_length=1, max_length=100)
    issue_date: date = Field(default_factory=date.today)
    # Items are deliberately `Any`: each row is validated individually later,
    # so one bad row does not reject the whole request.
    recipients: list[Any] = Field(min_length=1, max_length=settings.max_recipients)

    @field_validator("course_name", "organization")
    @classmethod
    def _supported(cls, v: str) -> str:
        return ensure_supported_text(v)


class JobCounts(BaseModel):
    total: int
    succeeded: int
    failed: int
    pending: int


class FailureOut(BaseModel):
    index: int
    recipient_name: str | None
    recipient_email: str | None
    error: str


class JobStatusOut(BaseModel):
    job_id: str
    status: str
    course_name: str
    organization: str
    issue_date: date
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    progress_percent: float
    counts: JobCounts
    failures: list[FailureOut]


class CertificateOut(BaseModel):
    certificate_id: str
    index: int
    recipient_name: str | None
    recipient_email: str | None
    status: str
    error: str | None
    generated_at: datetime | None
    download_url: str | None


class CertificateListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CertificateOut]
