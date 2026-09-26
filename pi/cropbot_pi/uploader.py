"""Sends results to the farmer dashboard.

Scans are written to a queue folder on disk first, then a background thread
posts them (oldest first) and deletes each one once the dashboard confirms.
If the WiFi or dashboard is down, scans wait in the folder and are sent when
it comes back - even after a reboot. The robot never waits on the network.

Status updates are "latest wins": only the current state matters, so they are
sent best-effort and repeated every few seconds as a heartbeat.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)


class Uploader:
    def __init__(self, dashboard_url: str, queue_dir: str | Path, heartbeat_s: float = 5.0):
        self.base = dashboard_url.rstrip("/") if dashboard_url else ""
        self.queue_dir = Path(queue_dir)
        self.failed_dir = self.queue_dir / "rejected"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.heartbeat_s = heartbeat_s
        self._wake = threading.Event()
        self._status: dict | None = None
        self._status_lock = threading.Lock()
        self._status_changed = threading.Event()
        self._running = False
        self._session = requests.Session()
        self._online: bool | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.base)

    def start(self) -> None:
        if not self.enabled:
            log.warning("No dashboard_url set: results are only saved on the Pi")
            return
        self._running = True
        threading.Thread(target=self._scan_worker, name="upload-scans", daemon=True).start()
        threading.Thread(target=self._status_worker, name="upload-status", daemon=True).start()
        pending = len(self._pending_files())
        log.info("Uploading to %s (%d scans waiting from before)", self.base, pending)

    # ---- scans ------------------------------------------------------------
    def queue_scan(self, payload: dict) -> None:
        name = f"{time.time_ns()}_{payload['scan_id']}.json"
        tmp = self.queue_dir / (name + ".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.rename(self.queue_dir / name)  # atomic: never a half-written file
        self._wake.set()

    def _pending_files(self) -> list[Path]:
        return sorted(self.queue_dir.glob("*.json"))

    def _scan_worker(self) -> None:
        backoff = 1.0
        while self._running:
            files = self._pending_files()
            if not files:
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            path = files[0]
            try:
                body = path.read_text()
                r = self._session.post(
                    f"{self.base}/api/scan", data=body,
                    headers={"Content-Type": "application/json"}, timeout=10,
                )
            except requests.RequestException as e:
                self._set_online(False, e)
                time.sleep(backoff)
                backoff = min(backoff * 2, 10)
                continue
            if 200 <= r.status_code < 300:
                path.unlink(missing_ok=True)
                self._set_online(True)
                backoff = 1.0
                log.info("Uploaded %s (%d still waiting)", path.stem.split("_", 1)[1][:8],
                         len(files) - 1)
            elif 400 <= r.status_code < 500:
                # The dashboard refused this scan; retrying won't help. Keep it for debugging.
                self.failed_dir.mkdir(exist_ok=True)
                path.rename(self.failed_dir / path.name)
                log.error("Dashboard rejected a scan (HTTP %d): %s. Saved in %s",
                          r.status_code, r.text[:200], self.failed_dir)
            else:
                log.warning("Dashboard error HTTP %d; will retry", r.status_code)
                time.sleep(backoff)
                backoff = min(backoff * 2, 10)

    # ---- status -----------------------------------------------------------
    def set_status(self, status: dict) -> None:
        with self._status_lock:
            self._status = status
        self._status_changed.set()

    def _status_worker(self) -> None:
        while self._running:
            self._status_changed.wait(timeout=self.heartbeat_s)
            self._status_changed.clear()
            with self._status_lock:
                status = dict(self._status) if self._status else None
            if not status:
                continue
            status["timestamp"] = _now_iso()  # heartbeat carries a fresh time
            try:
                self._session.post(f"{self.base}/api/status", json=status, timeout=3)
            except requests.RequestException:
                pass  # the scan worker reports connection problems

    def _set_online(self, online: bool, err: Exception | None = None) -> None:
        if online != self._online:
            if online:
                log.info("Dashboard reachable")
            else:
                log.warning("Dashboard NOT reachable (%s). Scans are kept and will be sent "
                            "when it is back.", type(err).__name__ if err else "")
            self._online = online

    def stop(self) -> None:
        self._running = False
        self._wake.set()
        self._status_changed.set()


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="milliseconds")
