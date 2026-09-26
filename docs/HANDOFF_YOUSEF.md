# CropBot — Handoff to Yousef (Pi + Nano)

*From Mu'men, 26 Sep 2026.*

**Yousef:** paste or attach this whole file in the Claude chat that already knows your robot progress, and send the message in Section 0.

---

## 0. What to ask your Claude

> Read this handoff from Mu'men fully. Then, using everything you know about what I've already built on the robot and the Pi:
> 1. Make a table: each item in Section 6 (the plan) → **Done / Partly done / Not started / Done differently**.
> 2. List every place where **what I built differs from Mu'men's plan** (Sections 3–5), and for each one say which is better for a reliable demo on 1 October and why. Don't assume Mu'men's plan wins automatically. If mine is better, say so.
> 3. List the **decisions I need to make** (Section 7), with your recommendation for each.
> 4. Give me my **next steps for today and tomorrow** in order, as copy-paste commands where possible.
> 5. Write a **short status message I can send back to Mu'men** (Section 8).

---

## 1. The situation

- **The AI Expo has moved to Thursday 1 October 2026.** That is the demo day, so we have about 4 working days. The ZM-RIA readiness deadline is the same day.
- Code freeze: **Wednesday 30 September evening.** After that, only fixes for real bugs.
- Mu'men is remote (UAE) and doesn't have the Pi. He and his Claude wrote the Pi software; **you** deploy and test it on the real robot.

## 2. Who does what

| Part | Job | Owner |
|---|---|---|
| **Arduino Nano** (or ESP32 if it works) | The "legs": line-following, stopping at the thick marker line, turning the camera servo, counting stations. Tells the Pi when to take photos. | Yousef |
| **Raspberry Pi 4** | The "eyes and brain": takes photos with the USB side camera, runs the disease model, sends results to the dashboard. Never drives the robot. | Code: Mu'men · Deploy/test: Yousef |
| **Dashboard** | The farmer website. Runs on Rahaf/Farah's **laptop** (not on the Pi). The Pi sends it results over WiFi. | Rahaf & Farah |
| **Chassis / mounts** | Body, camera + servo mount. | Osama |

Nano ⇄ Pi talk over the **USB cable** (serial, 115200 baud, text lines). Pi → laptop over **WiFi**: both join the same phone hotspot; internet not required.

## 3. What Mu'men built (GitHub: `github.com/ms7ah/cropbot`)

```
cropbot/
├── PROTOCOL.md          ← Nano ⇄ Pi messages + a minimal Arduino example. Read this for the Nano code.
├── pi/                  ← Everything that runs on the Pi
│   ├── README.md        ← Setup + testing guide (copy-paste commands)
│   ├── install.sh       ← One-time install: Python env, libraries, auto-start on boot
│   ├── update.sh        ← Pull the latest code + restart
│   ├── config.yaml      ← ALL settings (dashboard address, camera index, threshold…)
│   ├── cropbot_pi/      ← The program
│   ├── models/cropbot_v3_ncnn/   ← The trained model, already converted to NCNN (640 input)
│   ├── tools/fake_dashboard.py   ← Stand-in dashboard for testing (saves photos with boxes)
│   ├── tools/self_test.py        ← Checks the model runs + measures speed
│   └── samples/         ← 5 public leaf photos for testing without a camera
├── arduino/             ← Put your Nano code here
└── dashboard/           ← Rahaf & Farah's website will go here
```

**How the Pi program behaves:**
1. Starts automatically about 1 minute after the Pi powers on (systemd service `cropbot`). Nobody types anything.
2. Opens the Nano's USB port and waits for `READY`.
3. Waits for `SCAN <station> <side>`, e.g. `SCAN 3 A`.
4. Takes up to 3 fresh photos (a background thread always keeps the newest frame, so no stale or blurry buffered frames), then **immediately** replies `CAPTURED 3 A`. The Nano can flip the servo or drive on without waiting for the AI.
5. In the background, runs the model on the photos. A disease counts only if **2 photos agree** on the same class at or above the threshold; otherwise it's "healthy". It stops after 2 photos if they already agree.
6. Sends the result + photo to the dashboard. If WiFi or the dashboard is down, results wait on the SD card and are sent later.
7. Saves every photo + all raw scores in `pi/captures/<date>/scans.csv`, for tuning the threshold.

**Testing modes (no hardware needed):**
- `--keyboard`: you type `SCAN 1 A` yourself instead of the Nano
- `--fake-camera samples`: uses the sample photos instead of the camera
- `tools/fake_dashboard.py`: pretends to be the website

