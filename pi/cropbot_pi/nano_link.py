"""Text-line link to the Arduino Nano over USB serial.

Protocol (newline-terminated, see PROTOCOL.md at the repo root):
  Nano -> Pi : READY | SCAN <station> <side> | STATE <name> (optional)
  Pi -> Nano : CAPTURED <station> <side> | ERR <station> <side> <reason>

KeyboardLink offers the same interface but reads commands typed in the
terminal, so the Pi side can be tested without the Nano.
"""

from __future__ import annotations

import glob
import logging
import queue
import sys
import threading
import time

log = logging.getLogger(__name__)


def find_nano_port() -> str | None:
    """Arduino Nanos show up as ttyUSB* (CH340/FTDI clones) or ttyACM*."""
    ports = sorted(glob.glob("/dev/ttyUSB*")) + sorted(glob.glob("/dev/ttyACM*"))
    return ports[0] if ports else None


class NanoLink:
    def __init__(self, port: str = "auto", baud: int = 115200, ready_timeout: float = 4.0):
        self.port_setting = port
        self.baud = baud
        self.ready_timeout = ready_timeout
        self._ser = None
        self._buf = b""
        self._lock = threading.Lock()
        self._pending: str | None = None

    def connect(self) -> None:
        """Open the port, retrying forever (the Nano may be plugged in late)."""
        import serial  # imported here so keyboard mode works without pyserial

        warned = False
        while True:
            port = find_nano_port() if self.port_setting == "auto" else self.port_setting
            if port:
                try:
                    self._ser = serial.Serial(port, self.baud, timeout=0.1)
                    break
                except (serial.SerialException, OSError) as e:
                    log.warning("Could not open %s: %s", port, e)
            if not warned:
                log.warning("Waiting for the Arduino Nano to be plugged in...")
                warned = True
            time.sleep(2)

        log.info("Serial port %s opened at %d baud", self._ser.port, self.baud)
        # Opening the port resets most Nanos; give it time to boot and say READY.
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            line = self.read_line(timeout=0.2)
            if line == "READY":
                log.info("Nano says READY")
                return
            if line:
                self._pending = line  # something else arrived first; keep it
                log.info("Nano is already running (got %r before READY)", line)
                return
        log.info("No READY from Nano yet; continuing anyway")

    def read_line(self, timeout: float = 0.5) -> str | None:
        if self._pending is not None:
            line, self._pending = self._pending, None
            return line
        import serial

        deadline = time.monotonic() + timeout
        while True:
            if b"\n" in self._buf:
                raw, self._buf = self._buf.split(b"\n", 1)
                line = raw.decode("ascii", errors="replace").strip()
                if line:
                    log.debug("Nano -> Pi: %s", line)
                    return line
                continue
            if time.monotonic() >= deadline:
                return None
            try:
                chunk = self._ser.read(64)
            except (serial.SerialException, OSError) as e:
                log.error("Serial connection lost (%s); reconnecting", e)
                self._reconnect()
                return None
            if chunk:
                self._buf += chunk
                if len(self._buf) > 4096:  # garbage with no newlines; drop it
                    self._buf = b""

    def send(self, line: str) -> None:
        import serial

        with self._lock:
            try:
                self._ser.write((line + "\n").encode("ascii"))
                self._ser.flush()
                log.debug("Pi -> Nano: %s", line)
            except (serial.SerialException, OSError) as e:
                log.error("Could not send %r (%s)", line, e)

    def _reconnect(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass
        self._buf = b""
        time.sleep(1)
        self.connect()

    def close(self) -> None:
        if self._ser:
            self._ser.close()


class KeyboardLink:
    """Type Nano messages yourself, e.g.  SCAN 1 A  then  SCAN 1 B."""

    def __init__(self):
        self._q: queue.Queue[str] = queue.Queue()

    def connect(self) -> None:
        print(
            "\nKEYBOARD MODE - pretend to be the Arduino Nano.\n"
            "Type a command and press Enter, e.g.:\n"
            "   SCAN 1 A      (scan station 1, side A)\n"
            "   SCAN 1 B      (scan station 1, side B)\n"
            "Type QUIT (or press Ctrl+C) to stop.\n",
            flush=True,
        )
        threading.Thread(target=self._stdin_reader, daemon=True).start()

    def _stdin_reader(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if line:
                self._q.put(line.upper())
        self._q.put("QUIT")  # input ended (e.g. Ctrl+D)

    def read_line(self, timeout: float = 0.5) -> str | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def send(self, line: str) -> None:
        print(f"   [Pi -> Nano] {line}", flush=True)

    def close(self) -> None:
        pass
