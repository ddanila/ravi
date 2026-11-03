"""Verified relocatable helper; selector 1 is base RAM, 2..4 share top 16 KiB."""

from dataclasses import dataclass

from .build import build_helper


@dataclass(frozen=True)
class BankAddress:
    bank: int
    address: int

    def validate(self, length):
        if (
            self.bank not in (1, 2, 3, 4)
            or length <= 0
            or not 0 <= self.address < self.address + length <= 65536
        ):
            raise ValueError("invalid bank/address/range")


class BankedMonitor:
    def __init__(self, monitor, address):
        self.monitor = monitor
        self.image, self.labels = build_helper(address)
        self.start = address
        self.end = self.labels["helper_end"]
        self.active = False

    def install(self):
        # Stronger than trusting one write/readback: test the full helper+stack.
        first = self.start & ~255
        end = (self.end + 255) & ~255
        pages = self.monitor.survey(first, end - first)
        if not all(p["passed"] for p in pages):
            raise ValueError("helper window failed survey; no execution attempted")
        self.monitor.write_memory(self.start, self.image)
        self.monitor.reserved.append((self.start, self.end))
        self.active = True
        return {
            "address": self.start,
            "end": self.end,
            "common": self.start >= 0xC000,
            "survey": pages,
        }

    def _check(self, location, length, writing=False):
        if not self.active:
            raise ValueError("helper is not installed")
        location.validate(length)
        if location.bank != 1 and self.start < 0xC000:
            raise ValueError(
                "other read banks need a verified helper in common C000h..FFFFh RAM"
            )
        # A low helper is visible only in bank 1. For a common helper all
        # selectors alias its physical bytes; never permit overwriting them.
        if (
            writing
            and location.address < self.end
            and location.address + length > self.start
        ):
            raise ValueError("operation overlaps helper, buffer or stack")

    def _internal_write(self, address, data):
        # Temporary authorization for only this known, checked workspace.
        if not self.start <= address < address + len(data) <= self.end:
            raise ValueError("internal write escaped helper")
        reserved = self.monitor.reserved
        self.monitor.reserved = [r for r in reserved if r != (self.start, self.end)]
        try:
            self.monitor.write_memory(address, data)
        finally:
            self.monitor.reserved = reserved

    def _operate(self, operation, location, length, data=None):
        self._check(location, length, operation != 1)
        # Detect changed helper code before every execution. Config/data differ.
        code_end = self.labels["saved_id"] - self.start
        if self.monitor.read_memory(self.start, code_end) != self.image[:code_end]:
            self.active = False
            raise ValueError("helper code changed; stopped before execution")
        if data is not None:
            self._internal_write(self.labels["buffer"], data)
        config = (
            bytes((operation, location.bank))
            + location.address.to_bytes(2, "little")
            + length.to_bytes(2, "little")
        )
        self._internal_write(self.labels["operation"], config)
        result = self.monitor.execute(self.start)
        if result["accumulator"]:
            failure = int.from_bytes(
                self.monitor.read_memory(self.labels["failure"], 2), "little"
            )
            raise ValueError(
                f"helper RAM verification failed at {location.bank}:{failure:04X}"
            )

    def read_memory(self, location, length):
        self._check(location, length)
        out = bytearray()
        for i in range(0, length, 64):
            count = min(64, length - i)
            self._operate(1, BankAddress(location.bank, location.address + i), count)
            out.extend(self.monitor.read_memory(self.labels["buffer"], count))
        return bytes(out)

    def write_memory(self, location, data):
        self._check(location, len(data), True)
        for i in range(0, len(data), 64):
            chunk = data[i : i + 64]
            self._operate(
                2, BankAddress(location.bank, location.address + i), len(chunk), chunk
            )
        if self.read_memory(location, len(data)) != data:
            raise ValueError("banked readback mismatch")

    def call(self, address, timeout=5):
        location = (
            address if isinstance(address, BankAddress) else BankAddress(1, address)
        )
        self._check(location, 1, True)
        code_end = self.labels["saved_id"] - self.start
        if self.monitor.read_memory(self.start, code_end) != self.image[:code_end]:
            self.active = False
            raise ValueError("helper code changed")
        self._internal_write(
            self.labels["operation"],
            bytes((3, location.bank))
            + location.address.to_bytes(2, "little")
            + b"\0\0",
        )
        return self.monitor.execute(self.start, timeout)
