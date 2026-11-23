"""Optional Remotion packaging: animated intro + YouTube end screen around long episodes.

Only the short clips are rendered with Remotion (browser); they are encoded with the same
x264 settings as the episode shots and joined with FFmpeg, so the 8+ minute episode is
never re-rendered.  Enabled when the `remotion/` project has node_modules installed and
STUDIO_REMOTION is not "0".
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import config

REMOTION_DIR = config.WORKER_ROOT.parent / "remotion"
INTRO_S = 3.0
END_S = 10.0


def available() -> bool:
    return (os.environ.get("STUDIO_REMOTION", "1") != "0" and (REMOTION_DIR / "node_modules" / "@remotion" / "cli").exists()
            and shutil.which("npx") is not None)


def _browser() -> list[str]:
    exe = os.environ.get("STUDIO_CHROME")
    if not exe:
        for cand in ("/opt/pw-browsers/chromium-1243/chrome-linux64/chrome", "/usr/bin/google-chrome"):
            if Path(cand).exists():
                exe = cand
                break
    return [f"--browser-executable={exe}"] if exe else []


def _remotion_render(comp: str, out: Path, props: dict):
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["npx", "remotion", "render", comp, str(out), f"--props={json.dumps(props, ensure_ascii=False)}",
           "--log=error", *_browser()]
    subprocess.run(cmd, cwd=REMOTION_DIR, check=True, timeout=900)


def _normalize(src: Path, dst: Path, w: int, h: int):
    """Re-encode with exactly the episode's video parameters so the concat demuxer can stream-copy."""
    subprocess.run([config.ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(src), "-an",
                    "-vf", f"scale={w}:{h},fps={config.FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-g", str(config.FPS * 2), str(dst)], check=True)


def package_long_episode(master: Path, work: Path, series_title: str, episode_label: str, episode_title: str,
                         next_title: str, music_wav: Path | None = None) -> float:
    """Wrap `master` (in place) with intro + end screen. Returns the time offset added at the start."""
    pk = work / "packaging"
    pk.mkdir(parents=True, exist_ok=True)
    # background for the end screen: a frame from 60% into the episode
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(master)], capture_output=True, text=True, check=True).stdout.strip())
    bg = REMOTION_DIR / "public" / "endscreen_bg.png"
    subprocess.run([config.ffmpeg_bin(), "-y", "-loglevel", "error", "-ss", f"{dur * 0.6:.2f}", "-i", str(master),
                    "-frames:v", "1", str(bg)], check=True)
    _remotion_render("Intro", pk / "intro_raw.mp4",
                     {"seriesTitle": series_title, "episodeLabel": episode_label, "episodeTitle": episode_title})
    _remotion_render("EndScreen", pk / "end_raw.mp4",
                     {"seriesTitle": series_title, "nextTitle": next_title, "backgroundImage": "endscreen_bg.png"})
    _normalize(pk / "intro_raw.mp4", pk / "intro.mp4", 1920, 1080)
    _normalize(pk / "end_raw.mp4", pk / "end.mp4", 1920, 1080)
    # video: stream copy concat
    subprocess.run([config.ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(master), "-an", "-c", "copy",
                    str(pk / "main.mp4")], check=True)
    (pk / "list.txt").write_text("file 'intro.mp4'\nfile 'main.mp4'\nfile 'end.mp4'\n")
    # audio: short sting under the intro, episode mix, music bed under the end screen
    audio_end = music_wav if music_wav and music_wav.exists() else None
    a_inputs = ["-f", "lavfi", "-t", f"{INTRO_S}", "-i", "sine=frequency=660:sample_rate=48000",
                "-i", str(master)]
    if audio_end:
        a_inputs += ["-i", str(audio_end)]
    else:
        a_inputs += ["-f", "lavfi", "-t", f"{END_S}", "-i", "anullsrc=r=48000:cl=stereo"]
    fc = (f"[0:a]volume=0.12,afade=t=in:d=0.3,afade=t=out:st={INTRO_S - 1.2}:d=1.2,aformat=channel_layouts=stereo[a0];"
          f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo[a1];"
          f"[2:a]atrim=0:{END_S},afade=t=in:d=1,afade=t=out:st={END_S - 2}:d=2,aformat=sample_rates=48000:channel_layouts=stereo[a2];"
          f"[a0][a1][a2]concat=n=3:v=0:a=1[a]")
    subprocess.run([config.ffmpeg_bin(), "-y", "-loglevel", "error", *a_inputs, "-filter_complex", fc,
                    "-map", "[a]", "-c:a", "aac", "-b:a", "192k", str(pk / "audio.m4a")], check=True)
    out = pk / "packaged.mp4"
    subprocess.run([config.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(pk / "list.txt"), "-i", str(pk / "audio.m4a"), "-map", "0:v", "-map", "1:a",
                    "-c", "copy", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    out.replace(master)
    return INTRO_S
