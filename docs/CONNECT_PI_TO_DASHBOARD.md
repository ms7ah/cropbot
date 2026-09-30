# Connecting the CropBot Pi to the dashboard

**For Rahaf & Farah.** Give this whole file to your Claude/ChatGPT and say:
*"Read this fully. It describes exactly how the robot's Raspberry Pi sends data. Help me make our dashboard receive it, step by step, and test it."*

Everything here is taken directly from the code running on the robot (github.com/ms7ah/cropbot, folder `pi/`). **The Pi code is frozen for the Expo. The dashboard adapts to the Pi, not the other way round.**

---

## 1. The big picture (read this first)

```
 ROBOT                                      YOUR LAPTOP
 ┌──────────────────────────┐   WiFi        ┌───────────────────────────┐
 │ Raspberry Pi             │  (same phone  │ Your dashboard server     │
 │  takes photos, runs AI,  │   hotspot)    │  listens on port 8000     │
 │  then SENDS results  ────┼──────────────▶│  POST /api/scan           │
 │                          │               │  POST /api/status         │
 │  live video on :8081 ◀───┼───────────────┤  <img src=".../stream">   │
 └──────────────────────────┘               └───────────────────────────┘
```

- **The Pi does the sending.** Your dashboard never asks the Pi for results; it just waits for them to arrive, like a mailbox.
- The Pi sends to **one address**, set in a settings file on the Pi called `dashboard_url`, e.g. `http://192.168.8.57:8000`. The Pi adds `/api/scan` and `/api/status` to the end of it.
- **Laptop and Pi must be on the same WiFi** (the phone hotspot). No internet is needed.
- The only thing the dashboard *pulls* from the Pi is the live camera video (Section 6).

---

## 2. What your dashboard server must do

Your server must accept **two HTTP POST requests with a JSON body**, at exactly these paths:

| Path | When the Pi sends it | What you must reply |
|---|---|---|
| `POST /api/scan` | Once per plant side (so twice per station: side A, then side B) | Any **2xx** (e.g. `200 {"ok": true}`) within **10 seconds** |
| `POST /api/status` | Every time the robot's state changes, **and every 5 seconds** as a heartbeat | Any 2xx within **3 seconds** (the Pi doesn't read the reply) |

**The paths must be exactly `/api/scan` and `/api/status`.** If your dashboard already uses different paths (like `/scan` or `/api/scans`), **add these two as extra routes** that call your existing code. Don't ask for the Pi to change.

### How the Pi reacts to your reply (important)

| Your server replies | What the Pi does |
|---|---|
| **2xx** | Deletes the scan from its queue. Done. |
| **4xx** (400, 404, 413, 422…) | Treats it as "the dashboard will never accept this". It **stops retrying** that scan and moves it to a `rejected` folder on the Pi, **so it never shows on your dashboard.** |
| **5xx** (500…) or no answer | Keeps the scan and **retries forever** (1 s, 2 s, 4 s… up to every 10 s), oldest first. |
| Can't connect at all | Same as 5xx: keeps everything and sends it when you're back. Nothing is lost. |

So **a 4xx is the one reply that loses data.** The usual causes:
- **413 "Payload Too Large".** Each scan carries a photo, so the body is about **40–120 KB**. Express's `express.json()` defaults to 100 KB. **Set it to at least 10 MB:** `app.use(express.json({ limit: "10mb" }))`. Flask, FastAPI and Next.js defaults are fine.
- **422/400 from strict validation.** Accept the fields in Section 3, allow `top` to be `null`, and **ignore extra fields** you don't use.
- **404.** Wrong path (see above).

---

## 3. The exact data

### 3.1 `POST /api/scan`

Header: `Content-Type: application/json`. Real example (the image is shortened here):

