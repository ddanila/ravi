"""Raw byte-stream monitor v2 target; no Nano, CPU, reset or refresh assumptions."""

import secrets
import time
from dataclasses import dataclass

from ..execution import OutcomeUnknown
from ..integrity import crc16_ccitt
from ..monitor import MonitorTransactions, LoaderFrameError, LoaderResponseTimeout, SessionError
from ..protocols import monitor_v2 as wire
from ..targets import Capability, CallResult, MemoryLayout, TargetInfo
from ..transport import Transport


@dataclass(frozen=True)
class MonitorProfile:
    name: str
    memory: MemoryLayout
    capabilities: frozenset[Capability]
    # Information from a qualified firmware contract, not inferred from CPU type.
    replay_safe: bool = False


class MonitorTarget(MonitorTransactions):
    """A live monitor after target-specific bootstrap has completed.

    attach verifies a READY record against the supplied profile. Bootstrap,
    reset, SIO setup and early progress observation are the target driver's job.
    This adapter never toggles DTR or reopens a disconnected transport.
    """

    def __init__(self, transport: Transport, profile: MonitorProfile, *, timeout: float = 2.0, attempts: int = 3):
        if timeout <= 0 or attempts < 1:
            raise ValueError("timeout and attempt count must be positive")
        self.transport = transport
        self.profile = profile
        self.codec = wire.MonitorCodec(profile.memory)
        self.timeout = timeout
        self.loader_retries = attempts
        self.decoder = wire.StreamDecoder()
        self.frames = []
        self.cursor = 0
        self.transaction = 0
        self.attached = False
        self.invalidated = False
        self.target_info = TargetInfo(profile.name, "monitor-v2", profile.capabilities,
                                      profile.memory, replay_scope="bounded-agent-ram-cache" if profile.replay_safe else "none")

    def _next(self):
        value = self.transaction
        self.transaction = (value + 1) & 255
        return value

    def _send_loader_frame(self, frame, timeout, description):
        if self.invalidated:
            raise SessionError("target session was invalidated; establish a new session explicitly")
        self.transport.write(frame)

    def _wait_loader_frame(self, expected_type, cursor, timeout, description):
        deadline = time.monotonic() + timeout
        while True:
            while cursor < len(self.frames):
                frame = self.frames[cursor]
                cursor += 1
                if self.attached and frame.record_type in (wire.TYPE_BANNER, wire.TYPE_LOADER_READY):
                    self.invalidated = True
                    raise OutcomeUnknown("target boot/READY observed during an attached session")
                if frame.record_type == wire.TYPE_LOADER_ERROR:
                    if len(frame.payload) != 1:
                        raise SessionError("malformed loader error")
                    raise LoaderFrameError(frame.payload[0], cursor, description)
                if frame.record_type in (expected_type, wire.TYPE_LOADER_V2_RESULT):
                    return frame, cursor
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LoaderResponseTimeout(cursor, description)
            self.frames.extend(self.decoder.feed(self.transport.read(1024, remaining)))

    def attach(self):
        if self.attached or self.invalidated:
            raise SessionError("attach requires a fresh target object")
        ready, self.cursor = self._wait_loader_frame(wire.TYPE_LOADER_READY, self.cursor, self.timeout, "READY")
        # Historical monitor v2 READY: api,max_data,api_base(2),caps(2),
        # load_min_page,load_end_page,workspace_page,stack_page,default_votes.
        if len(ready.payload) != 11:
            raise SessionError("monitor v2 READY must contain eleven bytes")
        api, max_data, _, _, cap_hi, cap_lo, low, high, workspace, stack, votes = ready.payload
        caps = (cap_hi << 8) | cap_lo
        required = 0
        for capability, bit in ((Capability.MEMORY_READ, wire.LOADER_V2_CAP_READ),
                                (Capability.MEMORY_WRITE, wire.LOADER_V2_CAP_LOAD),
                                (Capability.MEMORY_CALL, wire.LOADER_V2_CAP_CALL_RETURN | wire.LOADER_V2_CAP_RUN)):
            if capability in self.profile.capabilities:
                required |= bit
        if self.profile.replay_safe:
            required |= wire.LOADER_V2_CAP_RUN_REPLAY
        if api != 2 or max_data < self.profile.memory.max_chunk or caps & required != required:
            raise SessionError("monitor READY does not satisfy the target profile")
        if votes != 1:
            raise SessionError("raw monitor transport requires one-vote byte coding")
        for region in self.profile.memory.writable:
            if region.start < low << 8 or region.end > high << 8:
                raise SessionError("monitor READY memory window differs from the profile")
            if region.start < stack << 8 and region.end > workspace << 8:
                raise SessionError("authorized memory overlaps advertised workspace")
        self.attached = True
        return self

    def _require(self, capability, address, length):
        self.target_info.require(capability)
        if not self.attached or self.invalidated:
            raise SessionError("memory operation requires a live attached target")
        self.profile.memory.validate(address, length)
        # Keep only unread frames, including an early RETURN in the same read.
        del self.frames[:self.cursor]
        self.cursor = 0

    def _result(self, command, body, description):
        result, self.cursor, _ = self._loader_v2_result_command(command, self._next(), body, self.cursor, self.timeout, description)
        if result["status"] != wire.LOADER_STATUS_OK:
            raise SessionError(f"{description} rejected with status {result['status']}")
        return result

    def read_memory(self, address, length):
        self._require(Capability.MEMORY_READ, address, length)
        result = bytearray()
        for current, count in self.profile.memory.chunks(address, length):
            detail, data, self.cursor, _ = self._loader_v2_data_command(
                wire.TYPE_LOADER_V2_READ, self._next(), current.to_bytes(2, "big") + bytes((count,)),
                self.cursor, self.timeout, "READ")
            if detail["status"] != wire.LOADER_STATUS_OK or detail["address"] != current or len(data) != count:
                raise SessionError("READ response does not match the requested range")
            result.extend(data)
        return bytes(result)

    def write_memory(self, address, data):
        self._require(Capability.MEMORY_WRITE, address, len(data))
        for current, count in self.profile.memory.chunks(address, len(data)):
            chunk = data[current-address:current-address+count]
            detail = self._result(wire.TYPE_LOADER_V2_LOAD, current.to_bytes(2, "big") + chunk, "LOAD")
            if detail["address"] != current or detail["count"] != count or detail["crc16"] != crc16_ccitt(chunk):
                raise SessionError("LOAD did not verify the stored bytes")

    def call(self, address):
        self._require(Capability.MEMORY_CALL, address, 1)
        tx = self._next()
        execution_id = secrets.randbits(32)
        body = address.to_bytes(2, "big") + bytes((wire.LOADER_V2_RUN_CALL,)) + execution_id.to_bytes(4, "big")
        saved_attempts = self.loader_retries
        if not self.profile.replay_safe:
            self.loader_retries = 1
        try:
            detail, self.cursor, attempts = self._loader_v2_result_command(wire.TYPE_LOADER_V2_RUN, tx, body, self.cursor, self.timeout, "RUN")
            if detail["status"] != wire.LOADER_STATUS_OK or detail["address"] != address or detail["count"] != wire.LOADER_V2_RUN_CALL:
                raise SessionError("RUN was rejected or acknowledged a different address")
            deadline = time.monotonic() + self.timeout
            while True:
                returned, self.cursor = self._wait_loader_frame(wire.TYPE_LOADER_V2_RETURN, self.cursor, max(0.0, deadline-time.monotonic()), "RETURN")
                if returned.record_type != wire.TYPE_LOADER_V2_RETURN or not returned.payload or returned.payload[0] != tx:
                    if time.monotonic() >= deadline:
                        raise LoaderResponseTimeout(self.cursor, "RETURN")
                    continue
                if len(returned.payload) != 3 or returned.payload[1] != wire.LOADER_STATUS_OK:
                    raise SessionError("malformed or unsuccessful RETURN")
                return CallResult(execution_id, returned.payload[2], {"transaction": tx, "attempts": attempts})
        except (OSError, SessionError) as error:
            self.invalidated = True
            raise OutcomeUnknown(f"CALL outcome unknown; no automatic reconnect: {error}") from error
        finally:
            self.loader_retries = saved_attempts

    def close(self):
        self.invalidated = True
        self.transport.close()
