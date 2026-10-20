"""PC1715 R1715BT ROM loader. No checksum, readback, ACK or replay on upload."""

from __future__ import annotations

import math
import struct
import time

from ravi.transport import Transport

# Deliberately narrower than the ROM's >=0800h check. Preserve its copied code,
# stack/workspace and the upper memory region. End is exclusive.
LOAD_START = 0x4000
LOAD_END = 0xC000


class BootError(RuntimeError):
    pass


def positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def load_record(address: int, data: bytes) -> bytes:
    if not data or not LOAD_START <= address < address + len(data) <= LOAD_END:
        raise ValueError("nonempty payload must fit entirely in 4000h..BFFFh")
    return b"\x0a" + struct.pack("<HH", address, len(data)) + data


def run_record(entry: int) -> bytes:
    if not LOAD_START <= entry < LOAD_END:
        raise ValueError("entry must be in 4000h..BFFFh")
    return b"\xaa" + struct.pack("<H", entry)


class StockBoot:
    """Single-use bootstrap session. Failure after attach requires board reset.

    The caller owns transport and physical reset. Handshake retries only occur
    before receipt of 12 12; LOAD/EXEC are never retried automatically.
    """

    def __init__(self, transport: Transport, *, byte_delay: float = 0.002):
        if not math.isfinite(byte_delay) or byte_delay < 0:
            raise ValueError("byte_delay must be finite and nonnegative")
        self.transport = transport
        self.byte_delay = byte_delay
        self.state = "new"
        self.loaded: tuple[int, int] | None = None

    def handshake(self, timeout: float = 30.0, interval: float = 0.25) -> None:
        positive(timeout, "timeout")
        positive(interval, "interval")
        if self.state != "new":
            raise BootError("new session and board reset required")
        self.state = "failed"
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            self.transport.write(b"\x11\x11")
            until = min(deadline, time.monotonic() + interval)
            while time.monotonic() < until:
                data = self.transport.read(1, max(0, until - time.monotonic()))
                if not data:
                    continue
                if previous == 0x12 and data == b"\x12":
                    self.state = "ready"
                    return
                previous = data[0]
        raise BootError("no 12 12 ROM reply; reset before another attempt")

    def _send(self, data: bytes) -> None:
        # Byte pacing gives the polling ROM time to consume its short SIO FIFO.
        # In particular, do not retry a partially transmitted record.
        for value in data:
            self.transport.write(bytes((value,)))
            if self.byte_delay:
                time.sleep(self.byte_delay)

    def upload(self, address: int, data: bytes) -> None:
        record = load_record(address, data)
        if self.state != "ready":
            raise BootError("upload requires a successful handshake")
        self.state = "failed"
        self._send(record)
        self.loaded = (address, address + len(data))
        self.state = "loaded"

    def execute(self, entry: int) -> None:
        record = run_record(entry)
        if self.state != "loaded" or self.loaded is None:
            raise BootError("execute requires an uploaded payload")
        if not self.loaded[0] <= entry < self.loaded[1]:
            raise ValueError("entry must lie inside the uploaded payload")
        self.state = "failed"
        self._send(record)
        self.state = "executed"

    def expect(self, expected: bytes, timeout: float = 5.0) -> None:
        """Exact response, bounded deadline; no retries on mismatch or timeout."""
        positive(timeout, "timeout")
        deadline = time.monotonic() + timeout
        received = bytearray()
        while len(received) < len(expected):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BootError(f"response timeout: received {bytes(received)!r}")
            received.extend(
                self.transport.read(len(expected) - len(received), remaining)
            )
            if not expected.startswith(received):
                raise BootError(f"unexpected response: {bytes(received)!r}")
