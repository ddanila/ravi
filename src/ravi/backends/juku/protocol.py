"""Wire-format primitives shared by Jukuravi firmware builders and host tools."""

from __future__ import annotations

from dataclasses import dataclass

from ...protocols.monitor_v2 import (
    LOADER_STATUS_BAD_COMMAND as LOADER_STATUS_BAD_COMMAND,
    LOADER_STATUS_BAD_CONFIG as LOADER_STATUS_BAD_CONFIG,
    LOADER_STATUS_BAD_CRC as LOADER_STATUS_BAD_CRC,
    LOADER_STATUS_BAD_LENGTH as LOADER_STATUS_BAD_LENGTH,
    LOADER_STATUS_BAD_RANGE as LOADER_STATUS_BAD_RANGE,
    LOADER_STATUS_OK as LOADER_STATUS_OK,
    LOADER_STATUS_STRONG_CRC as LOADER_STATUS_STRONG_CRC,
    LOADER_STATUS_VERIFY_FAILED as LOADER_STATUS_VERIFY_FAILED,
    LOADER_STATUS_WORKSPACE as LOADER_STATUS_WORKSPACE,
    LOADER_V2_API_VERSION as LOADER_V2_API_VERSION,
    LOADER_V2_CAP_CALL_RETURN as LOADER_V2_CAP_CALL_RETURN,
    LOADER_V2_CAP_CONFIG_VOTES as LOADER_V2_CAP_CONFIG_VOTES,
    LOADER_V2_CAP_CRC as LOADER_V2_CAP_CRC,
    LOADER_V2_CAP_IDLE_RESYNC as LOADER_V2_CAP_IDLE_RESYNC,
    LOADER_V2_CAP_LOAD as LOADER_V2_CAP_LOAD,
    LOADER_V2_CAP_PROBE as LOADER_V2_CAP_PROBE,
    LOADER_V2_CAP_READ as LOADER_V2_CAP_READ,
    LOADER_V2_CAP_REFRESH as LOADER_V2_CAP_REFRESH,
    LOADER_V2_CAP_RESYNC as LOADER_V2_CAP_RESYNC,
    LOADER_V2_CAP_RUN as LOADER_V2_CAP_RUN,
    LOADER_V2_CAP_RUN_REPLAY as LOADER_V2_CAP_RUN_REPLAY,
    LOADER_V2_CAP_STRONG_CRC as LOADER_V2_CAP_STRONG_CRC,
    LOADER_V2_CAP_TRANSACTIONS as LOADER_V2_CAP_TRANSACTIONS,
    LOADER_V2_CAP_UART_RESTORE as LOADER_V2_CAP_UART_RESTORE,
    LOADER_V2_CAP_VERIFIED_BUFFER as LOADER_V2_CAP_VERIFIED_BUFFER,
    LOADER_V2_CAPABILITIES as LOADER_V2_CAPABILITIES,
    LOADER_V2_COMMAND_TYPES as LOADER_V2_COMMAND_TYPES,
    LOADER_V2_RUN_CALL as LOADER_V2_RUN_CALL,
    LOADER_V2_RUN_JUMP as LOADER_V2_RUN_JUMP,
    MAX_PAYLOAD as MAX_PAYLOAD,
    PROTOCOL_VERSION as PROTOCOL_VERSION,
    SYNC as SYNC,
    TYPE_ACK as TYPE_ACK,
    TYPE_BANNER as TYPE_BANNER,
    TYPE_DIAG_STATUS as TYPE_DIAG_STATUS,
    TYPE_HEARTBEAT as TYPE_HEARTBEAT,
    TYPE_LOAD as TYPE_LOAD,
    TYPE_LOAD_RESULT as TYPE_LOAD_RESULT,
    TYPE_LOADER_ERROR as TYPE_LOADER_ERROR,
    TYPE_LOADER_READY as TYPE_LOADER_READY,
    TYPE_LOADER_V2_CONFIG as TYPE_LOADER_V2_CONFIG,
    TYPE_LOADER_V2_CRC as TYPE_LOADER_V2_CRC,
    TYPE_LOADER_V2_DATA as TYPE_LOADER_V2_DATA,
    TYPE_LOADER_V2_LOAD as TYPE_LOADER_V2_LOAD,
    TYPE_LOADER_V2_PROBE as TYPE_LOADER_V2_PROBE,
    TYPE_LOADER_V2_READ as TYPE_LOADER_V2_READ,
    TYPE_LOADER_V2_REFRESH as TYPE_LOADER_V2_REFRESH,
    TYPE_LOADER_V2_RESULT as TYPE_LOADER_V2_RESULT,
    TYPE_LOADER_V2_RESYNC as TYPE_LOADER_V2_RESYNC,
    TYPE_LOADER_V2_RETURN as TYPE_LOADER_V2_RETURN,
    TYPE_LOADER_V2_RUN as TYPE_LOADER_V2_RUN,
    TYPE_NANO_LIVENESS as TYPE_NANO_LIVENESS,
    TYPE_RAM_BEGIN as TYPE_RAM_BEGIN,
    TYPE_RAM_BLOCK as TYPE_RAM_BLOCK,
    TYPE_RAM_END as TYPE_RAM_END,
    TYPE_RUN as TYPE_RUN,
    TYPE_RUN_ACK as TYPE_RUN_ACK,
    Frame as Frame,
    MonitorCodec,
    StreamDecoder as StreamDecoder,
    crc8_atm as crc8_atm,
    crc16_ccitt_false as crc16_ccitt_false,
    encode_frame as encode_frame,
    encode_loader_v2_command as encode_loader_v2_command,
    validate_loader_v2_command as validate_loader_v2_command,
)
from .profile import JUKU_MEMORY

