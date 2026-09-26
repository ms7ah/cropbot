"""Tomato leaf disease detector: runs the YOLOv8n model exported to NCNN.

Uses the ncnn Python package directly (no PyTorch / Ultralytics needed on the
Pi), so installation is light and start-up is fast. Pre- and post-processing
mirror what Ultralytics does for this model: letterbox to 640x640, RGB 0-1
input, then confidence filter + per-class non-maximum suppression.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import ncnn
import numpy as np

# Index order is fixed by training. Note the lowercase "b" in class 1: it is
# the real dataset label and must not be "corrected".
CLASS_NAMES = [
    "EarlyBlightInitial",
    "EarlyblightIntermediate",
    "EarlyBlightAdvanced",
    "MinerInitial",
    "MinerIntermediate",
    "MinerAdvanced",
    "FusariumInitial",
    "FusariumIntermediate",
    "FusariumAdvanced",
]
# class_id -> (disease, stage), as sent to the dashboard.
CLASS_PARTS = [
    ("EarlyBlight", "Initial"),
    ("EarlyBlight", "Intermediate"),
    ("EarlyBlight", "Advanced"),
    ("Miner", "Initial"),
    ("Miner", "Intermediate"),
    ("Miner", "Advanced"),
    ("Fusarium", "Initial"),
    ("Fusarium", "Intermediate"),
    ("Fusarium", "Advanced"),
]


@dataclass
class Detection:
    class_id: int
    confidence: float
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 normalised 0-1

    @property
    def class_name(self) -> str:
        return CLASS_NAMES[self.class_id]

    def to_dict(self) -> dict:
        disease, stage = CLASS_PARTS[self.class_id]
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "disease": disease,
            "stage": stage,
            "confidence": round(float(self.confidence), 4),
            "bbox": [round(float(v), 4) for v in self.bbox],
        }


def letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize keeping aspect ratio and pad to size x size (grey 114), centred."""
    h, w = image.shape[:2]
    scale = min(size / h, size / w)
    new_w, new_h = round(w * scale), round(h * scale)
    if (new_w, new_h) != (w, h):
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_x = (size - new_w) / 2
    pad_y = (size - new_h) / 2
    top, bottom = round(pad_y - 0.1), round(pad_y + 0.1)
    left, right = round(pad_x - 0.1), round(pad_x + 0.1)
    padded = cv2.copyMakeBorder(
        image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    return padded, scale, left, top


class Detector:
    def __init__(
        self,
        model_dir: str | Path,
        imgsz: int = 640,
        threads: int = 4,
        nms_iou: float = 0.7,
    ):
        model_dir = Path(model_dir)
        self.imgsz = imgsz
        self.nms_iou = nms_iou
        self.net = ncnn.Net()
        self.net.opt.num_threads = threads
        self.net.opt.use_vulkan_compute = False
        if self.net.load_param(str(model_dir / "model.ncnn.param")) != 0:
            raise RuntimeError(f"Could not load model.ncnn.param from {model_dir}")
        if self.net.load_model(str(model_dir / "model.ncnn.bin")) != 0:
            raise RuntimeError(f"Could not load model.ncnn.bin from {model_dir}")

    def raw_output(self, image_bgr: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        padded, scale, left, top = letterbox(image_bgr, self.imgsz)
        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        chw = np.ascontiguousarray(rgb.transpose(2, 0, 1), dtype=np.float32) / 255.0
        with self.net.create_extractor() as ex:
            ex.input("in0", ncnn.Mat(chw).clone())
            _, out = ex.extract("out0")
        # (4 + num_classes, anchors): cx, cy, w, h in letterboxed pixels, then scores
        return np.array(out), scale, left, top

    def detect(self, image_bgr: np.ndarray, conf: float) -> tuple[list[Detection], float]:
        """Return detections at or above `conf`, plus inference time in ms."""
        t0 = time.perf_counter()
        out, scale, left, top = self.raw_output(image_bgr)
        ms = (time.perf_counter() - t0) * 1000

        h, w = image_bgr.shape[:2]
        preds = out.T  # (anchors, 4 + classes)
        scores = preds[:, 4:]
        class_ids = scores.argmax(axis=1)
        confs = scores[np.arange(len(scores)), class_ids]
        keep = confs >= conf
        if not keep.any():
            return [], ms
        boxes, confs, class_ids = preds[keep, :4], confs[keep], class_ids[keep]

        # centre-xywh (letterboxed) -> x1y1x2y2 in original image pixels
        x1 = (boxes[:, 0] - boxes[:, 2] / 2 - left) / scale
        y1 = (boxes[:, 1] - boxes[:, 3] / 2 - top) / scale
        x2 = (boxes[:, 0] + boxes[:, 2] / 2 - left) / scale
        y2 = (boxes[:, 1] + boxes[:, 3] / 2 - top) / scale
        xyxy = np.stack([x1, y1, x2, y2], axis=1)
        xyxy[:, [0, 2]] = xyxy[:, [0, 2]].clip(0, w)
        xyxy[:, [1, 3]] = xyxy[:, [1, 3]].clip(0, h)

        detections: list[Detection] = []
        for cid in np.unique(class_ids):  # per-class NMS, like Ultralytics
            idx = np.where(class_ids == cid)[0]
            rects = [
                [float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])]
                for b in xyxy[idx]
            ]
            kept = cv2.dnn.NMSBoxes(rects, confs[idx].tolist(), conf, self.nms_iou)
            for k in np.array(kept).flatten():
                i = idx[int(k)]
                bx = xyxy[i]
                detections.append(
                    Detection(
                        class_id=int(cid),
                        confidence=float(confs[i]),
                        bbox=(float(bx[0] / w), float(bx[1] / h), float(bx[2] / w), float(bx[3] / h)),
                    )
                )
        detections.sort(key=lambda d: -d.confidence)
        return detections, ms
