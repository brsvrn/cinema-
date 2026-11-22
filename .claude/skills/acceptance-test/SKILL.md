---
name: acceptance-test
description: Run the end-to-end acceptance test (two consecutive 30 s episodes with the same characters/location) and verify real MP4 output. Use after any engine/pipeline change before declaring work done.
---
# Acceptance test

```bash
cd worker
rm -rf data work/ser_fener_ep00*      # clean start (keeps TTS cache)
python -m studio acceptance            # exit code 0 = all continuity checks passed
```
Then verify visually: extract frames (`ffmpeg -ss 5 -i work/ser_fener_ep001/out/ser_fener_ep001_youtube.mp4 -frames:v 1 f.png`) and inspect them,
check `work/*/qc.json`, and confirm both `_youtube.mp4` (1920×1080) and `_shorts.mp4` (1080×1920) exist for both episodes.
On GitHub: run the "Acceptance (2 episodes)" workflow; MP4s are uploaded as artifacts.
