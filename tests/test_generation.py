"""The actual certificate PDF generation."""
from datetime import date

from app.certificate import generate_certificate_pdf
from app.config import settings


def _generate(path, **overrides):
    args = dict(
        recipient_name="Asha Patil",
        course_name="Python Backend Workshop",
        organization="Tech Academy",
        issue_date=date(2026, 1, 15),
        certificate_id="abc-123",
    )
    args.update(overrides)
    generate_certificate_pdf(path, **args)


def test_generates_a_valid_pdf_with_recipient_details(tmp_path):
    out = tmp_path / "cert.pdf"
    _generate(out)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    for expected in (b"Asha Patil", b"Python Backend Workshop", b"TECH ACADEMY", b"15 January 2026", b"abc-123"):
        assert expected in data


def test_very_long_name_does_not_crash(tmp_path):
    out = tmp_path / "long.pdf"
    _generate(out, recipient_name="W" * 100)
    assert out.stat().st_size > 0


def test_accented_latin_names_work(tmp_path):
    out = tmp_path / "accent.pdf"
    _generate(out, recipient_name="José Muñoz")
    assert out.read_bytes().startswith(b"%PDF")


def test_job_creates_one_pdf_file_per_valid_recipient(client, payload_factory):
    job_id = client.post("/jobs", json=payload_factory()).json()["job_id"]
    files = list((settings.storage_dir / job_id).glob("*.pdf"))
    assert len(files) == 2
    assert all(f.read_bytes().startswith(b"%PDF") for f in files)


def test_each_certificate_contains_its_own_recipient_name(client, payload_factory):
    job_id = client.post("/jobs", json=payload_factory()).json()["job_id"]
    items = client.get(f"/jobs/{job_id}/certificates").json()["items"]
    for item in items:
        pdf = client.get(item["download_url"]).content
        assert item["recipient_name"].encode() in pdf
