# CropBot — Raspberry Pi code

This code runs on the Raspberry Pi 4. At each plant station:

1. The Arduino Nano sends `SCAN <station> <side>` over USB.
2. The Pi takes 3 quick photos with the USB side camera and replies `CAPTURED`.
3. In the background, the AI model checks the photos. A disease only counts if at least 2 of the 3 photos agree with ≥ 75% confidence; otherwise the plant is reported healthy.
4. The result + photo is sent to the farmer dashboard over WiFi. If the WiFi drops, results wait on the Pi and are sent when it's back.

Messages between the Nano and the Pi are described in [`../PROTOCOL.md`](../PROTOCOL.md).

---

## Setup guide (Yousef)

You do steps A and B **once, at home, with internet**. Copy-paste the commands exactly.

### A. Prepare the Pi's SD card (skip if the Pi already runs 64-bit Raspberry Pi OS)

1. On a laptop, install **Raspberry Pi Imager** (raspberrypi.com/software).
2. Choose: Device **Raspberry Pi 4** → OS **Raspberry Pi OS (64-bit)** → your SD card.
3. Click **Edit settings** before writing:
   - set a username + password (write them down),
   - add your home WiFi **and** the phone hotspot you'll use at the booth,
   - under *Services*, tick **Enable SSH**.
4. Write the card, put it in the Pi, power on, wait ~2 minutes.

You can type commands either with a keyboard + monitor on the Pi, or from a laptop on the same WiFi: `ssh <username>@<pi-name>.local`.

### B. Install CropBot

```bash
sudo apt-get install -y git
git clone https://github.com/ms7ah/cropbot.git
cd cropbot/pi
./install.sh
sudo reboot
```

`install.sh` installs everything, tests the AI model (you should see **SELF-TEST PASSED** with a speed per photo), and makes CropBot **start by itself every time the Pi powers on**. No keyboard or screen is needed on the robot after this.

---

## Testing, step by step

Stop the auto-started copy first, so the camera and USB port are free:

```bash
cd ~/cropbot/pi
sudo systemctl stop cropbot
```

**Test 1 — No camera, no Nano.** Open two terminals on the Pi.

Terminal 1 (a stand-in dashboard that saves every result as a photo with boxes):
```bash
cd ~/cropbot/pi && .venv/bin/python tools/fake_dashboard.py
```
Terminal 2:
```bash
cd ~/cropbot/pi && .venv/bin/python -m cropbot_pi --keyboard --fake-camera samples --dashboard http://localhost:8000
```
Type `SCAN 1 A`, Enter, then `SCAN 1 B`. Terminal 1 should print a result for each, and the photos appear in `received/`. Ctrl+C to stop both.

**Test 2 — Real camera, no Nano.** Same as Test 1, but without `--fake-camera samples`. Hold a leaf in front of the camera and type `SCAN 1 A`. Check the saved photo in `received/` is sharp and shows the leaf. If the wrong camera opens, change `camera_index` in `config.yaml`.

**Test 3 — Everything.** Plug in the Nano and the camera and run:
```bash
.venv/bin/python -m cropbot_pi --dashboard http://localhost:8000 --verbose
```
(still with the fake dashboard in Terminal 1). Drive the robot over a station: you should see `SCAN` and `CAPTURED` lines, and results in Terminal 1.

When done testing, turn auto-start back on: `sudo systemctl start cropbot`.

---

## At the booth

1. The Pi and the dashboard laptop must be on the **same WiFi** (the phone hotspot).
2. Put the laptop's address in `config.yaml` (it's shown on the dashboard's Settings page):
   ```bash
   nano ~/cropbot/pi/config.yaml        # edit dashboard_url, Ctrl+O Enter to save, Ctrl+X to exit
   sudo systemctl restart cropbot
   ```
3. Watch the robot's brain live: `journalctl -u cropbot -f`

## Getting new code

Whenever Mu'men says there's an update:
```bash
cd ~/cropbot/pi && ./update.sh
```

## Useful commands

| What | Command |
|---|---|
| See what it's doing live | `journalctl -u cropbot -f` |
| Restart | `sudo systemctl restart cropbot` |
| Stop / start | `sudo systemctl stop cropbot` / `sudo systemctl start cropbot` |
| Is it running? | `systemctl status cropbot` |
| List cameras | `v4l2-ctl --list-devices` |
| Is the Nano plugged in? | `ls /dev/ttyUSB* /dev/ttyACM*` |
| Pi's IP address | `hostname -I` |

## Troubleshooting

| Problem | Fix |
|---|---|
| `Waiting for the Arduino Nano to be plugged in...` | Check the USB cable (some cables are charge-only). Run `ls /dev/ttyUSB* /dev/ttyACM*`. |
| `Permission denied: /dev/ttyUSB0` | You skipped the reboot after install. `sudo reboot`. |
| `Could not open camera 0` | Try `camera_index: 1` in `config.yaml`; check with `v4l2-ctl --list-devices`. |
| `Dashboard NOT reachable` | Laptop and Pi on the same WiFi? `dashboard_url` correct? Dashboard running? On Windows, allow port 8000 through the firewall. Results are kept and sent later, so nothing is lost. |
| `Device or resource busy` when testing | The auto-started copy is running: `sudo systemctl stop cropbot`. |
| Healthy leaf reported sick, or the opposite | Tell Mu'men. Every photo + raw score is saved in `captures/<date>/scans.csv` for tuning `confidence_threshold`. |

---

## Files

| Path | What |
|---|---|
| `config.yaml` | All settings (dashboard address, camera, threshold…) |
| `cropbot_pi/` | The program: `detector.py` (AI model), `camera.py`, `nano_link.py`, `pipeline.py` (3-photo voting), `uploader.py` (sending + offline queue), `__main__.py` |
| `models/cropbot_v3_ncnn/` | The trained disease model (YOLOv8n, NCNN format) |
| `tools/fake_dashboard.py` | Stand-in dashboard for testing |
| `tools/self_test.py` | Checks the model works and how fast |
| `samples/` | 5 public tomato leaf photos for testing (PlantVillage dataset, not our training data) |
| `captures/`, `queue/` | Created while running: saved photos + scores, and results waiting to upload |