JUKU_CODEC = MonitorCodec(JUKU_MEMORY)


LOADER_API_VERSION = 1
LOADER_API_BASE = 0x0A00
LOADER_MAX_DATA = MAX_PAYLOAD - 2
LOADER_LOAD_MIN = 0x4000
LOADER_LOAD_END = 0xD800
HEARTBEAT_VERSION = 1
NANO_LIVENESS_VERSION = 1
NANO_LIVENESS_ENABLED = 0x01
NANO_LIVENESS_RESET_RELEASED = 0x02
NANO_LIVENESS_CLOCK_SEEN = 0x04
NANO_LIVENESS_MRDC_SEEN = 0x08
NANO_LIVENESS_KNOWN_FLAGS = 0x0F

LOADER_V2_BOOT_VOTES = 7
LOADER_V2_T35_BOOT_VOTES = 1
LOADER_V2_T36_BOOT_VOTES = 1
LOADER_V2_MIN_VOTES = 1
LOADER_V2_MAX_VOTES = 15
LOADER_V2_MAX_DATA = JUKU_MEMORY.max_chunk
LOADER_V2_MAX_PROBE = 16
LOADER_V2_LOAD_MIN = JUKU_MEMORY.windows[0].start
LOADER_V2_LOAD_END = JUKU_MEMORY.windows[0].end
LOADER_V2_WORKSPACE_BASE = JUKU_MEMORY.reserved[0].start
LOADER_V2_WORKSPACE_END = JUKU_MEMORY.reserved[0].end
LOADER_V2_T35_CAPABILITIES = LOADER_V2_CAPABILITIES | LOADER_V2_CAP_REFRESH
LOADER_V2_T36_CAPABILITIES = LOADER_V2_T35_CAPABILITIES
LOADER_V2_REFRESH_API = 0x07A9
LOADER_V2_REFRESH_VERSION = 1
LOADER_V2_REFRESH_QUERY = 0
LOADER_V2_REFRESH_ENABLE = 1
LOADER_V2_REFRESH_DISABLE = 2
LOADER_V2_REFRESH_RESET_COUNTER = 3
LOADER_V2_REFRESH_ROW_START = 0x40
LOADER_V2_T36_REFRESH_ROW_START = 0x00
LOADER_V2_REFRESH_ROWS = 128


def encode_load_frame(address: int, data: bytes) -> bytes:
    """Encode one independently checksummed loader chunk."""
    if not 0 <= address <= 0xFFFF:
        raise ValueError("load address does not fit 16 bits")
    if not data:
        raise ValueError("load chunk is empty")
    if len(data) > LOADER_MAX_DATA:
        raise ValueError(f"load chunk exceeds {LOADER_MAX_DATA} bytes")
    payload = address.to_bytes(2, "big") + data
    return encode_frame(TYPE_LOAD, payload)


def encode_run_frame(address: int) -> bytes:
    if not 0 <= address <= 0xFFFF:
        raise ValueError("run address does not fit 16 bits")
    return encode_frame(TYPE_RUN, address.to_bytes(2, "big"))


