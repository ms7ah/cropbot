# CropBot 🌱🤖

An AI-powered ground robot that helps Jordanian smallholder farmers catch tomato leaf disease early.

CropBot drives along crop rows, photographs each plant from both sides, runs an on-board AI model to detect disease and how far it has progressed, and sends the results to a farmer dashboard in Arabic and English.

Built by team CropBot at Al-Hussein Technical University (HTU), Amman, Jordan, for AI Expo Jordan 2026 and the Ziad Al-Manaseer Innovative Research Award.

## How the prototype works

```
Arduino Nano ──USB──> Raspberry Pi 4 ──WiFi──> Farmer dashboard
(line-following,       (camera + YOLOv8n       (live field view,
 stops, camera flip)    disease model)          records, alerts)
```

At every plant station the robot stops, the Pi photographs and checks side A, the camera turns, the Pi checks side B, and the robot moves on.

## Repository layout

| Folder | What's inside | Owner |
|---|---|---|
| `pi/` | Python code running on the Raspberry Pi: camera, AI model, serial link, uploads | Mu'men Abu Hejla |
| `dashboard/` | Farmer web dashboard (backend + website) | Rahaf Albehari, Farah Ja'ara |
| `arduino/` | Arduino Nano code: line-following, station stops, camera servo | Yousef Albulbul |

## The AI model

YOLOv8n trained on the Mendeley Data dataset *Tomato Leaf Damage Progression* ([link](https://data.mendeley.com/datasets/s96sc8sh6y/1)). It detects 3 conditions (Early Blight, Leaf Miner, Fusarium Wilt) at 3 stages each (initial, intermediate, advanced), and runs on the Pi in NCNN format (`pi/models/cropbot_v3_ncnn/`).

## Team

Mu'men Abu Hejla (lead) · Yousef Albulbul · Osama Alzaben · Rahaf Albehari · Farah Ja'ara
