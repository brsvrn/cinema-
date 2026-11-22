---
name: render-worker
description: Operate, debug or extend the cloud render worker and job queue (GitHub Actions, Supabase queue, resume, QC failures, performance). Use when renders fail, are stuck, slow, or when adding a production mode.
---
# Render worker

- Worker entry: `python -m studio worker` (`studio/queue.py`). Jobs: `produce_episode` (`episode_id`, `formats`, `force`, `stop_after`, `mode`), `character_sheets` (`character_id`, `approve`).
- Queue SQL: `claim_job`, `heartbeat_job`, `finish_job` in `supabase/migrations/0001_studio.sql`. Stuck job = `running` with expired `lease_until` → automatically re-claimed.
- Resume: `work/<episode>/state.json` (`stages`, `shots_done`, `artifacts`) mirrored to storage `episodes/<id>/work/`. Delete a stage key to force it to re-run.
- Script edits invalidate stages automatically (script hash in state).
- QC (`studio/qc.py`): resolution, duration 28–32.5 s, audio present/loud enough, no black segments, no frozen video > 2.5 s (catches slideshow output). `repair` re-renders failing shots twice before failing the job.
- Speed: shots render in parallel (`STUDIO_RENDER_PROCS`, default = CPU count). CU shots are the slowest (large blurred layers).
- GitHub Actions: `.github/workflows/render-worker.yml` (dispatch + every 4 h fallback), `acceptance.yml` (artifacts).
- Never move rendering to Vercel. GPU (RunPod) only with owner approval + budget check.
