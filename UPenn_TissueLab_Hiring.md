# Take-Home Challenge: Branch-Aware, Multi-Tenant Workflow Scheduler
**Duration:** 24 hours  
**Tech Stack:** FastAPI (backend) | Optional: simple web UI or CLI

---

Dear Candidate,

Thank you very much for your time and interest in our position. We truly appreciate your effort in completing this short take-home challenge. Please try your best to beautify your UI. And this will be the **only interview round**. Good luck!

---

## 🎯 Goal
Build a minimal but functional Workflow Scheduler for large-image inference tasks.
It should:

1. Allow users to define workflows (DAGs) composed of multiple long-running image processing jobs.

2. Enforce serial execution within the same branch and parallel execution across branches, up to a global worker limit.

3. Support multi-tenant isolation (each user sees only their own workflows).

4. Limit the number of concurrent active users to 3 — additional users queue until a slot frees.

5. Provide real-time progress tracking for both workflows and jobs.

> ⚡ **Note:** The acceleration logic (InstanSeg optimization and concurrency design) is the most important part of this challenge.  
> Please pay special attention to how you design the tiling, 

You may also reference OpenAI Agent Builder concepts for workflow/DAG design inspiration. 
`x.com/OpenAIDevs/status/1975269388195631492`  
([link](https://x.com/OpenAIDevs/status/1975269388195631492))

---

## 🧩 Core Requirements

### 1️⃣ Branch-Aware Scheduling
- Jobs within the same `branch` must execute **serially** (FIFO).  
- Jobs from different branches may run **in parallel**, bounded by a global concurrency limit (`MAX_WORKERS`).  
- Failures or retries are **branch-local** — one branch’s failure doesn’t block others.

### 2️⃣ Multi-Tenant Isolation & Active-User Limit

- Each request must include a tenant header:  
  ```http
  X-User-ID: <user-uuid>
  ```
- At most 3 distinct users may have running jobs concurrently.
- The 4th and later users must wait until one of the active users finishes all jobs.
- Please consider stability and rate limiting strategies for **high concurrency (high QPS)** scenarios.

On job execution:
- Each job has a unique `job_id`.  
- Execute an image inference task using **InstanSeg** (see below). 
- Jobs should be cancellable while still in the queue (before execution starts).
- Track state transitions asynchronously: `PENDING → RUNNING → SUCCEEDED / FAILED`.
  - Expose progress for both individual jobs and entire workflows (e.g., percent complete, tile count processed/total).  
  - Support real-time updates to be displayed on a frontend page.

### 3️⃣ Image Processing Job Types
Implement at least two long-running, tile-based tasks, for example: segment all cells in this image, Generate a binary tissue mask from a WSI to skip background tiles and so forth. And display the results in the front-end.

### 4️⃣ InstanSeg Integration (Segment large images)
- Using **InstanSeg** to segment all the cells in the image: `github.com/instanseg/instanseg`  
  ([link](https://github.com/instanseg/instanseg))  
- Optimize for speed and throughput — handle large WSIs efficiently.
- Hint: Use tiled prediction to process gigapixel-scale images (divide into tiles, process in batches, merge results).
- Your scheduler should be able to run multiple such segmentation jobs concurrently (subject to branch and user limits). 
- Hint: Use tile overlap with blending/merging to avoid seams at boundaries.  

### Data for Testing (WSI)
- Download Whole Slide Images (Aperio SVS) for local testing from CMU OpenSlide test data:  
  `openslide.cs.cmu.edu/download/openslide-testdata/Aperio/`  
  ([link](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/))  

---

## 💡 Bonus Features (Optional)

### 🥇 Concurrency Control & Observability
- Implement **rate limiting** using `asyncio.Semaphore` or Redis token bucket.  
- Expose **Prometheus metrics** such as `queue_depth`, `worker_active_jobs`, `job_latency_seconds`.  
- Add a small **dashboard** for: average job latency per minute, active workers, per-branch queue depth.

### 🥉 Deployment
- Provide a `docker-compose.yml` covering: backend API, worker(s), Redis/queue, Prometheus, Grafana.  
- Or deploy to a live environment of your choice.

---

## 📦 Deliverables
Please include the following in your submission:
- A public GitHub repository containing your source code  
- `README.md` with:  
  - Setup instructions (`docker-compose up` or local commands)  
  - A short section describing how you would **scale** to 10× more jobs/users  
  - A short section on **testing** and **monitoring** in production  
- API documentation (Swagger / OpenAPI)  
- Demo screenshots or short screen recording (optional)  
- Clean, modular, and readable code

---

Thank you again for your time and effort — we’re looking forward to seeing your work.  
Good luck, and happy coding! 🚀
