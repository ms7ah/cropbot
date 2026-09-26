"""Turns a burst of photos of one plant side into one dashboard result.

Each photo is checked by the model. A disease only counts if at least
`min_agree` photos show it at or above the confidence threshold - one lucky
or unlucky frame can't produce a false alarm on its own. If nothing reaches
agreement, the side is reported healthy.
"""

from __future__ import annotations

import base64
import csv
import logging
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .detector import Detection, Detector

log = logging.getLogger(__name__)

MODEL_VERSION = "cropbot-v3-yolov8n-ncnn"
LOG_FLOOR = 0.25  # confidences above this are logged, even if below the threshold


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class Pipeline:
    def __init__(
        self,
        detector: Detector,
        threshold: float,
        min_agree: int,
        captures_dir: Path | None,
    ):
        self.detector = detector
        self.threshold = threshold
        self.min_agree = min_agree
        self.captures_dir = captures_dir

    def process(self, station: int, side: str, frames: list[np.ndarray], captured_at: str) -> dict:
        per_frame: list[list[Detection]] = []
        confident: list[list[Detection]] = []
        times = []
        votes = Counter()  # one vote per class per frame
        for i, f in enumerate(frames):
            dets, ms = self.detector.detect(f, LOG_FLOOR)
            per_frame.append(dets)
            times.append(ms)
            conf_dets = [d for d in dets if d.confidence >= self.threshold]
            confident.append(conf_dets)
            for cid in {d.class_id for d in conf_dets}:
                votes[cid] += 1
            # Stop early once the answer can't change (saves ~1 s per side on the Pi):
            # a disease already has enough votes, or none can still reach enough.
            remaining = len(frames) - (i + 1)
            best = max(votes.values(), default=0)
            if best >= self.min_agree or best + remaining < self.min_agree:
                break
        frames = frames[: len(per_frame)]
        confirmed = {cid for cid, n in votes.items() if n >= self.min_agree}

        if confirmed:
            def best_conf(cid):
                return max(d.confidence for dets in confident for d in dets if d.class_id == cid)
            winner = max(confirmed, key=lambda c: (votes[c], best_conf(c)))
            # send the frame where the winning disease is seen most clearly
            best_i = max(
                range(len(frames)),
                key=lambda i: max((d.confidence for d in confident[i] if d.class_id == winner),
                                  default=0),
            )
            shown = [d for d in confident[best_i] if d.class_id in confirmed]
            top = max((d for d in shown if d.class_id == winner), key=lambda d: d.confidence)
            status, agreeing = "diseased", votes[winner]
        else:
            best_i = len(frames) // 2
            shown, top, status = [], None, "healthy"
            agreeing = sum(1 for dets in confident if not dets)

        image = frames[best_i]
        h, w = image.shape[:2]
        ok, jpg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("JPEG encoding failed")

        payload = {
            "scan_id": str(uuid.uuid4()),
            "station_id": station,
            "side": side,
            "timestamp": captured_at,
            "status": status,
            "top": None if top is None else {k: v for k, v in top.to_dict().items() if k != "bbox"},
            "detections": [d.to_dict() for d in shown],
            "frames_agreeing": agreeing,
            "frames_total": len(frames),
            "confidence_threshold": self.threshold,
            "image_jpeg_base64": base64.b64encode(jpg.tobytes()).decode("ascii"),
            "image_width": w,
            "image_height": h,
            "model_version": MODEL_VERSION,
            "inference_ms": round(sum(times) / len(times)),
            "marking_triggered": False,
        }

        summary = (f"{top.class_name} {top.confidence:.2f}" if top else "healthy")
        log.info("Station %d side %s -> %s (%d/%d frames agree, %.0f ms/frame)",
                 station, side, summary, agreeing, len(frames), payload["inference_ms"])
        if self.captures_dir:
            self._save(station, side, frames, per_frame, payload)
        return payload

    def _save(self, station, side, frames, per_frame, payload) -> None:
        """Keep photos + raw confidences so the threshold can be tuned later."""
        try:
            day = self.captures_dir / datetime.now().strftime("%Y-%m-%d")
            day.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%H%M%S")
            log_path = day / "scans.csv"
            new = not log_path.exists()
            with log_path.open("a", newline="") as fh:
                wr = csv.writer(fh)
                if new:
                    wr.writerow(["time", "station", "side", "frame", "file",
                                 "raw_detections", "result", "scan_id"])
                for i, (frame, dets) in enumerate(zip(frames, per_frame)):
                    name = f"{stamp}_st{station}{side}_f{i}.jpg"
                    cv2.imwrite(str(day / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    raw = "; ".join(f"{d.class_name}:{d.confidence:.3f}" for d in dets)
                    result = payload["top"]["class_name"] if payload["top"] else "healthy"
                    wr.writerow([payload["timestamp"], station, side, i, name, raw,
                                 result, payload["scan_id"]])
        except OSError as e:
            log.warning("Could not save capture: %s", e)