```json
{
  "scan_id": "3f1c2a9e-7b1d-4c55-9a0e-1a2b3c4d5e6f",
  "station_id": 3,
  "side": "A",
  "timestamp": "2026-10-01T10:15:32.120+03:00",
  "status": "diseased",
  "top": {
    "class_id": 3,
    "class_name": "MinerInitial",
    "disease": "Miner",
    "stage": "Initial",
    "confidence": 0.82
  },
  "detections": [
    {
      "class_id": 3,
      "class_name": "MinerInitial",
      "disease": "Miner",
      "stage": "Initial",
      "confidence": 0.82,
      "bbox": [0.31, 0.22, 0.58, 0.61]
    }
  ],
  "frames_agreeing": 2,
  "frames_total": 2,
  "confidence_threshold": 0.75,
  "image_jpeg_base64": "/9j/4AAQSkZJRgABAQAAAQABAAD...",
  "image_width": 640,
  "image_height": 480,
  "model_version": "cropbot-v3-yolov8n-ncnn",
  "inference_ms": 530,
  "marking_triggered": false
}
```

| Field | Type | Meaning / how to use it |
|---|---|---|
| `scan_id` | string (UUID) | Unique per scan. **The Pi can send the same scan twice after a WiFi hiccup: if you've already saved this `scan_id`, reply 200 and ignore it.** |
| `station_id` | integer 1, 2, 3… | Which plant station (counted by the robot). |
| `side` | `"A"` or `"B"` | Which side of the corridor. Show the farmer "left"/"right" (يسار/يمين). |
| `timestamp` | ISO 8601 string with timezone | When the photo was taken. |
| `status` | `"healthy"` or `"diseased"` | The verdict. **Healthy scans are sent too. Show them (green plant).** |
| `top` | object **or `null`** | The main finding. **`null` when healthy.** |
| `top.disease` | `"EarlyBlight"`, `"Miner"`, `"Fusarium"` | Show as Early Blight / Leaf Miner / Fusarium Wilt. |
| `top.stage` | `"Initial"`, `"Intermediate"`, `"Advanced"` | Show as Early stage / Spreading / Severe. |
| `top.class_name` | string | Combined name. **Note: class 1 is spelled `EarlyblightIntermediate` (lowercase b).** Use `disease` + `stage` instead of parsing this. |
| `top.confidence` | number 0–1 | Store it; don't show it to the farmer. |
| `detections` | list (empty `[]` when healthy) | One entry per box to draw on the photo. |
| `detections[].bbox` | `[x1, y1, x2, y2]`, numbers **0–1** | Box corners **as fractions of the image**. To draw: `left = x1 × displayedWidth`, `top = y1 × displayedHeight`, `width = (x2 − x1) × displayedWidth`, `height = (y2 − y1) × displayedHeight`. |
| `frames_agreeing`, `frames_total` | integers | How many photos agreed (2 or 3 photos per side). If `frames_agreeing ≥ 2`, you may show "Confirmed". |
| `image_jpeg_base64` | string | The photo, JPEG, base64, **without** a `data:` prefix. To show it: `<img src="data:image/jpeg;base64,${image_jpeg_base64}">`. Better: decode it and save it as a `.jpg` file on the laptop, then store the file path in your database. |
| `image_width`, `image_height` | integers | Photo size in pixels (normally 640 × 480). |
| `confidence_threshold`, `model_version`, `inference_ms`, `marking_triggered` | | Store or ignore. Don't show. |

### 3.2 `POST /api/status`

```json
{
  "state": "scanning",
  "station_id": 3,
  "side": "A",
  "timestamp": "2026-10-01T10:15:31.900+03:00",
  "message": ""
}
```

| Field | Values |
|---|---|
| `state` | `idle`, `scanning`, `flipping`, `driving`, `error` (also possible: `stopped`) |
| `station_id` | integer, or `null` (e.g. when `idle`) |
| `side` | `"A"`, `"B"` or `null` |
| `message` | usually `""`; text only when `state` is `error` (log it, show the farmer "The robot needs attention") |

What you'll actually see during a patrol:
```
idle → scanning (st 1, A) → flipping (st 1, A) → scanning (st 1, B) → driving (st 1) → scanning (st 2, A) → …
```
- The same status is **repeated every 5 s** (heartbeat) with a fresh `timestamp`.
- **Robot online/offline:** remember the time of the last `/api/status`. If nothing arrives for **15 s**, show "Robot offline".
- A scan's result arrives about 1–2 s **after** its `scanning` status, because the AI runs after the photo is taken.

---

## 4. Test your dashboard alone, without the robot (do this first)

This script sends **exactly what the Pi sends**. Save it on the laptop as `send_like_pi.py`, put any leaf photo next to it named `leaf.jpg`, start your dashboard, then run `python send_like_pi.py`. It needs only Python, no extra installs.

