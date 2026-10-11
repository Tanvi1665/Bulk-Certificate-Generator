"""Row-level validation: bad rows fail individually, good rows still succeed."""
from app.validation import validate_recipient


# ----- unit tests of the validator itself -----
def test_valid_recipient_is_cleaned():
    recipient, error = validate_recipient({"name": "  Asha Patil ", "email": "asha@example.com"})
    assert error is None
    assert recipient.name == "Asha Patil"  # whitespace stripped


def test_missing_fields_are_reported():
    recipient, error = validate_recipient({})
    assert recipient is None
    assert "name" in error and "email" in error


def test_invalid_email_is_reported():
    _, error = validate_recipient({"name": "Asha", "email": "not-an-email"})
    assert "email" in error


def test_name_must_be_a_string_and_not_blank():
    assert validate_recipient({"name": 123, "email": "a@b.com"})[0] is None
    assert validate_recipient({"name": "   ", "email": "a@b.com"})[0] is None


def test_name_too_long_is_rejected():
    assert validate_recipient({"name": "x" * 101, "email": "a@b.com"})[0] is None


def test_unsupported_characters_are_rejected():
    _, error = validate_recipient({"name": "प्रिया", "email": "a@b.com"})
    assert "not supported" in error


def test_row_that_is_not_an_object():
    recipient, error = validate_recipient("just a string")
    assert recipient is None and "object" in error


# ----- API-level behaviour -----
def test_invalid_rows_fail_but_valid_rows_still_succeed(client, payload_factory):
    recipients = [
        {"name": "Good One", "email": "good1@example.com"},
        {"name": "No Email"},                       # index 1: missing email
        {"name": "Bad Email", "email": "oops"},      # index 2: bad email
        "garbage",                                   # index 3: not an object
        {"name": "Good Two", "email": "good2@example.com"},
    ]
    job_id = client.post("/jobs", json=payload_factory(recipients=recipients)).json()["job_id"]
    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "completed_with_errors"
    assert body["counts"] == {"total": 5, "succeeded": 2, "failed": 3, "pending": 0}
    assert [f["index"] for f in body["failures"]] == [1, 2, 3]
    assert all(f["error"].startswith("Validation error") for f in body["failures"])
    assert body["failures"][0]["recipient_name"] == "No Email"


def test_duplicate_email_in_same_request_is_rejected(client, payload_factory):
    recipients = [
        {"name": "First", "email": "same@example.com"},
        {"name": "Second", "email": "SAME@example.com"},  # case-insensitive duplicate
    ]
    job_id = client.post("/jobs", json=payload_factory(recipients=recipients)).json()["job_id"]
    body = client.get(f"/jobs/{job_id}").json()
    assert body["counts"]["succeeded"] == 1
    assert body["failures"][0]["index"] == 1
    assert "Duplicate" in body["failures"][0]["error"]


def test_job_where_every_row_is_invalid_is_failed(client, payload_factory):
    job_id = client.post("/jobs", json=payload_factory(recipients=[{"name": "x"}, {}])).json()["job_id"]
    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "failed"
    assert body["progress_percent"] == 100.0
    assert body["counts"]["succeeded"] == 0
