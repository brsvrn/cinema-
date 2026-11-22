# CLAUDE.md — Cloud AI Animation Studio

Project memory for Claude Code sessions. Read this first; it is the source of truth
for architecture, rules and commands. Keep it updated when you change behaviour.

## What this is
A personal, fully cloud-hosted animation studio managed from a phone (installable PWA).
It produces original animated videos and mini-series with **character continuity** for
YouTube (1920×1080), Shorts/Reels/TikTok (1080×1920). The owner never installs anything
locally — all heavy work runs on cloud workers.

## Hard rules
1. **No paid service without explicit owner approval.** Paid paths (Claude API, ElevenLabs,
   RunPod GPU, R2 over free tier) only run when the key exists **and** the owner enabled
   paid usage (`settings/budget.allow_paid` in the app, `STUDIO_ALLOW_PAID=1` in the worker).
   Always prefer the free path (Piper TTS, template writer, GitHub Actions CPU, procedural music).
2. **Never render on Vercel.** Vercel only serves the PWA + server actions. Rendering runs in
   the independent worker (`worker/`, executed by GitHub Actions `render-worker.yml`,
   or Colab/RunPod using the same CLI).
3. **Secrets only in env vars** (Vercel env, GitHub Actions secrets). Never in code, never
   sent to the browser. The web app uses the Supabase service key **server-side only**.
4. **Characters are never regenerated per episode.** A character has a persistent Character ID
   + `design_hash` + `voice_hash`. Editing creates a new version that must be approved; the
   continuity checker blocks production if hashes don't match the approved record.
5. **Read the Series Bible before writing an episode.** `continuity.check_script` must pass
   (or be explicitly forced by the owner).
6. **A system change is not done until real MP4s are produced and QC passes**
   (`python -m studio acceptance`).

## Architecture
```
Phone (PWA, Next.js on Vercel) ──server actions──► Supabase Postgres (jsonb docs + jobs queue)
        │                                               ▲            │
        └── workflow_dispatch (GH_DISPATCH_TOKEN) ──►  GitHub Actions render worker (Python)
                                                        │  claim_job() lease + heartbeat
                                                        ▼
                                Supabase Storage (MP4/PNG/SRT/state) [+ optional Cloudflare R2]
```
- `web/` — Next.js 15 App Router PWA. Pages: home, series (+ Series Bible editor), characters
  (design + voice + approval), locations, episode production (estimate → preview/full),
  episode page (progress, players, downloads, storyboard, QC, continuity), script editor /
  video editing, render queue, publishing schedule, cost control, YouTube export.
  Auth: single owner password → HMAC cookie (`STUDIO_PASSWORD`, `STUDIO_SESSION_SECRET`).
  Data: `lib/store.ts` (Supabase REST with service key, or local JSON files when no Supabase).
