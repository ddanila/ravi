"""Capability contracts; targets explicitly select their operations and layout."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class UnsupportedOperation(ValueError):
    pass


class Capability(str, Enum):
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    MEMORY_CALL = "memory.call"
    FILE_READ = "file.read"
    FILE_WRITE = "file.write"
    FILE_LIST = "file.list"
    FILE_REMOVE = "file.remove"
    PROCESS_EXEC = "process.exec"


@dataclass(frozen=True)
class AddressRange:
    start: int
    end: int

    def __post_init__(self):
        if not isinstance(self.start, int) or not isinstance(self.end, int):
            raise ValueError("addresses must be integers")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("address range must be positive and nonempty")

    def contains(self, address: int, length: int) -> bool:
        return self.start <= address and length >= 0 and address + length <= self.end


@dataclass(frozen=True)
class MemoryLayout:
    """Host-authorized windows; reserved RAM is excluded even within a window."""

    writable: tuple[AddressRange, ...]
    reserved: tuple[AddressRange, ...] = ()
    address_bits: int = 16
    max_chunk: int = 32

    def __post_init__(self):
        if self.address_bits not in (16, 32) or not 1 <= self.max_chunk <= 65535:
            raise ValueError("invalid address width or chunk size")
        if not self.writable:
            raise ValueError("at least one memory window is required")
        for item in self.writable + self.reserved:
            if item.end > 1 << self.address_bits:
                raise ValueError("range exceeds the address space")
        for left, right in zip(sorted(self.writable, key=lambda r: r.start),
                               sorted(self.writable, key=lambda r: r.start)[1:]):
            if left.end > right.start:
                raise ValueError("memory windows overlap")

    def validate(self, address: int, length: int) -> None:
        if not isinstance(address, int) or not isinstance(length, int) or length <= 0:
            raise ValueError("memory operation requires an integer address and positive length")
        if not any(region.contains(address, length) for region in self.writable):
            raise ValueError("operation is outside the authorized memory window")
        if any(address < region.end and address + length > region.start for region in self.reserved):
            raise ValueError("operation overlaps reserved memory")

    def chunks(self, address: int, length: int):
        self.validate(address, length)
        for offset in range(0, length, self.max_chunk):
            yield address + offset, min(self.max_chunk, length - offset)


@dataclass(frozen=True)
class TargetInfo:
    target: str
    protocol: str
    capabilities: frozenset[Capability]
    memory: MemoryLayout | None = None
    # A local connection is not proof of the remote boot identity.
    boot_identity: str | None = None
    replay_scope: str = "none"

    def require(self, capability: Capability) -> None:
        if capability not in self.capabilities:
            raise UnsupportedOperation(f"{self.target} does not support {capability.value}")


@dataclass(frozen=True)
class CallResult:
    execution_id: int
    accumulator: int
    # Kept target-specific: no invented equivalence to a DOS process exit code.
    evidence: dict


@runtime_checkable
class MemoryTarget(Protocol):
    @property
    def target_info(self) -> TargetInfo: ...
    def read_memory(self, address: int, length: int) -> bytes: ...
    def write_memory(self, address: int, data: bytes) -> None: ...
    def call(self, address: int) -> CallResult: ...


@runtime_checkable
class FileTarget(Protocol):
    @property
    def target_info(self) -> TargetInfo: ...
    def list(self) -> list[dict[str, object]]: ...
    def put(self, local, remote: str, chunk_size: int = 512): ...
    def get(self, remote: str, local, chunk_size: int = 512): ...
    def remove(self, remote: str) -> None: ...
    def execute(self, remote: str, arguments: str = "", execution_id: int | None = None, **kwargs): ...
