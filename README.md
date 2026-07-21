# goGig Intelligent Media Processing Pipeline

An async backend that accepts uploaded vehicle images, queues them for background
analysis, and reports structured, confidence-scored findings on common field-photo
problems (blur, poor lighting, duplicates, screenshots, tampering signs, invalid
plate format).

Built for the Backend + AI Engineering take-home assignment.

---

## Live Deployment

- **Live API:** https://gogig-media-pipeline.onrender.com/docs
- **Interactive API docs (Swagger UI):** https://gogig-media-pipeline.onrender.com/docs
- **Repository:** https://github.com/pavan-kumar171/gogig-media-pipeline

This runs on Render's free tier, which spins the service down after ~15
minutes of inactivity. **The first request after idle time can take
30-60 seconds** to respond while it wakes back up - this is a hosting-tier
characteristic, not an application bug. Subsequent requests are fast.

Note: on this free-tier deployment, the API and worker run inside one
container (see `entrypoint.sh`) instead of the two separate containers
`docker-compose.yml` uses locally - this is a hosting-cost trade-off,
explained in full under Trade-offs below.

---

## Architecture

### Service flow

Client
│ POST /api/v1/uploads (multipart file)
▼
FastAPI (api process)
│ 1. validate extension/size
│ 2. save file to disk, get job_id
│ 3. INSERT image_jobs row (status=pending)
│ 4. enqueue Celery task ──────────────┐
│ 5. return 202 + job_id immediately │
▼ ▼
Client polls: Redis (broker)
GET /jobs/{id}/status │
GET /jobs/{id}/results ▼
Celery worker (separate process)
1. status -> processing
2. decode image once (OpenCV + PIL)
3. run 7 independent checks
4. persist AnalysisCheck rows
5. status -> completed | failed


The API process and the worker process never share memory or a DB session -
they're separate OS processes (and in Docker, separate containers) that only
communicate through Postgres (state) and Redis (queue + task metadata). This
is deliberate: it's the same shape you'd deploy at real scale, just with one
replica per role instead of many.

### Processing flow (inside the worker)

Each job goes through: `pending -> processing -> completed | failed`. The
image is decoded **once** (`app/analysis/registry.py:build_context`) into an
`AnalysisContext` shared read-only across all 7 checks, rather than each
check re-opening the file. The checks are:

| Check | What it does |
|---|---|
| `blur_detection` | Variance of Laplacian - low variance = few edges = blurry |
| `brightness_analysis` | Mean pixel intensity - flags too-dark or overexposed |
| `dimension_validation` | Rejects images below a minimum resolution |
| `duplicate_detection` | Perceptual hash (pHash), compared against every prior job's stored hash |
| `screenshot_detection` | Screen-like aspect ratio **and** missing camera EXIF (both signals required) |
| `suspicious_editing_heuristic` | EXIF `Software` tag checked against known editor names |
| `plate_format_validation` | Tesseract OCR over the full frame, regex-matched against Indian plate format |

Every check returns a `CheckResult` independently (`app/analysis/types.py`).
One check throwing an exception does **not** kill the others - `run_all_checks`
catches per-check exceptions and turns them into a `critical`-severity result
so the failure is visible in the report instead of silently dropped or
crashing the whole job.

`overall_confidence` is the mean of each check's self-reported confidence;
`has_issues` is true if any check with severity `warning`/`critical` failed.
This is intentionally simple - see Trade-offs.

### Queue strategy

**Celery + Redis**, chosen over an in-memory queue or SQS:

- **Why not in-memory:** a job enqueued in-process is lost if the API
  process restarts. Assignment explicitly says async processing "must"
  happen in the background, and I wanted that to survive a restart, not
  just look async.
- **Why not SQS:** no AWS account requirement, and Celery+Redis is fully
  reproducible with `docker-compose up`, which matters for someone
  reviewing this on their own machine in 48 hours.
- **Why Celery specifically (vs BullMQ, given this ended up Python):**
  it's the standard Python-ecosystem choice, has built-in retry/backoff,
  `task_acks_late` (task is only ack'd after it completes, so a worker
  crash mid-processing causes redelivery, not silent loss), and a hard
  time limit (`task_time_limit=120s`) so a stuck OCR call can't wedge a
  worker forever.

### Data model

Two tables, intentionally normalized rather than one JSON blob:

- **`image_jobs`** - one row per upload. Holds status, timestamps, the
  perceptual hash (indexed, so duplicate lookups don't need to re-read
  every prior file), retry count, and aggregate confidence/has_issues.
