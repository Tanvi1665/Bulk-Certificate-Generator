"""One certificate failing during generation must not stop the others."""
import pytest

from app import service
from app.config import settings


@pytest.fixture
def break_generation_for(monkeypatch):
    """Make the PDF generator raise for one specific recipient name."""
    real_generate = service.generate_certificate_pdf

    def install(bad_name, write_partial_file=False):
        def fake(path, **kwargs):
            if kwargs["recipient_name"] == bad_name:
                if write_partial_file:
                    path.write_bytes(b"%PDF-half-written")
                raise RuntimeError("disk exploded")
            return real_generate(path, **kwargs)

        monkeypatch.setattr(service, "generate_certificate_pdf", fake)

    return install


def _recipients():
    return [
        {"name": "First Person", "email": "first@example.com"},
        {"name": "Broken Person", "email": "broken@example.com"},
        {"name": "Third Person", "email": "third@example.com"},
    ]


def test_one_failure_does_not_block_other_certificates(client, payload_factory, break_generation_for):
    break_generation_for("Broken Person")
    job_id = client.post("/jobs", json=payload_factory(recipients=_recipients())).json()["job_id"]
    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "completed_with_errors"
    assert body["counts"] == {"total": 3, "succeeded": 2, "failed": 1, "pending": 0}
    failure = body["failures"][0]
    assert failure["index"] == 1
    assert failure["recipient_name"] == "Broken Person"
    assert "disk exploded" in failure["error"]
    assert failure["error"].startswith("Generation failed")


def test_certificates_after_the_failure_are_still_generated(client, payload_factory, break_generation_for):
    break_generation_for("Broken Person")
    job_id = client.post("/jobs", json=payload_factory(recipients=_recipients())).json()["job_id"]
    items = client.get(f"/jobs/{job_id}/certificates").json()["items"]
    assert [i["status"] for i in items] == ["success", "failed", "success"]


def test_partial_file_is_cleaned_up_after_failure(client, payload_factory, break_generation_for):
    break_generation_for("Broken Person", write_partial_file=True)
    job_id = client.post("/jobs", json=payload_factory(recipients=_recipients())).json()["job_id"]
    assert len(list((settings.storage_dir / job_id).glob("*.pdf"))) == 2  # no leftover half file


def test_failed_certificate_cannot_be_downloaded(client, payload_factory, break_generation_for):
    break_generation_for("Broken Person")
    job_id = client.post("/jobs", json=payload_factory(recipients=_recipients())).json()["job_id"]
    failed = client.get(f"/jobs/{job_id}/certificates", params={"status": "failed"}).json()["items"][0]
    assert failed["download_url"] is None
    response = client.get(f"/jobs/{job_id}/certificates/{failed['certificate_id']}/download")
    assert response.status_code == 409


def test_job_is_failed_when_every_generation_fails(client, payload_factory, monkeypatch):
    def always_fail(path, **kwargs):
        raise RuntimeError("nothing works")

    monkeypatch.setattr(service, "generate_certificate_pdf", always_fail)
    job_id = client.post("/jobs", json=payload_factory()).json()["job_id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "failed"