- `worker/studio/` — Python render engine + pipeline:
  - `rig.py` procedural vector character rig (Skia): skeleton (16 joints), turn −1..1 (front,
    3/4, side, back), poses (`POSES`), expressions (`EXPRESSIONS`), Rhubarb visemes A–H/X,
    blink, gaze, breathing, props (glowing shell, lantern), rim light. `render_turnaround`
    makes the model sheet; `render_mouth_chart` the mouth library.
  - `location.py` persistent procedural sets (`lighthouse_cliff`): parallax layers, lighting
    presets day/sunset/dusk/night, animated sea/clouds/stars, rotating lighthouse beam,
    distant boat signal, rain, fireflies. `object_camera` = insert-shot framing.
  - `camera.py` virtual camera: parallax, push/pan/crane moves, handheld noise, telephoto.
  - `storyboard.py` beats → timeline (exactly 30 s, dialogue never stretched) → shot list
    (establishing crane, CU/MCU/OTS/two/wide/insert, closing pull-back).
  - `performance.py` per-frame acting: pose/expression blending, talk gestures, auto-facing,
    look-at, walking, lip-sync visemes, env events (lamp on/off/flicker, boat blink).
  - `render.py` frame renderer (grade, DOF, vignette, burned captions for Shorts, title card)
    and per-shot H.264 encoder (raw BGRA → ffmpeg).
  - `tts.py` Piper (free) with per-character fixed voice profile (model, pitch, speed, noise);
    ElevenLabs optional. `lipsync.py` Rhubarb (phonetic) with amplitude fallback.
  - `audio.py` procedural music (series-seeded motif, mood keys), SFX synthesis, ducking mix.
  - `bible.py` Series Bible (facts + who knows them, events, threads, timeline, end states).
  - `continuity.py` story + identity checks; `resolve_blocking` inherits previous episode end state.
  - `writer.py` Claude script writer (if key) or free template writer — same JSON schema.
  - `pipeline.py` 15 checkpointed stages; parallel shot rendering; resume after crash.
  - `qc.py` probe/blackdetect/freezedetect/volumedetect; `repair` stage re-renders failed shots.
  - `publish.py` SRT TR/EN, thumbnail, YouTube metadata. `cost.py` estimates + budget.
  - `queue.py` worker loop (`claim_job` / `heartbeat_job` / `finish_job` SQL functions).
  - `store.py` LocalStore / SupabaseStore (+ R2 for large files).
- `supabase/migrations/0001_studio.sql` — tables (series, characters, locations, episodes,
  jobs, cost_ledger, settings), RLS (owner policies; worker uses service role), queue
  functions, private `studio` bucket.

## Production modes
1. **economic** (default, free): procedural 2D rig engine above, CPU on GitHub Actions.
   ~3–4 min wall time per 30 s episode (both formats) on 4 vCPU.
2. **advanced**: same engine with motion blur (sub-frame blending), supersampling, stronger
   DOF. Future: Blender headless 2.5D/3D scene export (`engines/` placeholder).
3. **cinematic** (paid, GPU): RunPod serverless ComfyUI (Wan 2.x i2v + IP-Adapter/ControlNet,
   optional character LoRA) refines economic-render keyframes. Requires `RUNPOD_API_KEY`,
   `RUNPOD_ENDPOINT_ID` and owner approval; the endpoint scales to zero after the job.

## Pipeline stages (pipeline.STAGES)
memory → script → continuity → storyboard → voices → animate → lipsync → staging → audio →
render (per shot, per format, parallel) → assemble → qc → repair → upload → publish.
State: `work/<episode>/state.json` (mirrored to storage under `episodes/<id>/work/`).

## Commands (run inside `worker/`)
```bash
bash bin/setup_worker.sh                 # ffmpeg, libEGL, python deps, Rhubarb, Piper voice
python -m pytest -q tests                # unit tests (fast)
python -m studio init-demo               # acceptance cast + location + 2 episode scripts
python -m studio produce ser_fener_ep001 # run/resume one episode
python -m studio sheets chr_ada          # model sheet + mouth chart
python -m studio estimate --mode cinematic
python -m studio worker --once           # process the queue (Supabase or local jobs/)
python -m studio acceptance              # full acceptance: 2 episodes + continuity report
```
Web (inside `web/`): `npm run dev` (uses `../worker/data` when Supabase env is absent),
`npx tsc --noEmit`, `npm run build`.

## Episode script schema (writer output, also editable in the app)
See `worker/studio/writer.py::SCHEMA_DOC` and the reference episodes in
`worker/studio/demo/episodes.py`. Key fields: `beats[]` (`line` with speaker/text/text_en/
emotion/action/look_at/uses_facts/new_facts/teaches, or `action` with duration/camera/moves/
poses/props/events/sfx), `new_facts`, `threads_opened/resolved`, `summary(_en)`,
`continues_from`, `lighting`, `music_mood`, `env_start`.

