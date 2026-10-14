"""Monitor v2 frames and memory commands, independent of CPU and board layout."""

from __future__ import annotations

from dataclasses import dataclass

from ..integrity import crc8_atm
from ..integrity import crc16_ccitt as crc16_ccitt_false
from ..targets import MemoryLayout

SYNC = bytes((0xA5, 0x5A))
PROTOCOL_VERSION = 1
TYPE_BANNER = 0x01
TYPE_ACK = 0x81
TYPE_RAM_BEGIN = 0x10
TYPE_RAM_BLOCK = 0x11
TYPE_RAM_END = 0x12
TYPE_LOAD = 0x20
TYPE_RUN = 0x22
TYPE_LOADER_V2_PROBE = 0x23
TYPE_LOADER_V2_CONFIG = 0x24
TYPE_LOADER_V2_LOAD = 0x25
TYPE_LOADER_V2_READ = 0x26
TYPE_LOADER_V2_CRC = 0x27
TYPE_LOADER_V2_RUN = 0x28
TYPE_LOADER_V2_RESYNC = 0x29
TYPE_LOADER_V2_REFRESH = 0x2A
TYPE_HEARTBEAT = 0x30
TYPE_NANO_LIVENESS = 0x40
TYPE_DIAG_STATUS = 0x50
TYPE_LOAD_RESULT = 0xA0
TYPE_RUN_ACK = 0xA2
TYPE_LOADER_READY = 0xA3
TYPE_LOADER_ERROR = 0xAF
TYPE_LOADER_V2_RESULT = 0xB0
TYPE_LOADER_V2_DATA = 0xB1
TYPE_LOADER_V2_RETURN = 0xB2
MAX_PAYLOAD = 255

LOADER_STATUS_OK = 0
LOADER_STATUS_BAD_CRC = 1
LOADER_STATUS_BAD_COMMAND = 2
LOADER_STATUS_BAD_LENGTH = 3
LOADER_STATUS_BAD_RANGE = 4
LOADER_STATUS_VERIFY_FAILED = 5
LOADER_STATUS_STRONG_CRC = 6
LOADER_STATUS_BAD_CONFIG = 7
LOADER_STATUS_WORKSPACE = 8

LOADER_V2_CAP_PROBE = 0x0001
LOADER_V2_CAP_CONFIG_VOTES = 0x0002
LOADER_V2_CAP_LOAD = 0x0004
LOADER_V2_CAP_READ = 0x0008
LOADER_V2_CAP_CRC = 0x0010
LOADER_V2_CAP_RUN = 0x0020
LOADER_V2_CAP_RESYNC = 0x0040
LOADER_V2_CAP_TRANSACTIONS = 0x0080
LOADER_V2_CAP_VERIFIED_BUFFER = 0x0100
LOADER_V2_CAP_STRONG_CRC = 0x0200
LOADER_V2_CAP_CALL_RETURN = 0x0400
LOADER_V2_CAP_RUN_REPLAY = 0x0800
LOADER_V2_CAP_UART_RESTORE = 0x1000
LOADER_V2_CAP_IDLE_RESYNC = 0x2000
LOADER_V2_CAP_REFRESH = 0x4000
LOADER_V2_CAPABILITIES = (
    LOADER_V2_CAP_PROBE
    | LOADER_V2_CAP_CONFIG_VOTES
    | LOADER_V2_CAP_LOAD
    | LOADER_V2_CAP_READ
    | LOADER_V2_CAP_CRC
    | LOADER_V2_CAP_RUN
    | LOADER_V2_CAP_RESYNC
    | LOADER_V2_CAP_TRANSACTIONS
    | LOADER_V2_CAP_VERIFIED_BUFFER
    | LOADER_V2_CAP_STRONG_CRC
    | LOADER_V2_CAP_CALL_RETURN
    | LOADER_V2_CAP_RUN_REPLAY
    | LOADER_V2_CAP_UART_RESTORE
    | LOADER_V2_CAP_IDLE_RESYNC
)

LOADER_V2_RUN_CALL = 0
LOADER_V2_RUN_JUMP = 1
LOADER_V2_COMMAND_TYPES = (
    TYPE_LOADER_V2_PROBE,
    TYPE_LOADER_V2_CONFIG,
    TYPE_LOADER_V2_LOAD,
    TYPE_LOADER_V2_READ,
    TYPE_LOADER_V2_CRC,
    TYPE_LOADER_V2_RUN,
    TYPE_LOADER_V2_RESYNC,
    TYPE_LOADER_V2_REFRESH,
)