- **`analysis_checks`** - one row per check per job (1:N). Normalizing
  this means individual checks are queryable ("how many jobs failed
  duplicate detection this week") and adding a new check later doesn't
  touch the schema of existing rows - it's just a new `check_name` value.

### Major design decisions

1. **Local disk storage, not S3.** Storage sits behind a tiny `LocalStorage`
   class (`app/storage/local_storage.py`) specifically so swapping in S3
   later is a one-file change. For a 48-hour take-home with a reviewer
   running this locally, adding real cloud storage credentials would add
   setup friction without adding signal about my engineering judgment.
2. **Whole-frame OCR, not plate-region detection.** A production system
   would run a plate-localization model (or at least edge/contour-based
   plate cropping) before OCR. I chose whole-frame OCR because it's
   honest about what it can and can't do (see the docstring in
   `plate_ocr.py`) rather than pretending a heavier pipeline exists.
3. **Confidence scores are heuristic self-reports, not calibrated
   probabilities.** Each check assigns its own confidence based on how
   far a metric sits from its threshold. This is explicitly *not* a
   trained/calibrated model output - it's a way to communicate "how sure
   is this specific heuristic" rather than presenting binary pass/fail as
   if it were ground truth. Documented per-check in code comments.

---

## AI Usage Disclosure (Mandatory)

I built this collaborating with Claude (Claude Sonnet 4.6, via Claude.ai)
inside a sandboxed dev environment where I could actually run the code,
not just generate it.

**Where AI helped:**
- Scaffolding the FastAPI/Celery/SQLAlchemy project structure and
  boilerplate (routes, models, Celery task wiring) faster than typing it
  by hand.
- Drafting the 7 heuristic checks (blur/brightness/duplicate/screenshot/
  metadata/plate OCR) with initial threshold values.
- Writing the docstrings that explain *why* each heuristic works the way
  it does, and the trade-offs section below.
- Generating unit tests for the pure-function checks.

**Where AI output was wrong, and how I caught it:**
- The initial `screenshot_detection` heuristic included **4:3 (3, 4)** in
  its list of "screen-like" aspect ratios. 4:3 is also the standard
  camera sensor ratio, so this made the check flag almost every normal
  photo as a suspected screenshot. This wasn't caught by reading the
  code - it only showed up when I actually ran the pipeline end-to-end
  against synthetic test images and looked at the output: every single
  seeded image (including plain camera-ratio photos) was failing
  `screenshot_detection`. I removed 4:3 from the ratio list and
  re-verified with a direct unit check that a standard 1024x768 image no
  longer trips the heuristic. This is exactly the kind of bug that looks
  fine on read-through and only surfaces under actual execution - which
  is why I ran a live end-to-end test (uploaded a real file through the
  API, polled results, inspected the JSON) rather than trusting generated
  code on sight.
- Celery's `autoretry_for` + manual `retries >= max_retries` check in
  `process_image.py` needed a second look: the naive version would have
  either double-marked jobs as failed or swallowed the final failure
  reason. I validated the retry/failure-persistence logic by reading
  through the state transitions manually rather than assuming the
  AI-suggested retry pattern was correct out of the box.

**How I validated AI-generated code, generally:**
- Ran the actual API (`uvicorn`) and worker (`celery`) against real
  Postgres/Redis instances, not just imported the modules.
- Uploaded real files through `curl`, polled `/status` and `/results`,
  and read the actual JSON output for each of the 7 checks rather than
  assuming they worked because the code compiled.
- Wrote and ran the `pytest` suite (`tests/test_analysis_checks.py`)
  against deliberately constructed edge-case inputs (flat gray image,
  random noise, all-black, all-white) to confirm each heuristic's
  pass/fail boundary actually behaves as documented, not just "runs
  without throwing."
- Fixed the aspect-ratio bug above based on that live output, not on
  code review alone.
- Ran all 3 official sample images provided for grading through the
  live deployed API and inspected the raw JSON for each, which is what
  surfaced the plate-OCR and screenshot-detection findings documented
  under Trade-offs below.

**Where I used AI strategically vs. blindly:** I treated AI as a fast way
to get a reasonable first draft of routine, well-understood patterns
(REST CRUD, Celery task wiring, ORM models) so I could spend my own
attention on the parts that actually needed engineering judgment: which
heuristics to combine and why, what confidence scores mean, how failure
states should be surfaced, and - critically - verifying the thing
actually works by running it, not just reading it.

---

## Trade-offs

**What I intentionally simplified:**
- Whole-frame OCR instead of plate-region detection (see above).
- `overall_confidence` is an unweighted mean across checks. A real system
  would weight checks by how reliable they are (blur/dimensions are near-
  deterministic; screenshot/tamper heuristics are weak signals) - I kept
  it simple and documented the weak checks' low self-reported confidence
  instead of building a weighting model for a 48-hour assignment.
