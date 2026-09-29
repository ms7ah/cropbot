"""Live camera stream (MJPEG over HTTP) for the farmer dashboard.

    http://<pi>:8081/stream        live video, works in a plain <img src="...">
    http://<pi>:8081/snapshot.jpg  one current photo
    http://<pi>:8081/              a tiny test page

It never touches the camera itself: it re-uses the newest frame the camera
reader thread already keeps in memory, so scans are never delayed. One encoder
thread makes each JPEG once and shares it with every viewer, runs at low CPU
priority, and only works while someone is actually watching.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

log = logging.getLogger(__name__)

LOST_AFTER_S = 2.0  # no new camera frame for this long -> show "reconnecting"


def _placeholder(text: str, width: int = 640, height: int = 480) -> np.ndarray:
    img = np.full((height, width, 3), 90, np.uint8)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
    cv2.putText(img, text, ((width - tw) // 2, (height + th) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (235, 235, 235), 2, cv2.LINE_AA)
    return img


class LiveStream:
    def __init__(self, camera, port: int = 8081, fps: float = 5, quality: int = 70):
        self.camera = camera
        self.port = port
        self.interval = 1.0 / max(0.5, float(fps))
        self.quality = int(quality)
        self._jpeg: bytes | None = None
        self._seq = 0
        self._cond = threading.Condition()
        self._viewers = 0
        self._viewers_lock = threading.Lock()
        self._placeholders: dict[str, bytes] = {}

    # ---- encoder ----------------------------------------------------------------
    def _encode(self, img: np.ndarray) -> bytes | None:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        return buf.tobytes() if ok else None

    def _placeholder_jpeg(self, text: str) -> bytes:
        if text not in self._placeholders:
            w, h = self.camera.frame_size()
            self._placeholders[text] = self._encode(_placeholder(text, w, h)) or b""
        return self._placeholders[text]

    def _publish(self, jpeg: bytes) -> None:
        with self._cond:
            self._jpeg = jpeg
            self._seq += 1
            self._cond.notify_all()

    def _current_jpeg(self) -> bytes:
        frame, frame_no, age = self.camera.latest()
        if frame is None:
            return self._placeholder_jpeg("Camera starting...")
        if age > LOST_AFTER_S:
            return self._placeholder_jpeg("Camera reconnecting...")
        return self._encode(frame) or self._placeholder_jpeg("Camera reconnecting...")

    def _encoder(self) -> None:
        try:  # lower this thread's CPU priority so the disease model always wins
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
        except (AttributeError, OSError):
            pass
        last_no = -1
        last_sent = 0.0
        while True:
            time.sleep(self.interval)
            try:
                if self._viewers == 0:
                    continue  # nobody watching: no work at all
                frame, frame_no, age = self.camera.latest()
                now = time.monotonic()
                if frame is None or age > LOST_AFTER_S:
                    if now - last_sent >= 1.0:  # keep connections alive at 1 fps
                        text = "Camera starting..." if frame is None else "Camera reconnecting..."
                        self._publish(self._placeholder_jpeg(text))
                        last_sent = now
                    continue
                if frame_no == last_no:
                    continue
                jpeg = self._encode(frame)
                if jpeg:
                    self._publish(jpeg)
                    last_no, last_sent = frame_no, now
            except Exception:
                log.exception("Live stream encoder error (continuing)")
                time.sleep(1)

    # ---- HTTP -----------------------------------------------------------------------
    def _make_handler(self):
        stream = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # no per-request access log
                pass

            def _headers(self, content_type: str, length: int | None = None) -> None:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                if length is not None:
                    self.send_header("Content-Length", str(length))
                self.end_headers()

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                try:
                    if path == "/stream":
                        self._stream()
                    elif path == "/snapshot.jpg":
                        jpeg = stream._current_jpeg()
                        self._headers("image/jpeg", len(jpeg))
                        self.wfile.write(jpeg)
                    elif path == "/":
                        page = (b"<!doctype html><title>CropBot camera</title>"
                                b"<body style='margin:0;background:#111;display:grid;"
                                b"place-items:center;height:100vh'>"
                                b"<img src='/stream' style='max-width:100%'></body>")
                        self._headers("text/html; charset=utf-8", len(page))
                        self.wfile.write(page)
                    else:
                        self.send_error(404)
                except (BrokenPipeError, ConnectionResetError, socket.timeout):
                    pass  # viewer went away

            def _stream(self):
                self._headers("multipart/x-mixed-replace; boundary=frame")
                with stream._viewers_lock:
                    stream._viewers += 1
                try:
                    first = stream._current_jpeg()  # show something immediately
                    self._part(first)
                    seen = stream._seq
                    while True:
                        with stream._cond:
                            stream._cond.wait_for(lambda: stream._seq != seen, timeout=5)
                            if stream._seq == seen:
                                continue
                            seen, jpeg = stream._seq, stream._jpeg
                        if jpeg:
                            self._part(jpeg)
                finally:
                    with stream._viewers_lock:
                        stream._viewers -= 1

            def _part(self, jpeg: bytes) -> None:
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                self.wfile.flush()

        return Handler

    def start(self) -> None:
        try:
            server = ThreadingHTTPServer(("0.0.0.0", self.port), self._make_handler())
        except OSError as e:
            log.error("Live stream NOT started (port %d: %s). Everything else keeps working.",
                      self.port, e)
            return
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, name="stream-http", daemon=True).start()
        threading.Thread(target=self._encoder, name="stream-encoder", daemon=True).start()
        log.info("Live stream at http://%s:%d/stream", _local_ip(), self.port)


def _local_ip() -> str:
    """The Pi's address on the WiFi (what the dashboard laptop should use)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the WiFi interface
        return s.getsockname()[0]
    except OSError:
        return socket.gethostname() + ".local"
    finally:
        s.close()
