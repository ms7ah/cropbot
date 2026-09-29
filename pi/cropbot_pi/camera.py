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
    """Keeps the newest camera frame in memory, and survives a flaky camera.

    - A corrupted frame (OpenCV 5 raises cv2.error for these) is skipped.
    - If no good frame arrives for STALE_S seconds, the camera is closed and
      reopened in a loop until it comes back (loose cable, USB power dip).
    - If the camera is unplugged at start-up, the service keeps running and
      keeps retrying instead of exiting.
    """

    STALE_S = 2.0

    def __init__(self, index: int | str = 0, width: int = 640, height: int = 480):
        self.index = index
        self.width = width
        self.height = height
        self._cap: cv2.VideoCapture | None = None
        self._frame: np.ndarray | None = None
        self._frame_no = 0
        self._frame_time = 0.0
        self._cond = threading.Condition()
        self._running = False
        self._thread: threading.Thread | None = None
        self._healthy: bool | None = None  # None = not seen yet

    def start(self) -> None:
        log.info("OpenCV %s", cv2.__version__)
        self._running = True
        self._thread = threading.Thread(target=self._reader, name="camera", daemon=True)
        self._thread.start()
        with self._cond:  # wait for a first frame, but never fail start-up over it
            self._cond.wait_for(lambda: self._frame_no > 0, timeout=10)
        if self._frame_no == 0:
            log.warning("Camera %s not working yet - will keep retrying in the background",
                        self.index)

    # ---- opening / closing (never raise) ---------------------------------
    def _try_open(self) -> bool:
        try:
            cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2) if isinstance(self.index, int) \
                else cv2.VideoCapture(self.index)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.index)  # OpenCV's default backend
            if not cap.isOpened():
                cap.release()
                return False
            # MJPG lets cheap USB cameras deliver full frame rate at 640x480
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._cap = cap
            return True
        except Exception as e:
            log.debug("Opening camera failed: %s", e)
            return False

    def _release(self) -> None:
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception:
            pass
        self._cap = None

    def _mark_lost(self, why: str) -> None:
        if self._healthy is not False:  # log once per outage
            if self._healthy is None:
                log.warning("Camera %s not found (%s). Is it plugged in? Retrying...",
                            self.index, why)
            else:
                log.warning("Camera LOST (%s) - reconnecting...", why)
            self._healthy = False

    # ---- reader thread ------------------------------------------------------
    def _reader(self) -> None:
        backoff = 0.5
        last_good = time.monotonic()
        while self._running:
            if self._cap is None:
                if self._try_open():
                    backoff = 0.5
                    last_good = time.monotonic()  # grace period for the first frame
                else:
                    self._mark_lost("cannot open")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 1.5)
                    continue
            try:
                ok, frame = self._cap.read()
            except Exception:  # e.g. cv2.error on a corrupted MJPEG frame
                ok, frame = False, None
            now = time.monotonic()
            if ok and frame is not None and frame.size:
                last_good = now
                if self._healthy is not True:
                    if self._healthy is None:
                        log.info("Camera %s ready (%dx%d)", self.index, frame.shape[1],
                                 frame.shape[0])
                    else:
                        log.info("Camera is BACK")
                    self._healthy = True
                with self._cond:
                    self._frame = frame
                    self._frame_no += 1
                    self._frame_time = now
                    self._cond.notify_all()
                continue
            if now - last_good > self.STALE_S:
                self._mark_lost("no frames")
                self._release()  # next loop reopens
                continue
            time.sleep(0.02)
        self._release()

    # ---- used by scans and the live stream -------------------------------------
    def frame_size(self) -> tuple[int, int]:
        with self._cond:
            if self._frame is None:
                return (self.width, self.height)
            h, w = self._frame.shape[:2]
            return (w, h)

    def latest(self) -> tuple[np.ndarray | None, int, float]:
        """Newest frame (a copy), its number, and its age in seconds."""
        with self._cond:
            if self._frame is None:
                return None, 0, float("inf")
            return self._frame.copy(), self._frame_no, time.monotonic() - self._frame_time

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
        self._release()


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
        self._last: np.ndarray | None = None
        self._last_no = 0

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
        self._last, self._last_no = frames[-1], self._last_no + 1
        return frames

    def latest(self) -> tuple[np.ndarray | None, int, float]:
        if self._last is None:  # show the first photo until the first scan
            self._last, self._last_no = cv2.imread(str(self.paths[0])), 1
        return self._last.copy(), self._last_no, 0.0

    def stop(self) -> None:
        pass