- No plate-region cropping means OCR accuracy on real, angled, small
  plates will be noticeably worse than on a clean, cropped plate photo.
  This was confirmed against all 3 of the official sample images
  provided for grading: in every case, Tesseract read the auto's ad
  banner or nearby background text instead of the plate itself,
  producing a consistent, reproducible failure mode rather than an
  occasional miss.
- `screenshot_detection`'s reliance on aspect ratio + missing EXIF also
  produced false positives on 2 of the 3 official sample images, both
  shot at the common 720x1280 portrait ratio with EXIF stripped by
  sharing apps (WhatsApp). This is the same underlying weakness as the
  4:3 bug caught during development (see AI Usage Disclosure) - the
  fix in both cases is the same: this heuristic is a weak signal and
  should be weighted low or gated behind a stronger indicator (e.g.
  actual on-screen UI artifacts), not aspect ratio alone.
- Local disk storage instead of S3/GCS (see Architecture).
- No auth/rate limiting on the API - out of scope per the assignment's
  focus on system design over production hardening, but see below.
- **The hosted demo link runs API + worker inside one container**
  (`entrypoint.sh`), not as separate services as `docker-compose.yml`
  does locally. This is purely a free-hosting-tier constraint (most free
  tiers give one always-on process; a second worker service costs money)
  - not a design choice. It means the API and worker share CPU/memory and
    can't be scaled or restarted independently on the hosted demo, which
    docker-compose.yml (the "real" architecture) doesn't have. Documented
    in `entrypoint.sh` itself as well.

**What I'd improve with more time:**
- A plate-localization step (classical CV contour detection, or a small
  detection model) before OCR, to make `plate_format_validation`
  meaningfully more accurate - the highest-priority fix given it failed
  consistently across all 3 official sample images.
- Weighted/learned confidence aggregation instead of a flat mean.
- Duplicate detection is currently O(n) against every prior job's hash
  (`app/analysis/duplicate.py`) - fine at assignment scale, but at real
  volume this needs an indexed nearest-neighbor structure (e.g. an
  LSH/vector index) instead of a linear scan.
