#!/usr/bin/env bash
set -euo pipefail

# Install Chromium and the corresponding driver if they are not already present.
if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1 && ! command -v google-chrome >/dev/null 2>&1; then
  apt-get update
  apt-get install -y chromium chromium-driver
fi

pip install --upgrade pip
pip install -r requirements.txt
