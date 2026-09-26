#!/usr/bin/env bash
# One-time setup of CropBot on a Raspberry Pi (64-bit Raspberry Pi OS).
# Run from the pi/ folder:   ./install.sh
# Needs internet (do it at home, not at the booth). Safe to run again.
set -euo pipefail

PI_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(id -un)"
cd "$PI_DIR"

if [ "$USER_NAME" = "root" ]; then
  echo "Run this as your normal user (without sudo). It asks for your password when needed."
  exit 1
fi

echo "==> 1/5 Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip v4l-utils

echo "==> 2/5 Creating Python environment and installing libraries (a few minutes)"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> 3/5 Allowing access to the USB serial port and camera"
sudo usermod -aG dialout,video "$USER_NAME"

echo "==> 4/5 Testing the disease model"
.venv/bin/python tools/self_test.py

echo "==> 5/5 Making CropBot start automatically when the Pi turns on"
sudo tee /etc/systemd/system/cropbot.service > /dev/null <<EOF
[Unit]
Description=CropBot Pi (camera + disease model + Nano link)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$PI_DIR
ExecStart=$PI_DIR/.venv/bin/python -m cropbot_pi
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable cropbot

cat <<'EOF'

==========================================================
 Install finished.
 1. Reboot once so the port permissions apply:  sudo reboot
 2. After reboot CropBot runs by itself. Watch it live:
      journalctl -u cropbot -f
 Full guide: pi/README.md
==========================================================
EOF
