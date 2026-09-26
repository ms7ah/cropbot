"""Quick check that the disease model works on this machine, and how fast it is.

    python tools/self_test.py            (uses the photos in samples/)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

PI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PI_DIR))

from cropbot_pi.detector import Detector  # noqa: E402


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else PI_DIR / "samples"
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not images:
        sys.exit(f"No images in {folder}")

    t0 = time.perf_counter()
    det = Detector(PI_DIR / "models" / "cropbot_v3_ncnn")
    print(f"Model loaded in {time.perf_counter() - t0:.1f} s")
    det.detect(cv2.imread(str(images[0])), 0.25)  # warm-up

    times = []
    for p in images:
        dets, ms = det.detect(cv2.imread(str(p)), 0.25)
        times.append(ms)
        best = f"{dets[0].class_name} {dets[0].confidence:.2f}" if dets else "nothing above 0.25"
        print(f"  {p.name:20s} {ms:6.0f} ms   {best}")
    print(f"\nAverage {sum(times) / len(times):.0f} ms per photo. SELF-TEST PASSED")


if __name__ == "__main__":
    main()
