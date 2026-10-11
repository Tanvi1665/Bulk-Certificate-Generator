"""Creating a generation job + request-level input validation (whole request rejected)."""


def test_create_job_returns_202_with_job_id(client, payload_factory):
    response = client.post("/jobs", json=payload_factory())
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["counts"]["total"] == 2
    # The response is a snapshot taken BEFORE the background task runs.
    assert body["status"] == "pending"
    assert body["counts"]["pending"] == 2


def test_created_job_finishes_in_background(client, payload_factory):
    job_id = client.post("/jobs", json=payload_factory()).json()["job_id"]
    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "completed"
    assert body["counts"] == {"total": 2, "succeeded": 2, "failed": 0, "pending": 0}


def test_defaults_are_applied_for_optional_fields(client):
    response = client.post(
        "/jobs", json={"course_name": "Intro", "recipients": [{"name": "A B", "email": "a@b.com"}]}
    )
    assert response.status_code == 202
    body = response.json()
    assert body["organization"] == "Example Organization"
    assert body["issue_date"]  # defaults to today


# ----- request-level validation: these reject the entire request with 422 -----
def test_rejects_empty_recipient_list(client, payload_factory):
    assert client.post("/jobs", json=payload_factory(recipients=[])).status_code == 422


def test_rejects_missing_course_name(client, payload_factory):
    payload = payload_factory()
    del payload["course_name"]
    assert client.post("/jobs", json=payload).status_code == 422


def test_rejects_blank_course_name(client, payload_factory):
    assert client.post("/jobs", json=payload_factory(course_name="   ")).status_code == 422


def test_rejects_recipients_that_is_not_a_list(client, payload_factory):
    assert client.post("/jobs", json=payload_factory(recipients="nope")).status_code == 422


def test_rejects_too_many_recipients(client, payload_factory):
    too_many = [{"name": f"P{i}", "email": f"p{i}@example.com"} for i in range(51)]  # limit is 50 in tests
    assert client.post("/jobs", json=payload_factory(recipients=too_many)).status_code == 422


def test_rejects_bad_issue_date(client, payload_factory):
    assert client.post("/jobs", json=payload_factory(issue_date="not-a-date")).status_code == 422
