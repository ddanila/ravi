"""Host policy for W1. No automatic retries of memory mutation or execution."""

import math
import time
from collections import deque
from dataclasses import asdict

from ravi.execution import OutcomeUnknown
from ravi.targets import AddressRange, CallResult, Capability, MemoryLayout, TargetInfo

from . import protocol as p


class MonitorError(RuntimeError):
    def __init__(self, reply):
        self.reply = reply
        name = (
            p.STATUS[reply.status]
            if reply.status < len(p.STATUS)
            else str(reply.status)
        )
        super().__init__(
            f"{name} at bank {reply.bank}:{reply.address:04X}, value {reply.value:02X}"
        )


class Monitor:
    def __init__(self, transport, timeout=3.0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self.transport = transport
        self.timeout = timeout
        self.parser = p.Parser()
        self.pending = deque()
        self.transaction = 0
        self.usable = True
        self.attached = False
        self.events = []
        self.reserved = []

    @property
    def target_info(self):
        return TargetInfo(
            "robotron1715w",
            "W1",
            frozenset(
                (
                    Capability.MEMORY_READ,
                    Capability.MEMORY_WRITE,
                    Capability.MEMORY_CALL,
                )
            ),
            MemoryLayout(
                (AddressRange(0x4000, 0x10000),),
                tuple(AddressRange(a, b) for a, b in self.reserved),
                max_chunk=p.MAX_BLOCK,
            ),
            boot_identity=None,
            replay_scope="none",
        )

    def call(self, address):
        result = self.execute(address)
        return CallResult(result["transaction"], result["accumulator"], result)

    def _begin(self, op, bank=0, address=0, value=0, payload=b""):
        if not self.usable:
            raise OutcomeUnknown(
                "session invalid after reset or execution uncertainty; reset and attach anew"
            )
        self.transaction = self.transaction % 255 + 1
        self.transport.write(
            p.request(op, self.transaction, bank, address, value) + payload
        )
        return time.monotonic() + self.timeout

    def _reply(self, deadline):
        while time.monotonic() < deadline:
            while self.pending:
                r = self.pending.popleft()
                self.events.append(asdict(r))
                if r.status == p.RETURN and r.transaction == 0 and self.attached:
                    self.usable = False
                    raise ConnectionError(
                        "target restarted during established W1 session"
                    )
                if r.transaction == self.transaction:
                    self.attached = True
                    return r
            self.pending.extend(
                self.parser.feed(
                    self.transport.read(4096, max(0, deadline - time.monotonic()))
                )
            )
        raise TimeoutError("W1 response deadline expired; no automatic replay")

    def _ok(self, deadline):
        r = self._reply(deadline)
        if r.status != p.OK:
            raise MonitorError(r)
        return r

    def identify(self):
        r = self._ok(self._begin("I"))
        if (r.bank, r.address, r.value) != (0, 2048, 1):
            raise ValueError("unexpected W1 identity")
        return {
            "target": "robotron1715w",
            "protocol": "W1",
            "rom_bytes": r.address,
            "main_ram_workspace": 0,
            "max_block": p.MAX_BLOCK,
            "boot_identity": None,
            "replay_scope": "none",
        }

    def _range(self, address, length, writing=False):
        if (
            not isinstance(address, int)
            or not isinstance(length, int)
            or length <= 0
            or not 0x4000 <= address < address + length <= 0x10000
        ):
            raise ValueError("ROM direct access requires base RAM 4000h..FFFFh")
        if writing and any(
            address < end and address + length > start for start, end in self.reserved
        ):
            raise ValueError("operation overlaps active helper/return workspace")

    def read_memory(self, address, length):
        self._range(address, length)
        result = bytearray()
        while len(result) < length:
            count = min(p.MAX_BLOCK, length - len(result))
            start = address + len(result)
            deadline = self._begin("R", 1, start, count)
            for offset in range(count):
                r = self._reply(deadline)
                if r.status != p.DATA:
                    raise MonitorError(r)
                if (r.bank, r.address) != (1, start + offset):
                    raise ValueError("out-of-order W1 data")
                result.append(r.value)
        return bytes(result)

    def write_memory(self, address, data):
        self._range(address, len(data), True)
        for offset in range(0, len(data), p.MAX_BLOCK):
            block = data[offset : offset + p.MAX_BLOCK]
            self._ok(
                self._begin("W", 1, address + offset, len(block), p.protected(block))
            )
        actual = self.read_memory(address, len(data))
        if actual != data:
            i = next(i for i, (a, b) in enumerate(zip(actual, data)) if a != b)
            raise ValueError(
                f"readback mismatch at {address + i:04X}: wanted {data[i]:02X}, got {actual[i]:02X}"
            )

    def fill_page(self, address, value):
        self._range(address, 256, True)
        if address & 255 or not 0 <= value <= 255:
            raise ValueError("fill requires page alignment and byte pattern")
        self._ok(self._begin("F", 1, address, value))

    def survey(self, address, length):
        self._range(address, length, True)
        if address & 255 or length & 255:
            raise ValueError("survey requires whole pages")
        pages = []
        for page in range(address, address + length, 256):
            failures = []
            for value in (0, 255, 0x55, 0xAA):
                try:
                    self.fill_page(page, value)
                except MonitorError as exc:
                    if exc.reply.status != p.VERIFY:
                        raise
                    failures.append({"pattern": value, **asdict(exc.reply)})
            # Distinguish basic address aliases from data-line clamps.
            try:
                self.write_memory(page, bytes(range(256)))
            except (MonitorError, ValueError) as exc:
                failures.append({"pattern": "low-address", "error": str(exc)})
            pages.append(
                {"address": page, "passed": not failures, "failures": failures}
            )
        return pages

    def execute(self, address, timeout=5.0):
        self._range(address, 1)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("execution timeout must be positive")
        # Even losing STARTED leaves execution uncertain; never resend GO.
        try:
            r = self._reply(self._begin("G", 1, address))
            if r.status != p.STARTED:
                if r.status in (p.RANGE, p.BAD_OP, p.BAD_CRC):
                    raise MonitorError(r)
                raise ValueError("missing STARTED")
            r = self._reply(time.monotonic() + timeout)
            if r.status != p.RETURN:
                raise ValueError("missing RETURN")
            return {"transaction": r.transaction, "accumulator": r.value}
        except MonitorError:
            raise
        except Exception as exc:
            self.usable = False
            raise OutcomeUnknown(
                f"execution outcome unknown; reset required: {exc}"
            ) from exc
