"""A tiny stand-in for the farmer dashboard, for testing the Pi on its own.

It accepts the same /api/scan and /api/status messages as the real
dashboard, prints each result, and saves every photo with its disease boxes
drawn on it into a folder (received/ by default).

Run on the Pi itself:     python tools/fake_dashboard.py
then start CropBot with:  python -m cropbot_pi --dashboard http://localhost:8000

Uses only Python's standard library + OpenCV (already installed for CropBot).
"""

from __future__ import annotations

import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REQUIRED = ["scan_id", "station_id", "side", "timestamp", "status", "top", "detections",
            "frames_agreeing", "frames_total", "confidence_threshold", "image_jpeg_base64",
            "image_width", "image_height", "model_version", "inference_ms", "marking_triggered"]
COLORS = {"Initial": (0, 191, 255), "Intermediate": (0, 128, 255), "Advanced": (0, 0, 230)}


class Handler(BaseHTTPRequestHandler):
    out_dir: Path
    seen: set[str] = set()
    last_state = None

    def log_message(self, *args):  # silence default access log
        pass

    def _reply(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            msg = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._reply(400, {"ok": False, "error": "not JSON"})

        if self.path == "/api/status":
            key = (msg.get("state"), msg.get("station_id"), msg.get("side"))
            if key != Handler.last_state:
                print(f"  status: {msg.get('state'):9s} station={msg.get('station_id')} "
                      f"side={msg.get('side')} {msg.get('message') or ''}", flush=True)
                Handler.last_state = key
            return self._reply(200, {"ok": True})

        if self.path == "/api/scan":
            missing = [k for k in REQUIRED if k not in msg]
            if missing:
                print(f"  !! scan missing fields: {missing}", flush=True)
                return self._reply(400, {"ok": False, "missing": missing})
            if msg["scan_id"] in Handler.seen:
                print(f"  (duplicate {msg['scan_id'][:8]} ignored)", flush=True)
                return self._reply(200, {"ok": True, "duplicate": True})
            Handler.seen.add(msg["scan_id"])
            top = msg["top"]
            result = (f"{top['disease']} / {top['stage']}  conf {top['confidence']:.2f}"
                      if top else "HEALTHY")
            path = self._save_image(msg)
            print(f"SCAN  station {msg['station_id']} side {msg['side']}: {result}  "
                  f"({msg['frames_agreeing']}/{msg['frames_total']} frames, "
                  f"{msg['inference_ms']} ms)  -> {path}", flush=True)
            return self._reply(200, {"ok": True})

        self._reply(404, {"ok": False})

    def _save_image(self, msg: dict) -> str:
        import cv2
        import numpy as np

        jpg = base64.b64decode(msg["image_jpeg_base64"])
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        for d in msg["detections"]:
            x1, y1, x2, y2 = d["bbox"]
            p1, p2 = (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))
            color = COLORS.get(d["stage"], (0, 0, 255))
            cv2.rectangle(img, p1, p2, color, 2)
            cv2.putText(img, f"{d['class_name']} {d['confidence']:.2f}", (p1[0], max(p1[1] - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        name = f"st{msg['station_id']}{msg['side']}_{msg['status']}_{msg['scan_id'][:8]}.jpg"
        path = self.out_dir / name
        cv2.imwrite(str(path), img)
        return str(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--out", default="received")
    args = ap.parse_args()
    Handler.out_dir = Path(args.out)
    Handler.out_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Fake dashboard listening on port {args.port}; saving photos to {Handler.out_dir}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
