#!/usr/bin/env bash
# Get the newest CropBot code from GitHub and restart it.
# Run from the pi/ folder:   ./update.sh
# Your own edits to config.yaml (e.g. dashboard_url) are kept.
set -euo pipefail
cd "$(dirname "$0")"

SAVED=""
if ! git diff --quiet -- config.yaml; then
  SAVED="$(mktemp)"
  cp config.yaml "$SAVED"
  git checkout -- config.yaml
  echo "==> Keeping your config.yaml edits"
fi

echo "==> Downloading latest code"
if ! git pull --ff-only; then
  [ -n "$SAVED" ] && cp "$SAVED" config.yaml
  echo "!! Update failed (see above). Nothing was changed. Send Mu'men a screenshot."
  exit 1
fi
if [ -n "$SAVED" ]; then
  cp "$SAVED" config.yaml
  rm -f "$SAVED"
  echo "   (New settings added upstream use their defaults unless you add them to config.yaml.)"
fi

echo "==> Updating libraries (if anything changed)"
.venv/bin/pip install -q -r requirements.txt
echo "==> Restarting CropBot"
sudo systemctl restart cropbot
sleep 3
sudo systemctl --no-pager --lines=5 status cropbot || true
echo "Done. Watch it live with:  journalctl -u cropbot -f"
