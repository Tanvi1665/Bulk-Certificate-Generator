"""HTTP layer: routes only. Business logic lives in service.py."""
import io
import re
import zipfile
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import service
from app.config import settings
from app.database import Base, engine, get_db
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import CertificateListOut, CertificateOut, JobCreateRequest, JobStatusOut
from app.service import as_utc


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)  # create tables on startup if missing
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Bulk Certificate Generator", version="1.0.0", lifespan=lifespan)


# ---------- helpers ----------
def _get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _slug(text: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_") or "certificate"


def _to_out(cert: Certificate) -> CertificateOut:
    ok = cert.status == CertificateStatus.SUCCESS.value
    return CertificateOut(
        certificate_id=cert.id,
        index=cert.row_index,
        recipient_name=cert.recipient_name,
        recipient_email=cert.recipient_email,
        status=cert.status,
        error=cert.error_message,
        generated_at=as_utc(cert.generated_at),
        download_url=f"/jobs/{cert.job_id}/certificates/{cert.id}/download" if ok else None,
    )


# ---------- routes ----------
@app.post("/jobs", response_model=JobStatusOut, status_code=202, summary="Submit a bulk generation job")
def create_job(payload: JobCreateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Validates every row, stores the job, and returns immediately (202 Accepted).
    PDF generation continues in the background; poll GET /jobs/{job_id}."""
    job = service.create_job(db, payload)
    background_tasks.add_task(service.process_job, job.id)
    return service.get_job_status(db, job)


@app.get("/jobs/{job_id}", response_model=JobStatusOut, summary="Job status and progress")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return service.get_job_status(db, _get_job_or_404(db, job_id))


@app.get("/jobs/{job_id}/certificates", response_model=CertificateListOut, summary="List certificates of a job")
def list_certificates(
    job_id: str,
    status: CertificateStatus | None = Query(None, description="Filter by certificate status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _get_job_or_404(db, job_id)
    query = select(Certificate).where(Certificate.job_id == job_id)
    if status is not None:
        query = query.where(Certificate.status == status.value)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Certificate.row_index).limit(limit).offset(offset)).all()
    return CertificateListOut(total=total, limit=limit, offset=offset, items=[_to_out(c) for c in rows])


@app.get("/jobs/{job_id}/certificates/{certificate_id}/download", summary="Download one certificate (PDF)")
def download_certificate(job_id: str, certificate_id: str, db: Session = Depends(get_db)):
    _get_job_or_404(db, job_id)
    cert = db.scalar(select(Certificate).where(Certificate.id == certificate_id, Certificate.job_id == job_id))
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.status != CertificateStatus.SUCCESS.value:
        raise HTTPException(status_code=409, detail=f"Certificate is not available (status: {cert.status})")
    path = settings.storage_dir / cert.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Certificate file is missing from storage")
    return FileResponse(path, media_type="application/pdf", filename=f"certificate_{_slug(cert.recipient_name)}.pdf")


@app.get("/jobs/{job_id}/download", summary="Download all successful certificates as a ZIP")
def download_all(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    if job.status in (JobStatus.PENDING.value, JobStatus.PROCESSING.value):
        raise HTTPException(status_code=409, detail=f"Job is still {job.status}; try again when it finishes")
    certs = db.scalars(
        select(Certificate)
        .where(Certificate.job_id == job_id, Certificate.status == CertificateStatus.SUCCESS.value)
        .order_by(Certificate.row_index)
    ).all()
    if not certs:
        raise HTTPException(status_code=409, detail="No certificates were generated for this job")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for cert in certs:
            path = settings.storage_dir / cert.file_path
            if path.is_file():
                archive.write(path, arcname=f"{cert.row_index + 1:04d}_{_slug(cert.recipient_name)}.pdf")
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="certificates_{job_id}.zip"'},
    )