```python
import base64, json, time, uuid, urllib.request
from datetime import datetime

DASHBOARD = "http://localhost:8000"   # your dashboard address
img = base64.b64encode(open("leaf.jpg", "rb").read()).decode()

def post(path, data):
    req = urllib.request.Request(DASHBOARD + path, json.dumps(data).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        print(path, r.status, r.read()[:100])

now = lambda: datetime.now().astimezone().isoformat(timespec="milliseconds")

post("/api/status", {"state": "scanning", "station_id": 1, "side": "A", "timestamp": now(), "message": ""})
post("/api/scan", {
    "scan_id": str(uuid.uuid4()), "station_id": 1, "side": "A", "timestamp": now(),
    "status": "diseased",
    "top": {"class_id": 3, "class_name": "MinerInitial", "disease": "Miner", "stage": "Initial", "confidence": 0.82},
    "detections": [{"class_id": 3, "class_name": "MinerInitial", "disease": "Miner", "stage": "Initial",
                    "confidence": 0.82, "bbox": [0.31, 0.22, 0.58, 0.61]}],
    "frames_agreeing": 2, "frames_total": 2, "confidence_threshold": 0.75,
    "image_jpeg_base64": img, "image_width": 640, "image_height": 480,
    "model_version": "cropbot-v3-yolov8n-ncnn", "inference_ms": 530, "marking_triggered": False})
time.sleep(1)
post("/api/status", {"state": "flipping", "station_id": 1, "side": "A", "timestamp": now(), "message": ""})
post("/api/scan", {
    "scan_id": str(uuid.uuid4()), "station_id": 1, "side": "B", "timestamp": now(),
    "status": "healthy", "top": None, "detections": [],
    "frames_agreeing": 2, "frames_total": 2, "confidence_threshold": 0.75,
    "image_jpeg_base64": img, "image_width": 640, "image_height": 480,
    "model_version": "cropbot-v3-yolov8n-ncnn", "inference_ms": 510, "marking_triggered": False})
post("/api/status", {"state": "driving", "station_id": 1, "side": None, "timestamp": now(), "message": ""})
```

**Pass:** every line prints `200`, and the dashboard shows plant 1 side A as diseased (Leaf Miner, early stage, with a box on the photo) and side B as healthy. If you see `413`, `422`, `400` or `404`, fix it using Section 2 before going further. Those exact errors would lose real scans.

---

## 5. Connect the real robot (with Yousef, who has access to the Pi)

**Step 1: same WiFi.** Turn on the phone hotspot. Connect the laptop to it. The Pi joins it automatically.

**Step 2: start your dashboard so other devices can reach it.** It must listen on **`0.0.0.0`**, not `localhost`/`127.0.0.1` (those only accept connections from the laptop itself). Examples:
- FastAPI: `uvicorn main:app --host 0.0.0.0 --port 8000`
- Flask: `app.run(host="0.0.0.0", port=8000)`
- Node/Express: `app.listen(8000, "0.0.0.0")`
- Vite dev server: `npm run dev -- --host`

**Step 3: find the laptop's address on the hotspot.**
- Windows: open Command Prompt → `ipconfig` → under "Wireless LAN adapter Wi-Fi", the **IPv4 Address** (e.g. `192.168.8.57`)
- Mac: Terminal → `ipconfig getifaddr en0`

**Step 4: check from another device.** On a phone connected to the **same hotspot**, open `http://<laptop-ip>:8000`.
- If it loads, go to Step 5.
- If it doesn't load and the laptop is **Windows**, the firewall is blocking it. When Windows asks, click **"Allow access"** for private networks, or run this in **PowerShell as Administrator**:
  ```powershell
  New-NetFirewallRule -DisplayName "CropBot dashboard 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
  ```
  Also set the hotspot network to **Private** (Settings → Network → Wi-Fi → the hotspot → Private).

**Step 5: tell the Pi the address (Yousef).** From his Mac on the same hotspot:
```bash
ssh cropbot@cropbot.local
nano ~/cropbot-team/pi/config.yaml
```
Change the line to your laptop's address (keep the quotes, no `/` at the end):
```yaml
dashboard_url: "http://192.168.8.57:8000"
```
Save (**Ctrl+O**, Enter, **Ctrl+X**), then:
```bash
sudo systemctl restart cropbot
journalctl -u cropbot -f
```