## 4. Nano ⇄ Pi protocol (full detail in `PROTOCOL.md`)

```
Nano → Pi:  READY                      once, at the end of setup()
Nano → Pi:  SCAN <station> <side>      after stopping; wait ~400 ms first so the robot stops shaking
Pi → Nano:  CAPTURED <station> <side>  photos taken → Nano may move the servo / drive
Pi → Nano:  ERR <station> <side> <why> photos failed → Nano carries on anyway
Nano → Pi:  STATE driving|stopped|idle|error    optional, for the dashboard
```
Rules:
- The Nano counts stations (1, 2, 3…) and sends the number.
- If no `CAPTURED` within 3 s, resend the same `SCAN` once, then move on regardless. Never freeze.
- A repeated `SCAN` for the same station/side is recognised by the Pi, so no duplicate photos.

## 5. Installing on the Pi

Your Pi is already set up (you log in as `cropbot@cropbot.local`), so skip the SD-card step. The code installs into **`~/cropbot-team`**, so **your existing `~/cropbot` folder is not touched**.

```bash
sudo apt-get install -y git
git clone https://github.com/ms7ah/cropbot.git ~/cropbot-team
cd ~/cropbot-team/pi
./install.sh
sudo reboot
```
Then follow **Tests 1–3** in `pi/README.md`.

**Important:** only one program can use the camera at a time. Stop your own camera script before running ours (and if yours starts automatically at boot, disable that).

## 6. The plan: what needs to be true by Wednesday evening

**Robot (Nano side)**
1. Line-following works on the demo corridor floor.
2. Stops reliably at each thick marker line, and only there.
3. Servo turns the camera cleanly between side A and side B (~180°).
4. Nano speaks the protocol in Section 4 (READY / SCAN / wait for CAPTURED / retry once).
5. A **START button**: the robot only starts driving when pressed. The Pi needs ~1 minute to boot; if the robot drives before that, the first station is missed.
6. Safe power: Pi on its own 5V 3A supply (power bank); motors on their own battery; servo **not** from the Nano's 5V pin (use a separate 5V supply); all grounds connected.

**Pi side**
7. Our repo installed; `tools/self_test.py` passes (note the "ms per photo" number).
8. Test 1 (keyboard + sample photos) works.
9. Test 2 (real camera): photos are sharp and show the whole leaf.
10. Test 3: Nano + Pi together over 2–3 stations; each shows SCAN → CAPTURED → result.
11. Connected to the real dashboard on the girls' laptop over the phone hotspot (`dashboard_url` in `config.yaml`).
12. **Confidence threshold decided from real tests** (see Section 7).
13. Working SD card backed up to a spare card.

## 7. Decisions for you (with Mu'men's current view)

1. **Your test script vs. this repo.** You already have inference running on the Pi (your screenshot: ~1.2 frames/s, continuous). Mu'men recommends running *this repo* for the demo, because it matches the dashboard's data format exactly and handles the Nano handshake, offline queue and auto-start. If your script has something better (e.g. camera settings that work well), tell Mu'men and it can be merged in.
2. **The confidence threshold. The biggest open question.** Your screenshot shows real-camera scores of mostly **0.53–0.77** for `EarlyBlightAdvanced`, rarely above 0.75. With the current setting (`confidence_threshold: 0.75` + 2 photos must agree), that leaf would usually be called *healthy*. Please test with:
   - a **diseased** leaf and a **healthy** leaf,
   - at the real distance and lighting,
   - and send Mu'men `pi/captures/<date>/scans.csv` plus the photos.

   Also tell Mu'men **which leaf** was in your screenshot (real diseased? which disease? or a screen/printout?). The threshold will probably come down (0.5–0.6 is likely), because the 2-photo agreement already protects against false alarms. But it must come from real numbers: a healthy leaf must not come out sick.
3. **ESP32 or Nano?** Whichever board works. The protocol is identical on either (both use the USB serial port).
4. **Camera distance and position**: whatever gives a sharp, well-lit leaf filling most of the photo.

## 8. What to send back to Mu'men

- The status table from your Claude (done / next / different).
- Self-test speed: "Average ___ ms per photo".
- Answers to Section 7, especially which leaf was in the screenshot.
- After real tests: `scans.csv` + a few photos from `captures/`.
- Any error: a screenshot of the terminal is enough. Mu'men fixes the code, pushes to GitHub, and you run `./update.sh`.

**Please don't change the message formats (Section 4) or the dashboard data** without telling Mu'men: three people's code depends on them.
