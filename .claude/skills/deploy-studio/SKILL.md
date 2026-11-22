---
name: deploy-studio
description: Deploy or reconfigure the studio's cloud services (Supabase schema, Vercel PWA, GitHub Actions secrets, optional R2/RunPod). Use for first-time setup, new keys, or redeploys.
---
# Deploy

1. Supabase: apply `supabase/migrations/0001_studio.sql` (Supabase MCP `apply_migration` or SQL editor). Seed demo data with
   `SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python -m studio init-demo` (from `worker/`).
2. GitHub secrets (repo → Settings → Secrets → Actions): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (+ optional `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `RUNPOD_*`, `R2_*`).
3. Vercel: project root `web/`, framework Next.js. Env: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `STUDIO_PASSWORD`, `STUDIO_SESSION_SECRET`,
   `GH_DISPATCH_TOKEN` (fine-grained PAT, Actions: read/write on this repo), `GH_REPO=owner/name`, `GH_REF=<branch>`.
4. Never expose the service key with a `NEXT_PUBLIC_` prefix. Never enable paid services without the owner's explicit OK.
5. Smoke test: open the PWA → Kuyruk → “Worker’ı uyandır”; queue a preview episode; watch the Actions run.
