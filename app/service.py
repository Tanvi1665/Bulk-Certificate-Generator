"""Business logic: creating a job and processing it.

Flow:  create_job()  -> saves the job + one row per recipient (fast, in the request)
       process_job() -> generates the PDFs (slow, runs in the background)
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.certificate import generate_certificate_pdf
from app.config import settings
from app.database import SessionLocal
from app.models import Certificate, CertificateStatus, Job, JobStatus, utcnow
from app.schemas import FailureOut, JobCounts, JobCreateRequest, JobStatusOut
from app.validation import validate_recipient


def _safe_text(raw, key: str) -> str | None:
    """Keep what the client sent (even for invalid rows) so errors are traceable."""
    if isinstance(raw, dict) and raw.get(key) is not None:
        return str(raw[key])[:255]
    return None


def create_job(db: Session, payload: JobCreateRequest) -> Job:
    """Validate every recipient row and store the job. No PDF work happens here."""
    job = Job(
        course_name=payload.course_name,
        organization=payload.organization,
        issue_date=payload.issue_date,
        total=len(payload.recipients),
    )
    db.add(job)
    db.flush()  # assigns job.id without committing yet

    seen_emails: dict[str, int] = {}  # email -> first row index it appeared at
    for index, raw in enumerate(payload.recipients):
        recipient, error = validate_recipient(raw)

        if recipient is not None:
            key = recipient.email.lower()
            if key in seen_emails:
                error = f"Duplicate email (already used by row {seen_emails[key]} in this request)"
            else:
                seen_emails[key] = index

        if error is None:
            cert = Certificate(
                job_id=job.id, row_index=index,
                recipient_name=recipient.name, recipient_email=recipient.email,
                status=CertificateStatus.PENDING.value,
            )
        else:
            # Invalid rows are recorded as failed; they do NOT stop the other rows.
            cert = Certificate(
                job_id=job.id, row_index=index,
                recipient_name=_safe_text(raw, "name"), recipient_email=_safe_text(raw, "email"),
                status=CertificateStatus.FAILED.value, error_message=f"Validation error: {error}",
            )
        db.add(cert)

    db.commit()
    return job


def _generate_one(db: Session, job: Job, cert: Certificate) -> None:
    """Generate one PDF. Any error is caught so it only fails THIS certificate."""
    relative_path = f"{job.id}/{cert.id}.pdf"
    full_path = settings.storage_dir / relative_path
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        generate_certificate_pdf(
            full_path,
            recipient_name=cert.recipient_name,
            course_name=job.course_name,
            organization=job.organization,
            issue_date=job.issue_date,
            certificate_id=cert.id,
        )
        cert.status = CertificateStatus.SUCCESS.value
        cert.file_path = relative_path
        cert.generated_at = utcnow()
    except Exception as exc:  # noqa: BLE001 - isolating failures is the whole point
        full_path.unlink(missing_ok=True)  # remove a half-written file
        cert.status = CertificateStatus.FAILED.value
        cert.error_message = f"Generation failed: {exc}"
    db.commit()  # commit per certificate so progress is visible while running


def process_job(job_id: str) -> None:
    """Background task. Uses its OWN session because the request's session is closed
    by the time this runs. Safe to call again: it only touches 'pending' rows."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.PROCESSING.value
        job.started_at = utcnow()
        db.commit()

        pending = db.scalars(
            select(Certificate)
            .where(Certificate.job_id == job_id, Certificate.status == CertificateStatus.PENDING.value)
            .order_by(Certificate.row_index)
        ).all()
        for cert in pending:
            _generate_one(db, job, cert)

        counts = _count_by_status(db, job_id)
        succeeded = counts.get(CertificateStatus.SUCCESS.value, 0)
        if succeeded == job.total:
            job.status = JobStatus.COMPLETED.value
        elif succeeded == 0:
            job.status = JobStatus.FAILED.value
        else:
            job.status = JobStatus.COMPLETED_WITH_ERRORS.value
        job.finished_at = utcnow()
        db.commit()


def _count_by_status(db: Session, job_id: str) -> dict[str, int]:
    rows = db.execute(
        select(Certificate.status, func.count()).where(Certificate.job_id == job_id).group_by(Certificate.status)
    ).all()
    return {status: n for status, n in rows}


def as_utc(dt: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; we always store UTC, so tag them as such.
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def get_job_status(db: Session, job: Job) -> JobStatusOut:
    counts = _count_by_status(db, job.id)
    succeeded = counts.get(CertificateStatus.SUCCESS.value, 0)
    failed = counts.get(CertificateStatus.FAILED.value, 0)
    pending = counts.get(CertificateStatus.PENDING.value, 0)
    progress = round((succeeded + failed) / job.total * 100, 1) if job.total else 100.0

    failed_rows = db.scalars(
        select(Certificate)
        .where(Certificate.job_id == job.id, Certificate.status == CertificateStatus.FAILED.value)
        .order_by(Certificate.row_index)
    ).all()

    return JobStatusOut(
        job_id=job.id,
        status=job.status,
        course_name=job.course_name,
        organization=job.organization,
        issue_date=job.issue_date,
        created_at=as_utc(job.created_at),
        started_at=as_utc(job.started_at),
        finished_at=as_utc(job.finished_at),
        progress_percent=progress,
        counts=JobCounts(total=job.total, succeeded=succeeded, failed=failed, pending=pending),
        failures=[
            FailureOut(index=c.row_index, recipient_name=c.recipient_name,
                       recipient_email=c.recipient_email, error=c.error_message or "Unknown error")
            for c in failed_rows
        ],
    )