## Character system
Record = `{id, name, personality, backstory, design{…}, voice{…}, design_hash, voice_hash,
version, approved, library{views, skeleton, expressions, mouth_shapes, motions}, lora,
reference_images{model_sheet_key, mouth_shapes_key, voice_sample_key}}`.
New/edited characters → job `character_sheets` (recomputes hashes, renders references,
voice sample; `approve=true` marks approved).

## Acceptance test (done 2026-11-22)
Cast: **Ada** (`chr_ada`, 10 y/o, red curls, yellow raincoat, Piper +5 st) and **Tomo Dede**
(`chr_tomo`, retired captain, white beard, glasses, anchor cap, Piper −2.5 st).
Location: **Martı Burnu Feneri** (`loc_marti_burnu`). Series `ser_fener` "Fener Bekçileri".
Ep1 "Sessiz Fener" (sunset; lamp fails, Ada finds glowing shell, boat signals) →
Ep2 "Işıktan Mesaj" (night; Morse message, shell relights lamp; open thread: who is on the boat).
`python -m studio acceptance` checks MP4s (both formats, 30 s, audio), identical design/voice
hashes, same location, inherited positions + prop (shell), fact usage, thread resolution.

## Service status / owner-provided config
| Service | Used for | Free? | Config |
|---|---|---|---|
| GitHub Actions | render worker, CI | yes (quota) | secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (+ optional keys) |
| Vercel | PWA hosting | yes (Hobby) | env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, STUDIO_PASSWORD, STUDIO_SESSION_SECRET, GH_DISPATCH_TOKEN, GH_REPO, GH_REF |
| Supabase | DB, queue, storage | yes (free tier) | apply `supabase/migrations/*.sql` |
| Piper TTS / Rhubarb / FFmpeg / Skia | voices, lip-sync, video | yes | installed by setup_worker.sh |
| Claude API | script writing + review | paid | ANTHROPIC_API_KEY (worker + Vercel) |
| ElevenLabs | premium voices | paid (free tier small) | ELEVENLABS_API_KEY, per-character voice id |
| RunPod + ComfyUI/Wan | cinematic mode | paid | RUNPOD_API_KEY, RUNPOD_ENDPOINT_ID |
| Cloudflare R2 | large media | free 10 GB | R2_* |
Not used (by design): Google Colab (manual only; same CLI works there), Blender (planned for
advanced 3D), Remotion (Skia+FFmpeg covers compositing without a Node render farm), Whisper
(subtitles come from the script with exact TTS timings).

## Live resources
- Supabase project `cinema-studio` (ref `fpytljzquqqvgrowrwbf`, eu-central-1, free tier), URL
  `https://fpytljzquqqvgrowrwbf.supabase.co`. Schema applied; demo series seeded with 4 queued jobs
  (2× character_sheets, ep001, ep002) for the first cloud worker run.
- Vercel project `cinema-studio` (team vertice6, `prj_k0DbcF6SfXupCdmwS4DAEmUrNO7J`, root `web/`, functions fra1),
  production URL `https://cinema-studio-vertice6.vercel.app`, deploys from branch `ccr-a1e6e0c9-3i4spd`.
  Plain env set: SUPABASE_URL, SUPABASE_BUCKET, GH_REPO, GH_REF, GH_WORKFLOW. Owner must add secrets:
  SUPABASE_SERVICE_ROLE_KEY, STUDIO_PASSWORD, STUDIO_SESSION_SECRET, GH_DISPATCH_TOKEN (sensitive).
- Supabase keys: prefer the new `sb_secret_…` secret key (sent only as `apikey`); legacy JWT keys also work.

## Conventions
- UI text Turkish; code/comments English. Commit small, test before push.
- Never commit `.env*`, `worker/data`, `worker/work`, `worker/.models`.
- Add new poses/expressions to `rig.py` dicts → they automatically appear in the library.
- New location kinds: subclass pattern in `location.py`, register in `LOCATION_KINDS`.
