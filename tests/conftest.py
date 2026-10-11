"""Test setup: every test gets a clean temporary database and storage folder.

The environment variables MUST be set before `app` is imported, because the
database engine is created at import time. This guarantees tests never touch
your real certificates.db or storage/ folder.
"""
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="certgen_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["STORAGE_DIR"] = f"{_TMP}/storage"
os.environ["MAX_RECIPIENTS"] = "50"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(settings.storage_dir, ignore_errors=True)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
def client():
    # Note: the TestClient runs FastAPI background tasks before returning, so
    # after POST /jobs the job is already finished. This keeps tests deterministic.
    return TestClient(app)


def make_payload(recipients=None, **overrides):
    payload = {
        "course_name": "Python Backend Workshop",
        "organization": "Tech Academy",
        "issue_date": "2026-01-15",
        "recipients": recipients
        if recipients is not None
        else [
            {"name": "Asha Patil", "email": "asha@example.com"},
            {"name": "Rohan Mehta", "email": "rohan@example.com"},
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def payload_factory():
    return make_payload
