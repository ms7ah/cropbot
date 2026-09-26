# CropBot Farmer Dashboard — Project Brief for Claude

*Paste this whole document as the first message of a new Claude chat (or attach it and say "read this fully first"). It assumes you (Claude) know nothing about CropBot. Read all of it before writing any code, then follow "Your first steps" at the end.*

---

## 1. Who we are and what we're building

We are **Rahaf Albehari and Farah Ja'ara**, students at **Al-Hussein Technical University (HTU), Amman, Jordan**, on team **CropBot**. We own the **farmer dashboard** for our robot. You are helping us design and build it in **about 3 days**: the deadline is very tight.

**CropBot** is an AI-powered agricultural ground robot for Jordanian smallholder farmers (tomatoes and similar row crops). It drives along crop rows, photographs plant leaves, and uses an AI model to detect disease early. In the full product it also predicts which plants will get sick next and tells the farmer, in Arabic or English, what to do.

**The goal of the dashboard:** it must look and feel like a **real, finished product a farmer would use** — the app a farmer opens to see what their robot found today. It is **not** a technical/engineering dashboard. We'll show it live at **AI Expo Jordan 2026 on Thursday 1 October** (the ZM-RIA award readiness deadline is the same day), where the robot will drive a small demo corridor while this dashboard updates live. Judges should feel they're looking at a product that could ship, not a school project.

**Rule of thumb for every screen:** *"Would a tomato farmer understand this and know what to do next?"* If not, simplify it.

---

## 2. The team

- **Mu'men Abu Hejla** (team leader) — writes the **Python code on the Raspberry Pi** (camera, AI model, sending results to our dashboard). Working remotely from the UAE.
- **Yousef Albulbul** — Arduino Nano code (line-following, stopping, flipping the camera) and deploys Mu'men's code onto the Pi.
- **Osama Alzaben** — mechanical build.
- **Rahaf & Farah (us)** — the dashboard: the backend that receives the robot's data and the website the farmer sees.

---

## 3. Definition of done (read this twice)

When we hand the dashboard to Mu'men, it must be **complete and fully usable, with only one thing missing: the real robot plugged in.** That means:

