#!/usr/bin/env bash
# Get the newest CropBot code from GitHub and restart it.
# Run from the pi/ folder:   ./update.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Downloading latest code"
git pull --ff-only
echo "==> Updating libraries (if anything changed)"
.venv/bin/pip install -q -r requirements.txt
echo "==> Restarting CropBot"
sudo systemctl restart cropbot
sleep 3
sudo systemctl --no-pager --lines=5 status cropbot || true
echo "Done. Watch it live with:  journalctl -u cropbot -f"
