"""Job status and progress reporting."""
from app import service
from app.database import SessionLocal
from app.schemas import JobCreateRequest


def test_progress_before_and_after_processing(client, payload_factory):
    """Create the job WITHOUT running the background step to observe 'pending'."""
    with SessionLocal() as db:
        job = service.create_job(db, JobCreateRequest(**payload_factory()))
        job_id = job.id

    before = client.get(f"/jobs/{job_id}").json()
    assert before["status"] == "pending"
    assert before["progress_percent"] == 0.0
    assert before["counts"]["pending"] == 2
    assert before["started_at"] is None and before["finished_at"] is None

    service.process_job(job_id)

    after = client.get(f"/jobs/{job_id}").json()
    assert after["status"] == "completed"
    assert after["progress_percent"] == 100.0
    assert after["started_at"] and after["finished_at"]


def test_progress_percent_counts_failed_rows_as_processed(client, payload_factory):
    recipients = [{"name": "Ok", "email": "ok@example.com"}, {"name": "Bad"}]
    job_id = client.post("/jobs", json=payload_factory(recipients=recipients)).json()["job_id"]
    body = client.get(f"/jobs/{job_id}").json()
    assert body["progress_percent"] == 100.0
    assert body["status"] == "completed_with_errors"


def test_unknown_job_returns_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_reprocessing_a_finished_job_does_not_duplicate_work(client, payload_factory):
    job_id = client.post("/jobs", json=payload_factory()).json()["job_id"]
    service.process_job(job_id)  # run again: nothing is pending, so nothing happens
    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "completed"
    assert body["counts"]["succeeded"] == 2
