"""Frame sources for Mode 1 (08_MODE1_LIVE.md §2). The monitor asks for the latest frame on every tick: no queues.

- `replay`: a folder of images played in file-name order, one per tick (development, tuning, demo).
- `p1s`: the P1S chamber camera, TLS on port 6000 (LAN-only + Developer Mode, community-documented protocol).
- `url`: an HTTP endpoint that returns one JPEG (phone IP-webcam apps, snapshot endpoints).
"""
from __future__ import annotations

import io
import socket
import ssl
import struct
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from printloop.detector import frame_id
from printloop.models import now_iso

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class Frame:
    jpeg: bytes
    id: str
    taken_at: str
    name: str = ""


def make_frame(data: bytes, name: str = "") -> Frame:
    if not data.startswith(b"\xff\xd8"):  # not a JPEG: convert, so every stored frame is a JPEG
        with Image.open(io.BytesIO(data)) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=95)
            data = buf.getvalue()
    return Frame(jpeg=data, id=frame_id(data), taken_at=now_iso(), name=name)


class ReplaySource:
    kind = "replay"

    def __init__(self, folder: str | Path):
        self.folder = Path(folder).expanduser()
        if not self.folder.is_dir():
            raise ValueError(f"replay folder not found: {self.folder}")
        self.files = sorted(p for p in self.folder.iterdir() if p.suffix.lower() in IMAGE_EXT)
        if not self.files:
            raise ValueError(f"no images in {self.folder}")
        self.index = 0

    @property
    def detail(self) -> str:
        return str(self.folder)

    @property
    def exhausted(self) -> bool:
        return self.index >= len(self.files)

    def latest(self) -> Frame | None:
        if self.exhausted:
            return None
        path = self.files[self.index]
        self.index += 1
        return make_frame(path.read_bytes(), path.name)

    def close(self) -> None:
        pass


# --- P1S chamber camera -------------------------------------------------------------------------------------

def p1s_auth_packet(access_code: str, user: str = "bblp") -> bytes:
    """16-byte header (0x40, 0x3000, 0, 0) + user and access code, each zero-padded to 32 bytes."""
    return struct.pack("<IIII", 0x40, 0x3000, 0, 0) + user.encode().ljust(32, b"\0") + access_code.encode().ljust(32, b"\0")


def _read_exact(sock, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("camera stream closed")
        buf += chunk
    return bytes(buf)


def p1s_read_frame(sock) -> bytes:
    """One frame: a 16-byte header whose first u32 LE is the payload size, then the JPEG."""
    header = _read_exact(sock, 16)
    size = struct.unpack_from("<I", header)[0]
    if not 0 < size < 10_000_000:
        raise ValueError(f"implausible frame size {size}")
    data = _read_exact(sock, size)
    if not (data.startswith(b"\xff\xd8") and data.rstrip(b"\0").endswith(b"\xff\xd9")):
        raise ValueError("frame is not a JPEG")
    return data


class P1SCameraSource:
    """Keeps a TLS connection to the printer and overwrites one "latest frame" slot (~0.5–1 fps)."""
    kind = "p1s"

    def __init__(self, ip: str, access_code: str, port: int = 6000):
        if not ip or not access_code:
            raise ValueError("P1S camera: set PRINTER_IP and PRINTER_ACCESS_CODE (LAN-only + Developer Mode)")
        self.ip, self.access_code, self.port = ip, access_code, port
        self._latest: Frame | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.error = ""
        self._thread = threading.Thread(target=self._run, name="p1s-camera", daemon=True)
        self._thread.start()

    @property
    def detail(self) -> str:
        return f"{self.ip}:{self.port}"

    exhausted = False

    def _run(self) -> None:
        # The printer's certificate is self-signed: verification is off on this LAN link; the access code still applies.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        backoff = 1.0
        while not self._stop.is_set():
            try:
                with socket.create_connection((self.ip, self.port), timeout=10) as raw, \
                        ctx.wrap_socket(raw, server_hostname=self.ip) as sock:
                    sock.sendall(p1s_auth_packet(self.access_code))
                    backoff = 1.0
                    while not self._stop.is_set():
                        frame = make_frame(p1s_read_frame(sock))
                        with self._lock:
                            self._latest = frame
                        self.error = ""
            except (OSError, ValueError, ConnectionError) as exc:
                self.error = str(exc)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)

    def latest(self) -> Frame | None:
        with self._lock:
            return self._latest

    def close(self) -> None:
        self._stop.set()


class SnapshotSource:
    kind = "url"
    exhausted = False

    def __init__(self, url: str):
        if not url:
            raise ValueError("snapshot source: set MODE1_SNAPSHOT_URL or pass a url")
        self.url = url
        self.error = ""

    @property
    def detail(self) -> str:
        return self.url

    def latest(self) -> Frame | None:
        try:
            with urllib.request.urlopen(self.url, timeout=5) as resp:  # noqa: S310 - operator-configured URL
                return make_frame(resp.read())
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            return None

    def close(self) -> None:
        pass


def open_source(kind: str, replay_dir: str | None = None, url: str | None = None, ip: str | None = None,
                access_code: str | None = None):
    if kind == "replay":
        return ReplaySource(replay_dir or "")
    if kind == "p1s":
        return P1SCameraSource(ip or "", access_code or "")
    if kind == "url":
        return SnapshotSource(url or "")
    raise ValueError(f"unknown frame source: {kind}")


def wait_first_frame(source, timeout_s: float = 5.0) -> None:
    """For live sources: give the reader a moment so the first tick has a frame."""
    deadline = time.monotonic() + timeout_s
    while source.latest() is None and time.monotonic() < deadline:
        time.sleep(0.2)