- API-level authentication and per-client rate limiting.
- A `/jobs` listing endpoint with pagination/filtering (only single-job
  status/results are implemented, per the assignment's minimum scope).
- Structured JSON logging + a correlation ID threaded from the upload
  request through to the worker log lines, for real observability.

**Scalability concerns:**
- Celery workers scale horizontally trivially (just run more worker
  containers) since they're stateless besides their DB/Redis
  connections - `worker_prefetch_multiplier=1` in `celery_app.py` is set
  so tasks are distributed fairly across workers instead of one worker
  hoarding a batch.
- The real bottleneck at scale is `duplicate_detection`'s linear scan
  over all prior hashes, called out above.
- Local disk storage doesn't scale across multiple worker/API replicas
  on different hosts - this is the concrete reason the storage layer is
  behind an interface, so it's a real blocker to flag rather than a
  hypothetical one.

**Failure handling concerns:**
- Celery `autoretry_for` + `retry_backoff` retries transient failures
  (e.g. a flaky decode) up to `max_task_retries` (3) with exponential
  backoff before marking the job `failed` with a stored reason,
  queryable via `/jobs/{id}/status`.
- `task_acks_late=True` means a worker that crashes mid-task doesn't lose
  the task - Redis redelivers it to another worker.
- What's **not** handled: if enqueueing to Redis itself fails right after
  the DB commit (`app/api/routes.py`), the job row exists but never gets
  picked up - it's stuck at `pending` forever. A production system needs
  a reconciler sweeping jobs `pending` longer than N minutes and
  re-enqueuing them. Flagged in code comments, not implemented, given
  the assignment's time box.

---

## Running Instructions

### Option A: Docker Compose (recommended, one command)

```bash
docker-compose up --build
```

This starts Postgres, Redis, the API (port 8000), and a Celery worker.
Tables are created automatically on API startup.

API docs: http://localhost:8000/docs

### Option B: Run locally without Docker

Requires: Python 3.12+, PostgreSQL, Redis, and the `tesseract-ocr` system
package (`apt install tesseract-ocr` / `brew install tesseract`).

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # edit if your Postgres/Redis aren't on localhost defaults

# create the database (adjust user/db name to match .env)
createuser gogig && createdb gogig_pipeline -O gogig

# terminal 1 - API (creates tables on startup)
uvicorn app.main:app --reload

# terminal 2 - worker
celery -A app.tasks.celery_app worker --loglevel=info
```

### Seed sample data

With the stack running:

```bash
python scripts/seed.py
```

Uploads 5 synthetic test images (sharp, blurry, duplicate, dark,
screenshot-shaped) and prints each one's findings once processed - a fast
way to see all 7 checks produce real output without needing your own
vehicle photos.

### Run tests

```bash
pytest tests/ -v
```

Unit tests cover the pure-function heuristics (blur/brightness/dimensions)
against constructed edge cases (flat image, random noise, all-black,
all-white) - these don't need Postgres/Redis running.

---

## Sample API Requests/Responses

Captured live from the deployed instance
(`https://gogig-media-pipeline.onrender.com`) - not a local run.

**Upload:**
```bash
curl -X POST -F "file=@screenshot.jpg" \
  https://gogig-media-pipeline.onrender.com/api/v1/uploads
```
```json
{
  "job_id": "54a9a7da-725b-4112-935a-c80052909c70",
  "status": "pending",
  "message": "Upload accepted, processing queued."
}
```

**Status:**
```bash
curl https://gogig-media-pipeline.onrender.com/api/v1/jobs/54a9a7da-725b-4112-935a-c80052909c70/status
```
```json
{
  "job_id": "54a9a7da-725b-4112-935a-c80052909c70",
  "status": "completed",
  "retry_count": 0,
  "created_at": "2026-07-20T19:22:16.475590Z",
  "updated_at": "2026-07-20T19:22:19.651462Z",
  "processing_started_at": "2026-07-20T19:22:17.184891Z",
  "processing_completed_at": "2026-07-20T19:22:27.562553Z",
  "failure_reason": null
}
```

**Results:**
```bash
curl https://gogig-media-pipeline.onrender.com/api/v1/jobs/54a9a7da-725b-4112-935a-c80052909c70/results
```
```json
{
  "job_id": "54a9a7da-725b-4112-935a-c80052909c70",
  "status": "completed",
  "retry_count": 0,
  "failure_reason": null,
  "overall_confidence": 0.694,
  "has_issues": true,
  "checks": [
    {
      "check_name": "blur_detection",
      "passed": false,
      "severity": "critical",
      "confidence": 0.81,
      "message": "Image appears blurry (sharpness score 23.3, threshold 100.0)",
      "details": { "laplacian_variance": 23.33, "threshold": 100 }
    },
    {
      "check_name": "brightness_analysis",
      "passed": true,
      "severity": "info",
      "confidence": 0.85,
      "message": "Brightness OK (mean intensity 101.8/255)",
      "details": { "mean_intensity": 101.79 }
    },
    {
      "check_name": "dimension_validation",
      "passed": true,
      "severity": "info",
      "confidence": 1.0,
      "message": "Resolution OK (1920x1080)",
      "details": { "width": 1920, "height": 1080 }
    },
    {
      "check_name": "duplicate_detection",
      "passed": true,
      "severity": "info",
      "confidence": 0.9,
      "message": "No duplicate found among prior uploads",
      "details": { "phash": "ea6387ce399a4730", "closest_match_job_id": null, "closest_distance": null, "threshold": 5 }
    },
    {
      "check_name": "screenshot_detection",
      "passed": false,
      "severity": "warning",
      "confidence": 0.55,
      "message": "Image resembles a screenshot or re-saved photo (screen-like aspect ratio + no camera metadata)",
      "details": { "aspect_ratio": 0.562, "ratio_matches_screen": true, "has_camera_metadata": false }
    },
    {
      "check_name": "suspicious_editing_heuristic",
      "passed": true,
      "severity": "info",
      "confidence": 0.3,
      "message": "No known editing-tool signature found in EXIF (inconclusive - EXIF is frequently stripped or absent)",
      "details": { "exif_software_tag": "Windows 11", "matched_marker": null }
    },
    {
      "check_name": "plate_format_validation",
      "passed": false,
      "severity": "warning",
      "confidence": 0.45,
      "message": "No text matching Indian plate format found in image",
      "details": { "raw_ocr_text": "..." }
    }
  ]
}
```

This test image was itself a Windows screenshot (note
`exif_software_tag: "Windows 11"` above) - `screenshot_detection` correctly
flagged it using only aspect ratio and missing camera metadata, with no
external ML model involved. `blur_detection` also correctly caught it as
low-sharpness. Good live evidence the heuristics behave as designed on a
real, uncurated input rather than only on synthetic test images.

---

## Assumptions

- "Duplicate" means visually near-identical (perceptual hash match), not
  byte-identical - field uploads are frequently re-compressed/re-saved
  before reaching the API.
- Indian plate format only (per the assignment's problem context: vehicle
  images), matched as `[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}` after
  stripping whitespace/punctuation.
- A single uploaded file per request (no batch upload endpoint) - the
  assignment's example flows are all single-image.
- "Processing failed" is reserved for genuine processing errors (corrupt
  file, decode failure, exhausted retries) - a *detected issue* (blurry,
  duplicate, etc.) is a successful analysis that found a problem, not a
  failure state. This distinction is why `has_issues` is a separate field
  from `status`.