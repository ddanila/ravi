"""W1 fixed frames and W2 header-protected block replies."""

from dataclasses import dataclass

from ravi.integrity import crc16_ccitt

SYNC = 0xA5
REPLY = 0x5A
MAX_BLOCK = 64
OK, STARTED, RETURN, BAD_CRC, RANGE, TIMEOUT, UART, VERIFY, BAD_OP, DATA = range(10)
BOOT, ROM_BAD, BLOCK = 10, 11, 12
STAGES = {1: "SERIAL", 2: "ROM_CHECK", 3: "DISPLAY"}
CAP_BLOCK = 16
STATUS = (
    "OK",
    "STARTED",
    "RETURN",
    "BAD_CRC",
    "RANGE",
    "TIMEOUT",
    "UART",
    "VERIFY",
    "BAD_OP",
    "DATA",
    "BOOT",
    "ROM_BAD",
    "BLOCK",
)


def protected(data: bytes) -> bytes:
    return data + crc16_ccitt(data).to_bytes(2, "big")


def request(
    op: str, transaction: int, bank: int = 0, address: int = 0, value: int = 0
) -> bytes:
    if len(op) != 1 or not 0 <= address <= 65535:
        raise ValueError("invalid command/address")
    body = bytes((ord(op), transaction, bank, address & 255, address >> 8, value))
    return bytes((SYNC,)) + protected(body)


@dataclass(frozen=True)
class Response:
    status: int
    transaction: int
    bank: int
    address: int
    value: int


@dataclass(frozen=True)
class BlockResponse(Response):
    data: tuple[int, ...]


class Parser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[Response]:
        self.buffer.extend(data)
        result = []
        while self.buffer:
            if self.buffer[0] != REPLY:
                del self.buffer[0]
                continue
            if len(self.buffer) < 9:
                break
            body = bytes(self.buffer[1:9])
            if crc16_ccitt(body) != 0:
                del self.buffer[0]
                continue
            status, txn, bank, low, high, value = body[:6]
            if status == BLOCK:
                if not 1 <= value <= MAX_BLOCK:
                    del self.buffer[0]
                    continue
                size = 9 + value + 2
                if len(self.buffer) < size:
                    break
                payload = bytes(self.buffer[9:size])
                if crc16_ccitt(payload) != 0:
                    del self.buffer[0]
                    continue
                result.append(
                    BlockResponse(
                        status, txn, bank, low | high << 8, value, tuple(payload[:-2])
                    )
                )
                del self.buffer[:size]
            else:
                result.append(Response(status, txn, bank, low | high << 8, value))
                del self.buffer[:9]
        return result
