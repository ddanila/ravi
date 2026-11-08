"""Recoverable PC1715 diagnostic protocol; never replays commands automatically."""

from __future__ import annotations

import time

from ravi.transport import Transport

from .boot import BootError

IDENTITY = b"R1715 DIAG 1"


class Monitor:
    def __init__(self, transport: Transport, byte_delay: float = 0.002):
        if byte_delay < 0:
            raise ValueError("negative byte delay")
        self.transport = transport
        self.byte_delay = byte_delay

    def _send(self, data: bytes) -> None:
        for byte in data:
            self.transport.write(bytes([byte]))
            if self.byte_delay:
                time.sleep(self.byte_delay)

    def response(self, timeout: float = 15) -> list[bytes]:
        deadline = time.monotonic() + timeout
        data = bytearray()
        while len(data) < 2048:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BootError(f"monitor timeout: {bytes(data)!r}")
            data.extend(self.transport.read(1, remaining))
            if data.endswith(b"READY\r\n"):
                lines = bytes(data).split(b"\r\n")[:-1]
                if lines[-1] == b"READY":
                    return lines[:-1]
        raise BootError("monitor response exceeds limit")

    def identify(self) -> None:
        self._send(b"?")
        if self.response() != [IDENTITY]:
            raise BootError("unexpected monitor identity")

    @staticmethod
    def _range(address: int, length: int) -> bytes:
        if not 0 <= address <= 0xFFFF or not 1 <= length <= 256:
            raise ValueError("address must be 0000..FFFF, length 1..256")
        if address + length > 0x10000:
            raise ValueError("range wraps memory")
        return address.to_bytes(2, "little") + bytes([length & 255])

    def _hex_response(self, prefix: bytes, length: int) -> bytes:
        lines = self.response()
        if len(lines) != 1 or not lines[0].startswith(prefix):
            raise BootError(f"unexpected monitor response: {lines!r}")
        try:
            data = bytes.fromhex(lines[0][len(prefix) :].decode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise BootError("invalid hexadecimal response") from exc
        if len(data) != length:
            raise BootError("incorrect readback length")
        return data

    def read_memory(self, address: int, length: int) -> bytes:
        header = self._range(address, length)
        self._send(b"R" + header)
        return self._hex_response(b"DATA ", length)

    def test_page(self, page: int) -> dict:
        if not 0 <= page <= 255 or 8 <= page <= 15 or 0x40 <= page <= 0x4F:
            raise ValueError("protected or invalid page")
        self._send(b"T" + bytes([page]))
        lines = self.response()
        if len(lines) != 2 or lines[0] != f"TEST {page:02X}".encode():
            raise BootError(f"unexpected test response: {lines!r}")
        if lines[1] == f"PASS {page:02X}".encode():
            return {"page": page, "passed": True}
        fields = lines[1].split()
        try:
            if (
                len(fields) != 7
                or fields[0] != b"FAIL"
                or fields[1] not in (b"P", b"A")
            ):
                raise ValueError("invalid failure record")
            address, expected, actual, xor, second = [int(x, 16) for x in fields[2:]]
            if address >> 8 != page or any(
                not 0 <= x <= 255 for x in [expected, actual, xor, second]
            ):
                raise ValueError("out-of-range failure record")
            if xor != expected ^ actual or expected == actual:
                raise ValueError("inconsistent failure record")
        except ValueError as exc:
            raise BootError(f"invalid failure response: {lines[1]!r}") from exc
        return {
            "page": page,
            "passed": False,
            "phase": fields[1].decode(),
            "address": address,
            "expected": expected,
            "actual": actual,
            "xor": xor,
            "second_read": second,
        }

    def write_memory(self, address: int, data: bytes) -> None:
        header = self._range(address, len(data))
        if address < 0x1000 or 0x4000 <= address < 0x5000:
            raise ValueError("protected write address")
        if (address & 255) + len(data) > 256:
            raise ValueError("write must fit one page")
        self._send(b"W" + header + data)
        if self._hex_response(b"WROTE ", len(data)) != data:
            raise BootError("write readback mismatch; no automatic retry")

    def start(self, address: int, timeout: float = 15) -> None:
        """Transfer control permanently; consume GO only, leaving guest bytes unread.

        The caller must hand the same transport to the runtime service. No
        READY is expected, and a failed/uncertain start must never be replayed.
        """
        if not 0x1000 <= address <= 0xFFFF or 0x4000 <= address < 0x5000:
            raise ValueError("protected entry address")
        if timeout <= 0:
            raise ValueError("positive timeout required")
        self._send(b"G" + address.to_bytes(2, "little"))
        deadline = time.monotonic() + timeout
        for expected in b"GO\r\n":
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BootError("monitor handoff timeout; do not replay")
                received = self.transport.read(1, remaining)
                if received:
                    if received != bytes([expected]):
                        raise BootError(f"unexpected handoff byte: {received!r}; do not replay")
                    break

    def call(self, address: int) -> list[bytes]:
        if not 0x1000 <= address <= 0xFFFF or 0x4000 <= address < 0x5000:
            raise ValueError("protected entry address")
        self._send(b"G" + address.to_bytes(2, "little"))
        lines = self.response()
        if not lines or lines[0] != b"GO":
            raise BootError(f"unexpected call response: {lines!r}")
        return lines[1:]
