# Branch-Aware, Multi-Tenant Workflow Scheduler (FastAPI)

A tiny but complete scheduler for large-image inference (Whole Slide Images / SVS). It supports:

- Serial execution within a branch; parallel across branches up to a global worker cap
- Multi-tenant isolation (per `X-User-ID`) with a hard limit of 3 active users
- Long-running, tile-based jobs with progress and live updates (SSE)
- Two job types: SEGMENT_CELLS (InstanSeg) and TISSUE_MASK (thresholding)
- Simple Tailwind UI at `/ui` to upload, create workflows, create jobs, start, watch, and download outputs (with live queue status hints)

---

## 1) Prerequisites

macOS (Apple Silicon OK). You’ll use `brew` and `uv`.

1. Install OpenSlide (native lib):
   ```bash
   brew install openslide
   ```

2. Python deps (use `uv`):
   ```bash
   uv pip install fastapi uvicorn[standard] python-multipart pillow numpy scikit-image
   uv pip install openslide-python
   ```

   If OpenSlide dylib can’t be found at runtime, install a bundled dylib or set your path:
   ```bash
   # Option A: bundled dylib
   uv pip install openslide-bin

   # Option B: use Homebrew dylib
   export DYLD_LIBRARY_PATH="$(brew --prefix openslide)/lib:${DYLD_LIBRARY_PATH}"
   uv run python3 -c "import openslide; print('OpenSlide OK')"
   ```

3. PyTorch (Apple Silicon with Metal)
   ```bash
   uv pip install torch torchvision torchaudio
   uv run python3 -c "import torch; print('Torch', torch.__version__, 'MPS:', torch.backends.mps.is_available())"
   ```

4. InstanSeg (cells segmentation). We call `instanseg.InstanSeg` if present; falls back if not.
   ```bash
   uv pip install "git+https://github.com/instanseg/instanseg.git"
   uv run python3 - <<'PY'
import instanseg
print('instanseg OK; attrs:', [a for a in dir(instanseg) if not a.startswith('_')])
PY
   ```

5. Optional test data (SVS):
   ```bash
   mkdir -p samples
   curl -L -o samples/CMU-1.svs "https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1.svs"
   ```

---

## 2) Run the server

Always run in the same `uv` environment so OpenSlide + Python libs are found:

```bash
uv run python3 -m uvicorn app.main:app --reload
```

- Health: `http://127.0.0.1:8000/health`
- API Docs: `http://127.0.0.1:8000/docs`
- UI: `http://127.0.0.1:8000/ui`

---

### Settings

Key knobs live in `app/settings.py`:
- `MAX_WORKERS` (global concurrent jobs)
- `MAX_ACTIVE_USERS` (concurrent tenants allowed to run)
- `ENABLE_INSTANTSEG` (try InstanSeg if installed; falls back safely if not)
- `TILE_SIZE`, `TILE_OVERLAP` (tiling parameters)

---

## 3) Use the UI

Open `http://127.0.0.1:8000/ui`. Follow these steps top-to-bottom:

1) User
- Enter any `X-User-ID` (e.g., a UUID). Only 3 different users can run jobs at once. Others wait.

2) Upload File
- Prefer `.svs` Whole Slide Images so we can tile via OpenSlide (much faster than loading the whole image).
- You can also use a regular PNG/JPEG for quick sanity checks.

3) Create Workflow
- Click "New Workflow". The `workflow_id` appears.

4) Create Job
- Pick a `job type`:
  - `SEGMENT_CELLS`: uses InstanSeg (or a safe fallback) to mark likely cell regions (red overlay in preview).
  - `TISSUE_MASK`: classical thresholding to mark tissue vs background (green overlay). Useful to skip blank tiles.
- Optional `branch`: jobs in the same branch run serially; different branches can run concurrently.
- Click Create Job; you’ll see a `job_id`.
- Up to 10 jobs per workflow are allowed; the counter shows jobs created.

5) Start / Observe
- Click "Start Queue" to start all PENDING jobs, or click "Start" on an individual job card.
- Live updates stream via SSE. A small grey line shows queue reasons while PENDING, e.g.:
  - "Queued: waiting for branch lock"
  - "Queued: waiting for active-user slot (3/3)"
  - "Queued: waiting for worker capacity"
- Job progress shows tiles processed; workflow progress shows aggregate completion.
- After success, use "Preview" (stitched overlay), "Artifacts" (ZIP of masks + preview), and "Download" (manifest JSON).
- You can cancel a PENDING job, and retry a FAILED job. Actions appear contextually on each job card.

Outputs are saved under `uploads/results/<job_id>/`.

---

## 4) What’s happening under the hood (short)

- Branch-aware scheduling
  - Serial in-branch (FIFO). Branches run in parallel up to `MAX_WORKERS`.
- Multi-tenant isolation
  - Every request uses header `X-User-ID`. Max 3 distinct users can have jobs running concurrently; others wait.
- Jobs
  - States: `PENDING → RUNNING → SUCCEEDED / FAILED`; queued jobs can be `CANCELED`; `RETRY` resets to PENDING.
  - Progress updates per tile; live updates streamed via SSE at `/jobs/{job_id}/events?user_id=...`.
- Tiling
  - `.svs` is a pyramid format; we read small regions from the large slide via OpenSlide.
  - Each tile produces a mask image; we compose a stitched preview for quick inspection.

---

## 5) API quick reference