1. **One command starts everything** (backend + website), on Windows and Mac, documented in a README with copy-paste steps a non-programmer could follow.
2. With `mock_pi.py` running (a script that pretends to be the robot, see Section 7), **every screen works end to end**: live updates, photos, history, export, alerts, both languages.
3. **The real Pi must work with zero changes on our side.** It sends exactly the JSON in Section 6; if the mock works, the robot works.
4. **Live camera panel** (Section 5, Tab 1): built and styled, showing a clean "Camera not connected" state until a stream URL is set in Settings. This is the *only* piece allowed to be unconnected.
5. No placeholder text, lorem ipsum, broken links, console errors, or dead buttons. Anything not finished is removed, not left half-working.
6. Delivered as a folder (zip or a GitHub repo — Mu'men will say which) with the README, `requirements.txt` / `package.json`, and a short `HANDOFF.md`: how to run it, how to point the Pi at it, what's configurable.

---

## 4. How the robot works (what data we receive)

At the Expo the robot drives a short **demo corridor** (~2–3 m). Real tomato leaves are mounted at **plant stations** on **both sides** of the corridor.

At every station:
1. The robot follows a line on the floor and **stops** at a marker line (a "station").
2. A side-facing camera takes photos of **side A**; the Pi's AI model checks them; the Pi **sends the result to our dashboard**.
3. The camera rotates to face **side B**; same thing again.
4. The robot drives on to the next station.

So we receive **two scan results per station** (side A and side B) and **status updates** about what the robot is doing (driving, scanning, etc.).

**What the model detects** — 3 conditions, each at 3 stages. The Pi sends `disease` and `stage` as separate fields; use these display names (have one of us, as native Arabic speakers, check every Arabic string):

| `disease` | English | Arabic |
|---|---|---|
| `EarlyBlight` | Early Blight | اللفحة المبكرة |
| `Miner` | Leaf Miner | حافرة الأوراق |
| `Fusarium` | Fusarium Wilt | ذبول الفيوزاريوم |

| `stage` | English (farmer wording) | Arabic |
|---|---|---|
| `Initial` | Early stage | مرحلة أولية |
| `Intermediate` | Spreading | مرحلة متوسطة |
| `Advanced` | Severe | مرحلة متقدمة |

Healthy = Healthy / سليم.

**No technical numbers on screen.** Farmers don't need confidence percentages, model names, accuracy, inference times, or thresholds. The payload contains some of these — **store them, don't display them**, except as described below. If you want to show certainty, use plain words only: **"Confirmed"** (when `frames_agreeing >= 2`) — nothing else.

---

## 5. The dashboard — screens

The feel: a premium farm-management app. Calm, confident, bilingual, instantly readable. A farmer (or a judge standing 2 metres away) should understand the home screen in **10 seconds**.

### Tab 1 — Today's Patrol (home screen)

1. **Robot status card (top):** big, friendly, animated state: *On the way to Plant 3 → Checking Plant 3 (left side) → Turning camera → Checking Plant 3 (right side) → Moving on*. A green "Online" dot (grey "Robot offline" after 15 s with no updates). Battery/field icons are fine as decoration only if they don't show fake numbers.
2. **Summary tiles:** Plants checked · Healthy · Need attention. Numbers tick up live.
3. **Field view (the centrepiece):** a top-down illustration of the crop rows — side A row above, side B row below, a small robot icon between them. The robot **glides to the current station**, its camera **visibly turns** when flipping sides, and each plant **fills in** when its result arrives: green = healthy; amber = early stage; orange = spreading; red = severe; grey = not checked yet. Tap a plant → its detail card. Number of stations is a setting (the real corridor size isn't fixed yet; default 4).
4. **Latest findings:** two large cards (left side / right side) showing the leaf photo with **our own drawn boxes** around the problem areas (the image arrives clean; `bbox` is given — see 6.1), the condition name, a stage badge, "Confirmed", and a **"What to do"** line.
5. **Live camera panel:** a tile labelled "Robot camera". Shows an MJPEG/HTTP stream if a URL is set in Settings; otherwise a tasteful "Camera not connected" state. (Mu'men may add a stream on the Pi later — it will be a plain URL like `http://<pi-ip>:8080/stream`, usable in an `<img>` tag.)
6. **Alert on the farmer's phone:** when a diseased plant is found, a realistic **phone mockup** beside the field view receives a push notification: *"⚠ Leaf Miner found — Plant 3, left side. Early stage. Tap for what to do."* (Arabic first when the site is in Arabic.) This shows what the farmer's phone would get.
7. **Activity feed:** a short, human-readable timeline ("10:15 — Plant 3 left side: healthy").

**"What to do" advice** — keep it general and safe. Example: *remove and destroy affected leaves, check neighbouring plants in the next few days, and contact an agricultural engineer before using any spray.* **No pesticide product names, no doses.** Keep all advice strings in one file so Mu'men can review them.

### Tab 2 — Plant Records

- A clean list of every plant checked (station, side, time, result, stage) with a thumbnail; filter by healthy/needs attention; tap → full photo with boxes.
- **"Download report"** button → CSV (and a printable page if time allows). In the product story this is the farmer's **traceability record** — proof for export buyers of what was found and when.
- Past patrols selectable ("Today", "Earlier patrols").
- **"Start new patrol"** button (clears the field view and archives the old one). We will press this between Expo visitors, so it must be one click and instant.

### Tab 3 — Outbreak Forecast (Predictive Epidemic Intelligence)

This is CropBot's most original feature: **predicting which healthy plants are likely to get sick next — before any symptoms show** (symptoms usually appear 2–3 weeks after infection). How it works, in farmer language:
1. Every disease the robot finds is marked on the field map.
2. Each healthy plant gets a **risk level**: higher if it's close to a sick plant, if the current weather (temperature and humidity) suits that disease, and if the finding is recent.
3. The robot **checks the highest-risk plants first** on its next patrol.
4. The farmer gets an **early warning** before the plant shows symptoms.

Mu'men built this already as two interactive web pages using a **simulated demo farm**: `small_field.html` (108 plants) and `large_field.html` (1,440 plants — a realistic Jordanian farm size). He'll give us both files.

Build this tab as:
- A short, beautiful 4-step explainer (icons + one line each, bilingual).
- The two pages **embedded** (iframe), with a toggle "Small plot / Full farm". Style the frame around them to match the rest of the dashboard.
- A small, tasteful badge on the embedded map: **"Demo farm — simulated data"** (our team's rule: anything simulated is labelled; keep it elegant, not alarming).

### Tab 4 — My Field (field setup)

In the full product, the farmer sets up their field once by **drawing its outline on a satellite map**, and CropBot plans its own route to cover every row. Build this as:
- A **satellite map** (Leaflet + Esri World Imagery tiles, with the required attribution) centred on a farming area in the **Jordan Valley**.
- The user **draws the field boundary** with the mouse/finger; the page instantly draws a **back-and-forth patrol route** filling the field (use Turf.js to clip evenly spaced parallel lines to the polygon and join them in a zig-zag), and shows the field area (dunums — 1 dunum = 1,000 m²) and route length.
- A small badge: **"Preview — automatic navigation arrives with the GPS model"** (the demo robot follows a floor line; this screen shows the product's setup flow).
- Satellite tiles need internet. If they fail to load, fall back to a plain map style or an included static field image — no broken grey squares.

### Everywhere

- **Arabic / English toggle** in the header. Arabic switches the whole layout to **right-to-left** (`dir="rtl"`), not just the words. All strings in one dictionary file. Arabic should be the default look-and-feel for the farmer story; English must be equally polished.
- **"Open on your phone": two QR codes** (a corner button that opens a panel). Step 1 joins the booth WiFi (the standard WiFi QR format `WIFI:T:WPA;S:<name>;P:<password>;;`, with name/password set in Settings). Step 2 opens the dashboard's local address. Phones must be on the booth hotspot to reach the laptop, since the dashboard is not on the internet.
- **Fullscreen / kiosk button** — the booth screen should look like an app, not a browser tab.
- **Settings page:** number of stations, camera stream URL, language default, the dashboard's current network address (so we can tell the Pi where to send data), and a **Demo mode** switch.
- **Demo mode:** generates realistic robot events in the correct order (so the dashboard can run without the robot, e.g. if the robot breaks at the booth). When on, show a small but clear **"Demo mode"** badge in the header — never let simulated scans be mistaken for real ones.
- **Responsive:** must look great on a laptop/TV at the booth **and** on a phone.

---

## 6. Data contract (what the Pi sends us — must match exactly)

The Pi sends HTTP POST requests with JSON. If we want a change, we agree it with Mu'men first.

### 6.1 `POST /api/scan` — one per side, two per station

```json
{
  "scan_id": "3f1c2a9e-7b1d-4c55-9a0e-1a2b3c4d5e6f",
  "station_id": 3,
  "side": "A",
  "timestamp": "2026-10-04T10:15:32.120+03:00",
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
  "frames_total": 3,
  "confidence_threshold": 0.75,
  "image_jpeg_base64": "<JPEG bytes, base64, no data: prefix>",
  "image_width": 640,
  "image_height": 480,
  "model_version": "cropbot-v3-yolov8n-ncnn",
  "inference_ms": 850,
  "marking_triggered": false
}
```

- `side`: `"A"` = left, `"B"` = right (show "left"/"right" — يسار/يمين — to the farmer).
- `status` is `"diseased"` or `"healthy"`. When healthy, `top` is `null` and `detections` is `[]`. **Healthy results always arrive and must be shown** (green plants matter as much as red ones).
- `bbox` is **normalized 0–1**: `[x1, y1, x2, y2]` as fractions of image width/height. Draw the boxes yourselves over the photo (canvas or positioned divs), in the stage colour.
- `confidence`, `confidence_threshold`, `model_version`, `inference_ms`: **store, don't display.**
- `scan_id` is unique. **The Pi may resend a scan after a network hiccup — ignore duplicates by `scan_id`.**
- Reply `200 {"ok": true}` immediately. Never make the Pi wait on anything slow.

### 6.2 `POST /api/status` — robot state + heartbeat

```json
{
  "state": "scanning",
  "station_id": 3,
  "side": "A",
  "timestamp": "2026-10-04T10:15:31.900+03:00",
  "message": ""
}
```

- `state`: `idle`, `driving`, `stopped`, `scanning`, `flipping`, `error`. Map these to friendly farmer wording (Tab 1).
- Sent on every change and every ~5 s as a heartbeat. Nothing for 15 s → "Robot offline".
- `side` may be `null`; `message` is optional (only for `error`; don't show raw error text to the farmer — show "The robot needs attention" and log the message).

### 6.3 Our own endpoints (for the website)
- `WebSocket /ws` — pushes each new scan/status to every open browser instantly.
- `POST /api/patrol/new` — archive current patrol, start a fresh one.
- `GET /api/patrols`, `GET /api/patrols/{id}/scans` — history.
- `GET /api/export.csv?patrol=<id>` — the report download.
- Accept requests from any origin (CORS open) — it's a local network demo.

---

## 7. Tech stack and running it (adjust to what we're comfortable with — ask us)

- **Backend:** Python **FastAPI** + Uvicorn, **SQLite** (data survives a restart), WebSocket push. Store images as files on disk, not inside the database.
- **Frontend:** React + Vite + Tailwind (or plain HTML/CSS/JS if we prefer — ask). Leaflet + Turf.js for Tab 4. **Build the frontend to static files served by FastAPI**, so the booth needs exactly one program running.
- **`mock_pi.py`:** sends realistic `/api/status` and `/api/scan` events in the correct loop order (status → scan A → flipping → scan B → driving → next station), a mix of healthy and diseased, with real leaf photos from a `samples/` folder and plausible bounding boxes. Configurable speed. **This is how we prove the dashboard works before the robot does.**
- **At the booth:** the dashboard runs on **our laptop**. The laptop and the Pi join the **same WiFi (a phone hotspot)**; the Pi posts to `http://<laptop-ip>:8000`. Handle these gotchas in the README:
  - Run with `--host 0.0.0.0` (not `localhost`) or the Pi can't reach it.
  - **Windows Firewall** blocks port 8000 by default — include the exact steps to allow it.
  - The laptop's IP changes between networks — show it on the Settings page so we can tell Mu'men/Yousef.
  - Bundle fonts and JS libraries locally where possible so the dashboard works **without internet** (only satellite tiles need it).

---

## 8. Visual design

- **Mood:** premium agritech product — calm, trustworthy, warm. Not a generic admin template, not a hackathon page.
- **Palette:** deep leaf green primary, warm sand/soil neutrals, off-white background (a dark mode is a bonus). Status: green healthy, amber early, orange spreading, red severe, grey unchecked. Always pair colour with an icon or word.
- **Typography:** a font that handles Arabic and Latin beautifully — **IBM Plex Sans Arabic**, **Cairo**, or **Tajawal**. Big, readable numbers.
- **Motion:** smooth and purposeful — robot gliding, plants filling in, cards sliding in, counters ticking, the phone notification sliding down. Nothing gimmicky.
- **Logo:** CropBot logo in the header (Mu'men will provide).
- **Tone of text:** short, reassuring, action-first. "2 plants need attention" beats "2 positive detections".

---

## 9. Priorities and timeline

Today is **Saturday 26 September 2026**. **The Expo is Thursday 1 October.** Robot dry runs with the dashboard: **Tuesday 29 and Wednesday 30 September**.

- **Tier 1 — by Sunday 27 Sep evening (Mu'men checks a screen recording; the Pi connects on Monday):** backend (both POST endpoints, WebSocket, SQLite, duplicate-ignoring, new patrol); `mock_pi.py`; Tab 1 (status card, tiles, field view, latest findings with boxes, activity feed); Arabic/English with RTL.
- **Tier 2 — by Monday 28 Sep evening:** Tab 2 with CSV; Tab 3 with the embedded pages; phone alert mockup; live camera panel; Settings + Demo mode; QR code; fullscreen; visual polish; README + HANDOFF.
- **Tier 3 — Tuesday 29 Sep, only if Tiers 1 and 2 are solid:** Tab 4 satellite field drawing; printable report; dark mode.

**Handoff to Mu'men: Tuesday 29 September evening**, meeting Section 3's definition of done. Wednesday 30 is the full rehearsal with the robot; no new features after that. If time is short, cut Tier 3 — a polished, reliable Tier 1+2 beats a broken Tier 3.

---

## 10. What we get from Mu'men

- `small_field.html` and `large_field.html` (outbreak forecast pages)
- The CropBot logo
- A handful of real tomato-leaf photos for `samples/` (until then, any tomato leaf photos, used only in mock/demo mode)
- Review of the "What to do" advice text

---

## 11. Your first steps (Claude)

1. Summarise what you understood in a few lines and ask anything unclear — **don't start coding if something important is ambiguous.**
2. Ask about our experience (React vs. plain JS, Python comfort, Windows or Mac) and adjust the stack.
3. Propose the folder structure and build order following Section 9.
4. Build Tier 1 starting with the backend + `mock_pi.py`, so data flows end to end on day one; then Tab 1.
5. At every step, tell us exactly how to run and test it. Keep the data contract (Section 6) exactly as written unless we tell you it changed.
