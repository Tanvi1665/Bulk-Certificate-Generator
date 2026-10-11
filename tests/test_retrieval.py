"""Listing and downloading generated certificates."""
import io
import zipfile

from app import service
from app.database import SessionLocal
from app.schemas import JobCreateRequest


def _make_job(client, payload_factory, count=3):
    recipients = [{"name": f"Person {i}", "email": f"p{i}@example.com"} for i in range(count)]
    return client.post("/jobs", json=payload_factory(recipients=recipients)).json()["job_id"]


def test_list_certificates(client, payload_factory):
    job_id = _make_job(client, payload_factory)
    body = client.get(f"/jobs/{job_id}/certificates").json()
    assert body["total"] == 3
    assert [i["index"] for i in body["items"]] == [0, 1, 2]
    assert all(i["status"] == "success" and i["download_url"] for i in body["items"])


def test_list_supports_pagination(client, payload_factory):
    job_id = _make_job(client, payload_factory, count=5)
    page = client.get(f"/jobs/{job_id}/certificates", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 5
    assert [i["index"] for i in page["items"]] == [2, 3]


def test_list_can_filter_by_status(client, payload_factory):
    recipients = [{"name": "Good", "email": "g@example.com"}, {"name": "Bad"}]
    job_id = client.post("/jobs", json=payload_factory(recipients=recipients)).json()["job_id"]
    failed = client.get(f"/jobs/{job_id}/certificates", params={"status": "failed"}).json()
    assert failed["total"] == 1 and failed["items"][0]["recipient_name"] == "Bad"
    assert client.get(f"/jobs/{job_id}/certificates", params={"status": "bogus"}).status_code == 422


def test_download_single_certificate(client, payload_factory):
    job_id = _make_job(client, payload_factory)
    item = client.get(f"/jobs/{job_id}/certificates").json()["items"][0]
    response = client.get(item["download_url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "Person_0" in response.headers["content-disposition"]


def test_download_unknown_certificate_or_job_is_404(client, payload_factory):
    job_id = _make_job(client, payload_factory)
    assert client.get(f"/jobs/{job_id}/certificates/nope/download").status_code == 404
    assert client.get("/jobs/nope/certificates").status_code == 404


def test_certificate_cannot_be_fetched_through_another_job(client, payload_factory):
    job_a = _make_job(client, payload_factory)
    job_b = _make_job(client, payload_factory)
    cert_of_a = client.get(f"/jobs/{job_a}/certificates").json()["items"][0]["certificate_id"]
    assert client.get(f"/jobs/{job_b}/certificates/{cert_of_a}/download").status_code == 404


def test_download_all_as_zip(client, payload_factory):
    job_id = _make_job(client, payload_factory)
    response = client.get(f"/jobs/{job_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert archive.namelist() == ["0001_Person_0.pdf", "0002_Person_1.pdf", "0003_Person_2.pdf"]
    assert all(archive.read(n).startswith(b"%PDF") for n in archive.namelist())


def test_zip_is_refused_while_job_is_not_finished(client, payload_factory):
    with SessionLocal() as db:
        job_id = service.create_job(db, JobCreateRequest(**payload_factory())).id
    assert client.get(f"/jobs/{job_id}/download").status_code == 409


def test_zip_is_refused_when_nothing_succeeded(client, payload_factory):
    job_id = client.post("/jobs", json=payload_factory(recipients=[{"name": "x"}])).json()["job_id"]
    assert client.get(f"/jobs/{job_id}/download").status_code == 409