Headers: `X-User-ID: <your-id>` unless noted.

- Create workflow: `POST /workflows`
  - body: `{ "name": "demo" }`
  - returns: `{ workflow: { workflow_id, user_id, ... } }`

- Upload file: `POST /files` (multipart form; field: `file`)
  - returns: `{ file: { file_id, ... } }`

- Create job: `POST /jobs`
  - body: `{ "workflow_id": "...", "file_id": "...", "job_type": "SEGMENT_CELLS"|"TISSUE_MASK", "branch": "A" }`
  - returns: `{ job: { job_id, ... } }`

- Start job: `POST /jobs/{job_id}/start`
- Cancel (only PENDING): `POST /jobs/{job_id}/cancel`
- Retry (not RUNNING): `POST /jobs/{job_id}/retry`

- Queue status (UX helper): `GET /jobs/{job_id}/queue_status`
  - returns: `{ queued: bool, waiting_for: ["USER_SLOT"|"BRANCH"|"WORKER"], active_users, max_active_users, active_workers, max_workers }`

- Get job: `GET /jobs/{job_id}` → `{ state, progress, ... }`
- Live updates: `GET /jobs/{job_id}/events?user_id=<same-X-User-ID>` (SSE)
- Download manifest JSON: `GET /jobs/{job_id}/result`
- Download preview image: `GET /jobs/{job_id}/preview`
- Download masks zip: `GET /jobs/{job_id}/artifacts.zip`

- Get workflow: `GET /workflows/{workflow_id}` → `{ state, percent_complete, ... }`
- Live workflow updates: `GET /workflows/{workflow_id}/events?user_id=<same-X-User-ID>` (SSE)
 - List jobs in workflow: `GET /workflows/{workflow_id}/jobs`

---

## 6) Scaling to 10×

- Workers & queue
  - Split API and workers; use Redis or a durable queue. Each worker runs tiles with `asyncio.Semaphore` per GPU/CPU slot.
  - Keep per-branch locks (serial) and global worker cap; add per-user rate limits.

- Tiling & batching
  - Tune tile size/overlap; batch tiles to amortize model overhead.
  - Use JPEG-compressed intermediate tiles on NVMe; cache slide reads.

- Hardware
  - Pool multiple GPUs (CUDA) or Apple Silicon devices (MPS). Pin workers per device.

- Observability (optional)
  - Export metrics: `queue_depth`, `active_jobs`, `job_latency_seconds`, `per_branch_queue_depth`.
  - Dashboard tiles/sec, job latency, active users, error rates.

- Resilience
  - Add retries with backoff at tile level. Persist job state and artifacts to object storage (e.g., S3).

---

## 7) Testing & Monitoring (production)

Note: Prometheus/Grafana are not bundled in this repo; items below are guidance if you choose to add them.

- Testing
  - Unit: scheduler branch-serial ordering, `MAX_WORKERS` cap, 3 active-user gate, job store state transitions and cancel/retry rules.
  - Integration: upload → create workflow → create job → start → receive SSE updates → SUCCEEDED/FAILED → preview/artifacts present on disk.
  - Performance: measure tiles/sec on representative SVS files; run concurrent jobs across branches and users to verify throughput and fairness.

- Monitoring
  - Metrics (optional via Prometheus): `queue_depth`, `active_workers`, `active_users`, `job_latency_seconds`, `per_branch_queue_depth` (e.g., expose at `/metrics`).
  - Logs: structured JSON logs with `job_id`, `workflow_id`, `user_id`, state changes, durations, and errors; ship to a log backend.
  - Alerts: stuck jobs (RUNNING > N minutes), surge in failures, backlog growth beyond threshold, no workers available.
  - Dashboards (optional via Grafana): tiles/sec, job latency percentiles, active users/workers, queue depth per branch, error rates.

---

## 8) Troubleshooting

- `ModuleNotFoundError: openslide`
  - You’re not using the `uv` env or the dylib isn’t visible. Fix:
    ```bash
    uv run python3 -c "import openslide; print('OK')"
    uv pip install openslide-bin  # or set DYLD_LIBRARY_PATH
    ```

- PIL `DecompressionBombError`
  - You tried to open a huge `.svs` with PIL. Always process SVS through OpenSlide by running the server via `uv run ...` and uploading `.svs` (not expanding to a giant PNG first).

- MPS False
  - Check your Python is arm64 and Torch is the Apple Silicon wheel.
    ```bash
    python3 -c "import platform; print(platform.machine())"   # arm64 expected
    uv pip install torch torchvision torchaudio
    ```

---

## 9) Project layout (key parts)

```
app/
  main.py                  # FastAPI app + routers + static UI mount
  api_jobs.py              # Jobs API (create/list/get/start/cancel/retry/result/preview/events)
  api_workflows.py         # Workflows API (create/get)
  api_files.py             # Uploads API
  scheduler.py             # Branch-serial scheduler + MAX_WORKERS + 3 active users gate
  executor.py              # Tiling executors + InstanSeg/tissue mask + previews
  instanseg_runner.py      # InstanSeg integration (model load + per-tile mask)
  file_store.py            # File paths, uploads dir, results dir helpers
  store.py                 # In-memory jobs store
  schemas.py               # Pydantic models + enums
  static/index.html        # Tailwind UI (no React)
uploads/
  results/<job_id>/        # mask_*.png, preview.png, manifest.json, artifacts.zip
```

---


