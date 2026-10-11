# Bulk Certificate Generator

A backend API that accepts a list of recipients in **one request**, generates a PDF
certificate for each valid recipient from a single predefined template, tracks progress,
and lets the client retrieve the results.

**Stack:** Python 3.10+ · FastAPI · SQLAlchemy 2 · SQLite (any SQL database works) · ReportLab (PDF) · pytest

---

## 1. Setup

```bash
git clone https://github.com/Tanvi1665/Bulk-Certificate-Generator.git
cd Bulk-Certificate-Generator
python -m venv .venv
source .venv/bin/activate            
pip install -r requirements-dev.txt  
```

## 2. Run the application

```bash
uvicorn app.main:app --reload
```

* API: http://127.0.0.1:8000
* Interactive docs (try every endpoint in the browser): http://127.0.0.1:8000/docs

Tables are created automatically on startup. Optional environment variables:

| Variable         | Default                         | Meaning                                  |
|------------------|---------------------------------|------------------------------------------|
| `DATABASE_URL`   | `sqlite:///./certificates.db`   | Any SQLAlchemy URL (e.g. PostgreSQL)     |
| `STORAGE_DIR`    | `./storage`                     | Where generated PDFs are saved           |
| `MAX_RECIPIENTS` | `1000`                          | Max recipients accepted in one request   |

## 3. Run the tests

```bash
pytest -v
```

Tests use a temporary database and folder, so they never touch your real data.

---

## 4. API overview

| Method | Endpoint                                         | Purpose                                      |
|--------|--------------------------------------------------|----------------------------------------------|
| POST   | `/jobs`                                          | Submit a bulk generation request (202)       |
| GET    | `/jobs/{job_id}`                                 | Status, progress, counts, list of failures   |
| GET    | `/jobs/{job_id}/certificates`                    | List certificates (`?status=`, `limit`, `offset`) |
| GET    | `/jobs/{job_id}/certificates/{cert_id}/download` | Download one certificate (PDF)               |
| GET    | `/jobs/{job_id}/download`                        | Download all successful certificates (ZIP)   |

### Submit a request

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "course_name": "Python Backend Workshop",
    "organization": "Tech Academy",
    "issue_date": "2026-01-15",
    "recipients": [
      {"name": "Asha Patil",  "email": "asha@example.com"},
      {"name": "Rohan Mehta", "email": "rohan@example.com"},
      {"name": "Broken Row"}
    ]
  }'
```

`organization` and `issue_date` are optional (defaults: "Example Organization", today).
Response (`202 Accepted`, returned immediately):

```json
{
  "job_id": "3f0c...-uuid",
  "status": "pending",
  "progress_percent": 33.3,
  "counts": {"total": 3, "succeeded": 0, "failed": 1, "pending": 2},
  "failures": [
    {"index": 2, "recipient_name": "Broken Row", "recipient_email": null,
     "error": "Validation error: email: Field required"}
  ],
  "...": "..."
}
```

### Check progress

```bash
curl http://127.0.0.1:8000/jobs/<job_id>
```

Job `status` values: `pending` → `processing` → one of
`completed` (all succeeded) · `completed_with_errors` (some failed) · `failed` (none succeeded).
`failures[].index` is the position of the row in the `recipients` array you sent (0-based).

### Retrieve certificates

```bash
# list (optionally only failed ones)
curl "http://127.0.0.1:8000/jobs/<job_id>/certificates?status=success"

# one PDF  (use the download_url from the list)
curl -o asha.pdf http://127.0.0.1:8000/jobs/<job_id>/certificates/<cert_id>/download

# everything as a ZIP
curl -o certificates.zip http://127.0.0.1:8000/jobs/<job_id>/download
```

### Error responses

| Code | When                                                                              |
|------|-----------------------------------------------------------------------------------|
| 422  | Request-level problem: no recipients, too many, missing `course_name`, bad date   |
| 404  | Unknown job or certificate                                                        |
| 409  | Certificate failed / not generated; ZIP requested while job still running or empty |

---

## 5. Design decisions

**Processing model: background task.** `POST /jobs` validates and stores everything, then returns
`202 Accepted` right away; PDFs are generated afterwards by a FastAPI `BackgroundTask`, and the client polls
`GET /jobs/{id}`. Generating hundreds of PDFs inside the request would make the HTTP call slow and risk
client/proxy timeouts. A background task needs no extra infrastructure (no Redis/worker), which keeps
the project simple to run and review. *Trade-off:* it runs inside the web process, so a server restart
mid-job leaves that job in `processing`. In production I would swap it for a task queue (Celery/RQ);
only the one line that schedules `process_job` would change, because the logic is already in a separate function.

**Two levels of validation.**
1. *Request level* (Pydantic → HTTP 422): problems that make the whole request meaningless — empty list,
   more than `MAX_RECIPIENTS`, missing course name.
2. *Row level*: each recipient is checked individually (name present/≤100 chars/printable/Latin-1; valid email;
   no duplicate email in the request). A bad row is stored as `failed` with a readable error and the rest continue.
   This satisfies "one bad record must not block the others".

**Failure isolation.** Each certificate is generated inside its own `try/except` and committed on its own.
A crash only marks that one certificate `failed` (error message saved, half-written file deleted).

**Progress is computed, not stored.** Counts come from a `GROUP BY status` query on the certificates table,
so they can never drift out of sync with reality. Each certificate is committed as it finishes,
so progress is visible live.

**Data model.** `jobs` (1) → `certificates` (many), one row per submitted recipient, including invalid ones,
with `row_index` so clients can map results back to their input.

**Certificate template.** A single landscape-A4 PDF layout in `app/certificate.py` (ReportLab, pure Python,
no system dependencies). Long names/course titles automatically shrink to fit. Every certificate carries a unique ID.

**Storage.** PDFs are saved to `STORAGE_DIR/<job_id>/<certificate_id>.pdf`; the DB stores only the relative path.
File names come from server-generated UUIDs, never from user input (no path-traversal risk).

**Idempotent processing.** `process_job` only touches `pending` rows, so running it twice cannot create duplicates.

### Known limitations / possible improvements
* Names must be Latin-1 (built-in PDF fonts). Supporting e.g. Devanagari needs registering a Unicode TTF font.
* No authentication, rate limiting, or per-user ownership of jobs.
* Local-disk storage; production would use S3/object storage.
* Jobs interrupted by a restart are not resumed automatically (a startup hook could re-run `process_job` for jobs left in `processing`).
* No retry endpoint for failed certificates.

## 6. Project structure

```
app/
  main.py          HTTP routes only
  service.py       create_job() and process_job(): the business logic
  certificate.py   PDF template / generation
  validation.py    per-recipient validation rules
  schemas.py       request/response models
  models.py        Job and Certificate tables
  database.py      engine and sessions
  config.py        settings from environment variables
tests/             pytest suite (42 tests)
```
