"""USB camera capture.

A background thread reads the camera continuously and keeps only the newest
frame. Without this, OpenCV hands back frames that were buffered while the
robot was still moving (blurry, or showing the previous plant).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


class Camera:
    def __init__(self, index: int | str = 0, width: int = 640, height: int = 480):
        self.index = index
        self.width = width
        self.height = height
        self._cap: cv2.VideoCapture | None = None
        self._frame: np.ndarray | None = None
        self._frame_no = 0
        self._cond = threading.Condition()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._open()
        self._running = True
        self._thread = threading.Thread(target=self._reader, name="camera", daemon=True)
        self._thread.start()
        # wait for the first frame so we know the camera really works
        self.burst(1, timeout=10)
        log.info("Camera %s ready (%dx%d)", self.index, *self.frame_size())

    def _open(self) -> None:
        cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2) if isinstance(self.index, int) \
            else cv2.VideoCapture(self.index)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.index)  # fall back to OpenCV's default backend
        if not cap.isOpened():
            raise RuntimeError(
                f"Could not open camera {self.index!r}. Is it plugged in? "
                "Try another camera_index in config.yaml (0, 1, 2...)."
            )
        # MJPG lets cheap USB cameras deliver full frame rate at 640x480
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap

    def _reader(self) -> None:
        failures = 0
        while self._running:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                failures += 1
                if failures in (10, 100) or failures % 500 == 0:
                    log.warning("Camera read failing (%d times); reopening", failures)
                    try:
                        self._cap.release()
                        time.sleep(0.5)
                        self._open()
                    except RuntimeError as e:
                        log.error("%s", e)
                time.sleep(0.02)
                continue
            failures = 0
            with self._cond:
                self._frame = frame
                self._frame_no += 1
                self._cond.notify_all()

    def frame_size(self) -> tuple[int, int]:
        with self._cond:
            if self._frame is None:
                return (self.width, self.height)
            h, w = self._frame.shape[:2]
            return (w, h)

    def burst(self, n: int, timeout: float = 3.0) -> list[np.ndarray]:
        """Return n frames that all arrived *after* this call started."""
        frames: list[np.ndarray] = []
        deadline = time.monotonic() + timeout
        with self._cond:
            last = self._frame_no
            while len(frames) < n:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
                if self._frame_no != last and self._frame is not None:
                    last = self._frame_no
                    frames.append(self._frame.copy())
        if not frames:
            raise RuntimeError("Camera gave no frames (unplugged or frozen?)")
        return frames

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap:
            self._cap.release()


class FakeCamera:
    """Serves images from a folder instead of a real camera (for testing
    without hardware). Each burst returns the next image, repeated n times
    with a little noise, like a real still scene."""

    def __init__(self, folder: str | Path, width: int = 640, height: int = 480):
        exts = {".jpg", ".jpeg", ".png", ".bmp"}
        self.paths = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in exts)
        if not self.paths:
            raise RuntimeError(f"No images found in {folder}")
        self.width, self.height = width, height
        self._i = 0
        self._rng = np.random.default_rng(0)

    def start(self) -> None:
        log.info("Using FAKE camera: %d images from %s", len(self.paths), self.paths[0].parent)

    def frame_size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def burst(self, n: int, timeout: float = 3.0) -> list[np.ndarray]:
        path = self.paths[self._i % len(self.paths)]
        self._i += 1
        img = cv2.imread(str(path))
        if img is None:
            raise RuntimeError(f"Could not read {path}")
        # keep the image's own shape (squashing it would change what the model sees)
        longest = max(img.shape[:2])
        if longest > 1280:
            s = 1280 / longest
            img = cv2.resize(img, (round(img.shape[1] * s), round(img.shape[0] * s)))
        frames = []
        for _ in range(n):
            noise = self._rng.normal(0, 2, img.shape)
            frames.append(np.clip(img + noise, 0, 255).astype(np.uint8))
        return frames

    def stop(self) -> None:
        pass