def encode_loader_v2_command(
    record_type: int, transaction: int, body: bytes = b""
) -> bytes:
    """Encode one loader API v2 command with outer CRC-8 and inner CRC-16.

    The inner checksum is calculated over type, final payload length, the
    transaction byte, and the command body. The ROM recomputes it from its RAM
    parser buffer, so a correct UART CRC cannot conceal a failed RAM store.
    """
    if record_type not in LOADER_V2_COMMAND_TYPES:
        raise ValueError("record type is not a loader API v2 command")
    if not 0 <= transaction <= 0xFF:
        raise ValueError("transaction does not fit one byte")
    payload_without_crc = bytes((transaction,)) + body
    final_length = len(payload_without_crc) + 2
    if final_length > MAX_PAYLOAD:
        raise ValueError("loader API v2 command payload is too long")
    protected = bytes((record_type, final_length)) + payload_without_crc
    strong_crc = crc16_ccitt_false(protected)
    return encode_frame(
        record_type,
        payload_without_crc + strong_crc.to_bytes(2, "big"),
    )


def validate_loader_v2_command(frame: Frame) -> tuple[int, bytes]:
    """Validate and split a loader API v2 command into transaction and body."""
    if frame.record_type not in LOADER_V2_COMMAND_TYPES:
        raise ValueError("frame is not a loader API v2 command")
    if len(frame.payload) < 3:
        raise ValueError(
            "loader API v2 command is shorter than transaction plus CRC-16"
        )
    payload_without_crc = frame.payload[:-2]
    received = int.from_bytes(frame.payload[-2:], "big")
    protected = bytes((frame.record_type, len(frame.payload))) + payload_without_crc
    if crc16_ccitt_false(protected) != received:
        raise ValueError("loader API v2 command inner CRC-16 differs")
    return payload_without_crc[0], payload_without_crc[1:]


def encode_frame(record_type: int, payload: bytes) -> bytes:
    if not 0 <= record_type <= 0xFF:
        raise ValueError("record type is not one byte")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload is longer than one-byte length")
    body = bytes((record_type, len(payload))) + payload
    return SYNC + body + bytes((crc8_atm(body),))


@dataclass(frozen=True)
class Frame:
    record_type: int
    payload: bytes


class StreamDecoder:
    """Incremental decoder that resynchronizes at the next A5 5A marker."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buffer.extend(data)
        frames: list[Frame] = []
        while True:
            marker = self._buffer.find(SYNC)
            if marker < 0:
                self._buffer[:] = (
                    self._buffer[-1:] if self._buffer.endswith(SYNC[:1]) else b""
                )
                break
            if marker:
                del self._buffer[:marker]
            if len(self._buffer) < 5:
                break
            length = self._buffer[3]
            frame_length = 5 + length
            if len(self._buffer) < frame_length:
                break
            candidate = bytes(self._buffer[:frame_length])
            body = candidate[2:-1]
            if crc8_atm(body) == candidate[-1]:
                frames.append(Frame(body[0], body[2:]))
                del self._buffer[:frame_length]
            else:
                del self._buffer[0]
        return frames


@dataclass(frozen=True)
class MonitorCodec:
    layout: MemoryLayout

    def __post_init__(self):
        if self.layout.address_bits != 16 or self.layout.max_chunk > 249:
            raise ValueError("monitor v2 requires 16-bit addresses and chunks <=249")

    def load(self, transaction: int, address: int, data: bytes) -> bytes:
        self.layout.validate(address, len(data))
        if len(data) > self.layout.max_chunk:
            raise ValueError("load exceeds target chunk size")
        return encode_loader_v2_command(
            TYPE_LOADER_V2_LOAD, transaction, address.to_bytes(2, "big") + data
        )

    def range_command(
        self, command: int, transaction: int, address: int, count: int
    ) -> bytes:
        if command not in (TYPE_LOADER_V2_READ, TYPE_LOADER_V2_CRC):
            raise ValueError("range command must be READ or CRC")
        self.layout.validate(address, count)
        if count > self.layout.max_chunk:
            raise ValueError("range exceeds target chunk size")
        return encode_loader_v2_command(
            command, transaction, address.to_bytes(2, "big") + bytes((count,))
        )

    def run(
        self, transaction: int, address: int, mode: int, execution_id: int
    ) -> bytes:
        self.layout.validate(address, 1)
        if mode not in (LOADER_V2_RUN_CALL, LOADER_V2_RUN_JUMP):
            raise ValueError("run mode is invalid")
        if not 0 <= execution_id <= 0xFFFFFFFF:
            raise ValueError("execution ID does not fit 32 bits")
        return encode_loader_v2_command(
            TYPE_LOADER_V2_RUN,
            transaction,
            address.to_bytes(2, "big")
            + bytes((mode,))
            + execution_id.to_bytes(4, "big"),
        )
