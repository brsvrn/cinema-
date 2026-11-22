# Cloud AI Animation Studio

Telefondan yönetilen, tamamen bulut tabanlı kişisel animasyon stüdyosu. YouTube (1920×1080) ve
Shorts/Reels/TikTok (1080×1920) için karakter devamlılığına sahip mini diziler üretir.

- `web/` — Mobil öncelikli, kurulabilir PWA (Next.js, Vercel)
- `worker/` — Render motoru + 15 aşamalı kalıcı üretim hattı (Python, Skia, Piper TTS, Rhubarb, FFmpeg)
- `supabase/` — Veritabanı şeması, kalıcı iş kuyruğu, depolama
- `.github/workflows/` — CI, render worker, kabul testi
- `CLAUDE.md` — mimari, kurallar ve komutlar (Claude Code oturumları için proje hafızası)
- `.claude/skills/` — tekrar kullanılabilir Claude Skills

Hızlı başlangıç (worker): `cd worker && bash bin/setup_worker.sh && python -m studio acceptance`
