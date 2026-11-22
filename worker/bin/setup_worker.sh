#!/usr/bin/env bash
# Installs everything the render worker needs on a fresh Ubuntu runner (GitHub Actions / Colab / RunPod CPU).
set -euo pipefail
cd "$(dirname "$0")/.."
if command -v apt-get >/dev/null; then
  sudo apt-get update -qq || true
  sudo apt-get install -y -qq ffmpeg libegl1 libgl1 fonts-dejavu-core unzip >/dev/null
fi
python -m pip install -q -r requirements.txt
mkdir -p .models
if [ ! -x .models/rhubarb/rhubarb ]; then
  curl -sL -o /tmp/rhubarb.zip https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.13.0/Rhubarb-Lip-Sync-1.13.0-Linux.zip
  unzip -q -o /tmp/rhubarb.zip -d /tmp/rhubarb
  mkdir -p .models/rhubarb && cp -r /tmp/rhubarb/Rhubarb-Lip-Sync-1.13.0-Linux/rhubarb /tmp/rhubarb/Rhubarb-Lip-Sync-1.13.0-Linux/res .models/rhubarb/
fi
python -c "from studio.tts import ensure_piper_model; ensure_piper_model('tr_TR-dfki-medium')"
echo "worker ready"
