#!/usr/bin/env bash
# Setup-Skript für die Claude-Cloud-Umgebung (läuft als root auf Ubuntu 24.04).
# In claude.ai/code -> Umgebung -> "Setup script" eintragen:  bash cloud/setup.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ffmpeg fonts-dejavu-core >/dev/null
python3 -m pip install -q --break-system-packages -U yt-dlp numpy
ffmpeg -version | head -1
yt-dlp --version
