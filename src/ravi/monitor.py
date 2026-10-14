"""Shared monitor command exchange and response validation.

Adapters supply frame transmission and reception. Juku supplies its solicited
symbol link; raw monitor targets use ordinary ordered byte transports.
"""

import time

from .protocols import monitor_v2 as protocol


class SessionError(RuntimeError):
    """A complete, trustworthy monitor session could not be obtained."""


class LoaderFrameError(SessionError):
    """The ROM rejected a frame while retaining the next decoder cursor."""

    def __init__(self, status: int, cursor: int, description: str) -> None:
        self.status = status
        self.cursor = cursor
        super().__init__(
            f"loader error during {description}: {loader_status_name(status)}"
        )


class LoaderResponseTimeout(SessionError):
    """No loader response arrived, while retaining the decoder cursor."""

    def __init__(self, cursor: int, description: str) -> None:
        self.cursor = cursor
        super().__init__(f"timeout waiting for {description}")


def loader_status_name(status: int) -> str:
    return {
        protocol.LOADER_STATUS_OK: "ok",
        protocol.LOADER_STATUS_BAD_CRC: "bad_crc",
        protocol.LOADER_STATUS_BAD_COMMAND: "bad_command",
        protocol.LOADER_STATUS_BAD_LENGTH: "bad_length",
        protocol.LOADER_STATUS_BAD_RANGE: "bad_range",
        protocol.LOADER_STATUS_VERIFY_FAILED: "verify_failed",
        protocol.LOADER_STATUS_STRONG_CRC: "strong_crc",
        protocol.LOADER_STATUS_BAD_CONFIG: "bad_config",
        protocol.LOADER_STATUS_WORKSPACE: "workspace",
    }.get(status, f"unknown_{status:02X}")


def decode_loader_v2_result(frame: protocol.Frame) -> dict[str, int]:
    if frame.record_type != protocol.TYPE_LOADER_V2_RESULT or len(frame.payload) != 10:
        raise SessionError("loader API v2 RESULT must contain ten detail bytes")
    (
        transaction,
        status,
        command,
        decoded_length,
        address_hi,
        address_lo,
        count,
        crc_hi,
        crc_lo,
        store_retries,
    ) = frame.payload
    return {
        "transaction": transaction,
        "status": status,
        "command": command,
        "decoded_length": decoded_length,
        "address": (address_hi << 8) | address_lo,
        "count": count,
        "crc16": (crc_hi << 8) | crc_lo,
        "store_retries": store_retries,
    }


def decode_loader_v2_data(frame: protocol.Frame) -> tuple[dict[str, int], bytes]:
    if frame.record_type != protocol.TYPE_LOADER_V2_DATA or len(frame.payload) < 6:
        raise SessionError("loader API v2 DATA is shorter than its six-byte header")
    transaction, status, command, address_hi, address_lo, count = frame.payload[:6]
    data = frame.payload[6:]
    if len(data) != count:
        raise SessionError(
            f"loader API v2 DATA count {count} differs from payload bytes {len(data)}"
        )
    return {
        "transaction": transaction,
        "status": status,
        "command": command,
        "address": (address_hi << 8) | address_lo,
        "count": count,
    }, data


class MonitorTransactions:
    def _loader_v2_transact(
        self,
        command: bytes,
        transaction: int,
        expected_type: int,
        cursor: int,
        timeout: float,
        description: str,
    ) -> tuple[protocol.Frame, int, int]:
        """Run one bounded, transaction-correlated loader API v2 exchange."""
        for attempt in range(1, self.loader_retries + 1):
            deadline = time.monotonic() + timeout
            self._send_loader_frame(
                command, timeout, f"{description} attempt {attempt}"
            )
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise LoaderResponseTimeout(cursor, description)
                    response, cursor = self._wait_loader_frame(
                        expected_type,
                        cursor,
                        remaining,
                        f"{description} response attempt {attempt}",
                    )
                    response_transaction = (
                        response.payload[0] if response.payload else None
                    )
                    if response_transaction == transaction:
                        break
                if response.record_type == protocol.TYPE_LOADER_V2_RESULT:
                    detail = decode_loader_v2_result(response)
                    if (
                        detail["status"]
                        in (
                            protocol.LOADER_STATUS_BAD_CRC,
                            protocol.LOADER_STATUS_STRONG_CRC,
                        )
                        and attempt < self.loader_retries
                    ):
                        continue
                    if expected_type != protocol.TYPE_LOADER_V2_RESULT:
                        raise SessionError(
                            f"loader API v2 {description} returned "
                            f"{loader_status_name(detail['status'])} "
                            f"after {attempt} attempt(s)"
                        )
                return response, cursor, attempt
            except LoaderFrameError as error:
                cursor = error.cursor
                if (
                    error.status != protocol.LOADER_STATUS_BAD_CRC
                    or attempt >= self.loader_retries
                ):
                    raise
            except LoaderResponseTimeout as error:
                cursor = error.cursor
                if attempt >= self.loader_retries:
                    raise
        raise AssertionError("bounded loader transaction loop fell through")

    def _loader_v2_result_command(
        self,
        record_type: int,
        transaction: int,
        body: bytes,
        cursor: int,
        timeout: float,
        description: str,
    ) -> tuple[dict[str, int], int, int]:
        command = protocol.encode_loader_v2_command(record_type, transaction, body)
        response, cursor, attempts = self._loader_v2_transact(
            command,
            transaction,
            protocol.TYPE_LOADER_V2_RESULT,
            cursor,
            timeout,
            description,
        )
        detail = decode_loader_v2_result(response)
        if detail["command"] != record_type:
            raise SessionError(
                f"loader API v2 {description} response command "
                f"0x{detail['command']:02X} "
                f"!= 0x{record_type:02X}"
            )
        return detail, cursor, attempts

    def _loader_v2_data_command(
        self,
        record_type: int,
        transaction: int,
        body: bytes,
        cursor: int,
        timeout: float,
        description: str,
    ) -> tuple[dict[str, int], bytes, int, int]:
        command = protocol.encode_loader_v2_command(record_type, transaction, body)
        response, cursor, attempts = self._loader_v2_transact(
            command,
            transaction,
            protocol.TYPE_LOADER_V2_DATA,
            cursor,
            timeout,
            description,
        )
        detail, data = decode_loader_v2_data(response)
        if detail["command"] != record_type:
            raise SessionError(
                f"loader API v2 {description} DATA command "
                f"0x{detail['command']:02X} "
                f"!= 0x{record_type:02X}"
            )
        return detail, data, cursor, attempts
