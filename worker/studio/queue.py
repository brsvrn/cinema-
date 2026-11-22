"""Persistent job queue worker.

Queue lives in Postgres (Supabase) table `jobs`.  Claiming uses the SQL
function `claim_job(worker_id, lease_seconds)` (FOR UPDATE SKIP LOCKED) and a
lease that is extended by heartbeats.  If a worker dies, its lease expires and
the next worker re-claims the job; the pipeline resumes from checkpoints.
Locally (no Supabase) the queue is a folder of JSON documents.
"""
from __future__ import annotations

import os
import socket
import threading
import time
import traceback

from .pipeline import Pipeline


class Worker:
    def __init__(self, store, lease_s: int = 900):
        self.store = store
        self.lease_s = lease_s
        self.id = f"{socket.gethostname()}-{os.getpid()}-{os.environ.get('GITHUB_RUN_ID', 'local')}"

    def claim(self):
        if self.store.kind == "supabase":
            rows = self.store.rpc("claim_job", {"p_worker": self.id, "p_lease_seconds": self.lease_s})
            return rows[0] if rows else None
        now = time.time()
        for j in sorted(self.store.list("jobs"), key=lambda j: j.get("created_at", 0)):
            if j.get("status") == "queued" or (j.get("status") == "running" and j.get("lease_until", 0) < now):
                j.update(status="running", worker=self.id, lease_until=now + self.lease_s,
                         attempts=j.get("attempts", 0) + 1)
                self.store.put("jobs", j["id"], j)
                return j
        return None

    def _heartbeat(self, job_id: str, stop: threading.Event):
        while not stop.wait(60):
            try:
                if self.store.kind == "supabase":
                    self.store.rpc("heartbeat_job", {"p_job": job_id, "p_worker": self.id,
                                                     "p_lease_seconds": self.lease_s})
                else:
                    j = self.store.get("jobs", job_id)
                    j["lease_until"] = time.time() + self.lease_s
                    self.store.put("jobs", job_id, j)
            except Exception:  # noqa: BLE001
                traceback.print_exc()

    def finish(self, job: dict, status: str, error: str | None = None):
        if self.store.kind == "supabase":
            self.store.rpc("finish_job", {"p_job": job["id"], "p_worker": self.id, "p_status": status,
                                          "p_error": error})
        else:
            job.update(status=status, error=error, finished_at=time.time())
            self.store.put("jobs", job["id"], job)

    def run_job(self, job: dict):
        data = job.get("data") or job
        kind = job.get("kind") or data.get("kind")
        stop = threading.Event()
        hb = threading.Thread(target=self._heartbeat, args=(job["id"], stop), daemon=True)
        hb.start()
        try:
            if kind == "produce_episode":
                mode = data.get("mode", "economic")
                if mode == "cinematic":
                    from .engines.cinematic import ensure_allowed
                    ensure_allowed(self.store)
                Pipeline(self.store, job.get("episode_id") or data["episode_id"],
                         formats=tuple(data.get("formats", ["youtube", "shorts"])),
                         force_continuity=data.get("force", False),
                         quality="advanced" if mode in ("advanced", "cinematic") else "economic",
                         stop_after=data.get("stop_after")).run()
            elif kind == "character_sheets":
                from .cli import finalize_character
                finalize_character(self.store, data["character_id"], approve=bool(data.get("approve")))
            else:
                raise ValueError(f"unknown job kind {kind}")
            self.finish(job, "done")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            attempts = job.get("attempts", 1)
            self.finish(job, "failed" if attempts >= 3 else "queued", str(e)[:1000])
        finally:
            stop.set()

    def loop(self, once: bool = False, max_jobs: int = 5, idle_exit_s: int = 60):
        done = 0
        idle_since = time.time()
        while done < max_jobs:
            job = self.claim()
            if not job:
                if once or time.time() - idle_since > idle_exit_s:
                    print("queue empty - exiting (GPU/CPU runners stop when idle)")
                    return
                time.sleep(10)
                continue
            print(f"claimed job {job['id']}")
            self.run_job(job)
            done += 1
            idle_since = time.time()