**Step 6: test with the real Pi code but without driving (Yousef, optional but recommended).** This uses sample leaf photos and lets you type the robot's commands:
```bash
sudo systemctl stop cropbot
cd ~/cropbot-team/pi
.venv/bin/python -m cropbot_pi --keyboard --fake-camera samples
```
Type `SCAN 1 A`, Enter, then `SCAN 1 B`. Each should appear on the dashboard within a few seconds. Type `QUIT` when done, then `sudo systemctl start cropbot`.

**Step 7: real patrol.** Press the robot's START button and watch plants appear on the dashboard.

### What the Pi's log tells you (`journalctl -u cropbot -f`)

| Log line | Meaning | Fix |
|---|---|---|
| `Uploaded 3f1c2a9e (0 still waiting)` | ✅ Scan delivered | — |
| `Dashboard reachable` | ✅ Connection works (printed after the first successful scan) | — |
| `Dashboard NOT reachable (ConnectionError)` | The Pi can't reach the laptop | Wrong IP in `dashboard_url`, server not on `0.0.0.0`, Windows firewall, or not on the same hotspot. Scans are kept and sent later. |
| `Dashboard NOT reachable (ReadTimeout)` | The server took over 10 s to reply | Reply to `/api/scan` immediately; do slow work after replying. |
| `Dashboard rejected a scan (HTTP 413 …)` | Body too big for your server | Raise the JSON body limit to 10 MB (Section 2). |
| `Dashboard rejected a scan (HTTP 422/400 …)` | Your server refused the data | Loosen validation: allow `top: null`, ignore unknown fields. The text after the code says what your server complained about. |
| `Dashboard rejected a scan (HTTP 404 …)` | Wrong path | The server must have `POST /api/scan` exactly. |
| `Dashboard error HTTP 500; will retry` | Your server crashed on that scan | Check your server's error log. The Pi retries until it works. |

**Getting rejected scans back** after you fix a 4xx problem (Yousef, on the Pi):
```bash
cd ~/cropbot-team/pi && mv queue/rejected/*.json queue/ && sudo systemctl restart cropbot
```

---

## 6. Live camera video

The Pi serves live video itself. In the dashboard's camera panel:
```html
<img src="http://<pi-ip>:8081/stream" alt="CropBot live camera">
```
- Get `<pi-ip>` on the Pi with `hostname -I` (it was `192.168.8.248` on 29 Sep; it can change between hotspots). **Use the number, not `cropbot.local`:** Windows often can't find `.local` names.
- Test in a browser first: `http://<pi-ip>:8081/stream` should show live video. `http://<pi-ip>:8081/snapshot.jpg` shows a single photo.
- It's a normal image URL. No JavaScript or special library is needed, and it's already allowed to be embedded from another page (CORS is open).
- If the camera cable wiggles loose, the video shows a grey **"Camera reconnecting..."** image and recovers by itself.
- Put the Pi IP in your **Settings page**, so it can be changed at the booth without editing code.
- **Only works if your dashboard page is opened over `http://`, not `https://`.** Browsers block `http` video inside an `https` page.

---

## 7. Final checklist (all must be ✅ before the Expo)

- [ ] `send_like_pi.py` gets `200` on all lines, and the dashboard shows the diseased + healthy result correctly, with the box in the right place.
- [ ] Sending the **same** scan twice (same `scan_id`) shows it only once.
- [ ] A healthy scan (`top: null`, `detections: []`) displays without errors.
- [ ] Server started on `0.0.0.0:8000`; a phone on the hotspot can open `http://<laptop-ip>:8000`.
- [ ] `dashboard_url` on the Pi = the laptop's IP, and the log shows `Uploaded …` lines.
- [ ] "Robot offline" appears ~15 s after the Pi is turned off, and goes away when it's back.
- [ ] Live video shows in the camera panel.
- [ ] Write down on paper: the hotspot name/password, the laptop IP, the Pi IP, and the command that starts the dashboard.

**Don't change:** the Pi code, the data format above, or the paths `/api/scan` and `/api/status`.
