"""CropBot Raspberry Pi main program.

    python -m cropbot_pi                      normal robot mode (Nano over USB)
    python -m cropbot_pi --keyboard           type SCAN commands yourself (no Nano)
    python -m cropbot_pi --fake-camera DIR    use photos from a folder (no camera)

A live camera stream runs at http://<pi>:8081/stream (see stream.py).

At each plant station the Nano sends "SCAN <station> <side>". The Pi grabs a
short burst of photos, immediately replies "CAPTURED <station> <side>" (so the
Nano can flip the camera / drive on right away), then checks the photos with
the disease model in the background and uploads the result.
"""

from __future__ import annotations

import argparse
import logging
import queue
import signal
import sys
import threading
import time
from pathlib import Path

import yaml

from .camera import Camera, FakeCamera
from .detector import Detector
from .nano_link import KeyboardLink, NanoLink
from .pipeline import Pipeline, now_iso
from .stream import LiveStream
from .uploader import Uploader

PI_DIR = Path(__file__).resolve().parent.parent  # the pi/ folder
log = logging.getLogger("cropbot")

REPEAT_WINDOW_S = 10  # a repeated SCAN for the same spot within this time = Nano resend
VALID_STATES = {"idle", "driving", "stopped", "scanning", "flipping", "error"}


def load_config(path: Path) -> dict:
    with path.open() as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg


class Robot:
    def __init__(self, cfg: dict, link, camera, pipeline: Pipeline, uploader: Uploader):
        self.cfg = cfg
        self.link = link
        self.camera = camera
        self.pipeline = pipeline
        self.uploader = uploader
        self.jobs: queue.Queue = queue.Queue()
        self.last_scan: tuple[int, str, float] | None = None
        self.station: int | None = None
        self.sides_done: set[str] = set()
        self.running = True

    def status(self, state: str, station: int | None = None, side: str | None = None,
               message: str = "") -> None:
        self.uploader.set_status({
            "state": state, "station_id": station, "side": side,
            "timestamp": now_iso(), "message": message,
        })

    def run(self) -> None:
        threading.Thread(target=self._worker, name="inference", daemon=True).start()
        self.status("idle")
        log.info("Waiting for SCAN commands from the Nano...")
        while self.running:
            line = self.link.read_line(timeout=0.5)
            if line:
                self.handle(line)

    def handle(self, line: str) -> None:
        parts = line.strip().split()
        cmd = parts[0].upper()
        if cmd == "READY":
            log.info("Nano (re)started")
            self.status("idle")
        elif cmd == "QUIT" and isinstance(self.link, KeyboardLink):
            self.running = False
        elif cmd == "SCAN":
            self.handle_scan(parts)
        elif cmd == "STATE" and len(parts) >= 2 and parts[1].lower() in VALID_STATES:
            self.status(parts[1].lower())
        else:
            log.warning("Ignoring unknown message from Nano: %r", line)

    def handle_scan(self, parts: list[str]) -> None:
        if len(parts) != 3 or not parts[1].isdigit() or parts[2].upper() not in ("A", "B"):
            log.warning("Bad SCAN message %r (expected e.g. 'SCAN 3 A')", " ".join(parts))
            return
        station, side = int(parts[1]), parts[2].upper()

        # The Nano resends SCAN if it missed our CAPTURED; don't photograph twice.
        if self.last_scan and self.last_scan[:2] == (station, side) \
                and time.monotonic() - self.last_scan[2] < REPEAT_WINDOW_S:
            log.info("Repeated SCAN %d %s - re-sending CAPTURED", station, side)
            self.link.send(f"CAPTURED {station} {side}")
            return

        self.status("scanning", station, side)
        captured_at = now_iso()
        try:
            frames = self.camera.burst(self.cfg.get("burst_frames", 3))
        except RuntimeError as e:
            log.error("Camera problem at station %d side %s: %s", station, side, e)
            self.link.send(f"ERR {station} {side} CAMERA")
            self.status("error", station, side, str(e))
            return

        self.link.send(f"CAPTURED {station} {side}")
        self.last_scan = (station, side, time.monotonic())
        if station != self.station:  # arrived at a new station
            self.station, self.sides_done = station, set()
        self.sides_done.add(side)
        if self.sides_done >= {"A", "B"}:
            self.status("driving", station, None)
        else:
            self.status("flipping", station, side)
        self.jobs.put((station, side, frames, captured_at))

    def _worker(self) -> None:
        while True:
            station, side, frames, captured_at = self.jobs.get()
            try:
                payload = self.pipeline.process(station, side, frames, captured_at)
                self.uploader.queue_scan(payload)
            except Exception:
                log.exception("Failed to process station %d side %s", station, side)
            finally:
                self.jobs.task_done()


def main() -> None:
    ap = argparse.ArgumentParser(description="CropBot Raspberry Pi program")
    ap.add_argument("--config", default=str(PI_DIR / "config.yaml"))
    ap.add_argument("--keyboard", action="store_true",
                    help="type SCAN commands in the terminal instead of using the Nano")
    ap.add_argument("--fake-camera", metavar="FOLDER",
                    help="use photos from FOLDER instead of the USB camera")
    ap.add_argument("--dashboard", metavar="URL", help="override dashboard_url from config")
    ap.add_argument("--verbose", action="store_true", help="show every serial message")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    cfg = load_config(Path(args.config))
    if args.dashboard is not None:
        cfg["dashboard_url"] = args.dashboard

    def resolve(p: str) -> Path:
        p = Path(p)
        return p if p.is_absolute() else PI_DIR / p

    log.info("CropBot Pi starting")
    detector = Detector(resolve(cfg.get("model_dir", "models/cropbot_v3_ncnn")),
                        imgsz=cfg.get("model_imgsz", 640), threads=cfg.get("model_threads", 4))
    log.info("Disease model loaded")

    if args.fake_camera:
        camera = FakeCamera(args.fake_camera)
    else:
        camera = Camera(cfg.get("camera_index", 0), cfg.get("camera_width", 640),
                        cfg.get("camera_height", 480))
    camera.start()
    if cfg.get("stream_enabled", True):
        LiveStream(camera, port=int(cfg.get("stream_port", 8081)),
                   fps=float(cfg.get("stream_fps", 5)),
                   quality=int(cfg.get("stream_jpeg_quality", 70))).start()

    pipeline = Pipeline(
        detector,
        threshold=float(cfg.get("confidence_threshold", 0.75)),
        min_agree=int(cfg.get("min_agree", 2)),
        captures_dir=resolve("captures") if cfg.get("save_captures", True) else None,
    )
    uploader = Uploader(cfg.get("dashboard_url", ""), resolve("queue"),
                        heartbeat_s=float(cfg.get("heartbeat_seconds", 5)))
    uploader.start()

    link = KeyboardLink() if args.keyboard else NanoLink(cfg.get("serial_port", "auto"),
                                                        int(cfg.get("serial_baud", 115200)))
    link.connect()

    robot = Robot(cfg, link, camera, pipeline, uploader)

    def shutdown(*_):
        log.info("Shutting down")
        robot.running = False

    signal.signal(signal.SIGTERM, shutdown)
    try:
        robot.run()
    except KeyboardInterrupt:
        shutdown()
    finally:
        # give queued photos a moment to finish processing
        deadline = time.monotonic() + 15
        while robot.jobs.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.2)
        camera.stop()
        link.close()
        uploader.stop()


if __name__ == "__main__":
    main()