def encode_loader_v2_load(transaction: int, address: int, data: bytes) -> bytes:
    return JUKU_CODEC.load(transaction, address, data)


def encode_loader_v2_range_command(
    record_type: int, transaction: int, address: int, count: int
) -> bytes:
    return JUKU_CODEC.range_command(record_type, transaction, address, count)


def encode_loader_v2_run(
    transaction: int, address: int, mode: int, execution_id: int
) -> bytes:
    return JUKU_CODEC.run(transaction, address, mode, execution_id)


def encode_heartbeat_frame(sequence: int) -> bytes:
    """Encode one uploaded-program liveness record."""
    if not 0 <= sequence <= 0xFF:
        raise ValueError("heartbeat sequence does not fit one byte")
    return encode_frame(TYPE_HEARTBEAT, bytes((HEARTBEAT_VERSION, sequence)))


def encode_nano_liveness_frame(flags: int) -> bytes:
    """Encode one Nano-side liveness observation record."""
    if not 0 <= flags <= NANO_LIVENESS_KNOWN_FLAGS:
        raise ValueError("Nano liveness flags contain unknown bits")
    if not flags & NANO_LIVENESS_ENABLED:
        raise ValueError("Nano liveness record is not enabled")
    return encode_frame(TYPE_NANO_LIVENESS, bytes((NANO_LIVENESS_VERSION, flags)))


@dataclass(frozen=True)
class RamWindow:
    start: int
    end: int  # exclusive; may be 0x10000

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class RamSurvey:
    version: int
    pattern_set: int
    start_page: int
    end_page: int
    masks: tuple[int, ...]
    bad_pages_by_bit: tuple[tuple[int, ...], ...]
    largest_good_window: RamWindow | None


def decode_ram_survey(frames: list[Frame]) -> RamSurvey:
    """Validate one complete ordered RAM survey and derive its host verdict."""
    begin_index = next(
        (
            index
            for index, frame in enumerate(frames)
            if frame.record_type == TYPE_RAM_BEGIN
        ),
        None,
    )
    if begin_index is None:
        raise ValueError("RAM_BEGIN record is missing")
    begin = frames[begin_index]
    if len(begin.payload) != 4:
        raise ValueError("RAM_BEGIN payload length is not four")
    version, start_page, end_page, pattern_set = begin.payload
    if start_page > end_page:
        raise ValueError("RAM survey page range is reversed")

    page_count = end_page - start_page + 1
    block_frames = frames[begin_index + 1 : begin_index + 1 + page_count]
    if len(block_frames) != page_count:
        raise ValueError("RAM survey block records are incomplete")
    masks: list[int] = []
    for index, frame in enumerate(block_frames):
        expected_page = start_page + index
        if frame.record_type != TYPE_RAM_BLOCK or len(frame.payload) != 2:
            raise ValueError(f"RAM block {expected_page:02X} has wrong type or length")
        page, mask = frame.payload
        if page != expected_page:
            raise ValueError(
                f"RAM block page {page:02X} is out of order; expected {expected_page:02X}"
            )
        masks.append(mask)

    end_index = begin_index + 1 + page_count
    if end_index >= len(frames):
        raise ValueError("RAM_END record is missing")
    end = frames[end_index]
    if end != Frame(TYPE_RAM_END, bytes((start_page, end_page))):
        raise ValueError("RAM_END does not match RAM_BEGIN range")

    bad_pages_by_bit = tuple(
        tuple(
            start_page + index for index, mask in enumerate(masks) if mask & (1 << bit)
        )
        for bit in range(8)
    )
    best_start: int | None = None
    best_length = 0
    run_start: int | None = None
    for index, mask in enumerate((*masks, 0xFF)):
        if mask == 0 and run_start is None:
            run_start = index
        elif mask != 0 and run_start is not None:
            run_length = index - run_start
            if run_length > best_length:
                best_start, best_length = run_start, run_length
            run_start = None
    largest = None
    if best_start is not None:
        largest = RamWindow(
            (start_page + best_start) << 8,
            (start_page + best_start + best_length) << 8,
        )
    return RamSurvey(
        version=version,
        pattern_set=pattern_set,
        start_page=start_page,
        end_page=end_page,
        masks=tuple(masks),
        bad_pages_by_bit=bad_pages_by_bit,
        largest_good_window=largest,
    )
