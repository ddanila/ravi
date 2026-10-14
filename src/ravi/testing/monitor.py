"""A synthetic monitor with a different map and no Juku physical assumptions."""

from ..backends.monitor import MonitorProfile
from ..integrity import crc16_ccitt
from ..protocols import monitor_v2 as wire
from ..targets import AddressRange, Capability, MemoryLayout
from ..transport import LoopbackTransport

DEMO_PROFILE = MonitorProfile(
    "synthetic-monitor",
    MemoryLayout(
        (AddressRange(0x8000, 0xA000),), (AddressRange(0xA000, 0xB000),), max_chunk=16
    ),
    frozenset(
        {Capability.MEMORY_READ, Capability.MEMORY_WRITE, Capability.MEMORY_CALL}
    ),
    replay_safe=True,
)


class MonitorPeer:
    """Reference protocol endpoint. CALL increments a counter, never runs code."""

    def __init__(self, profile=DEMO_PROFILE):
        self.profile = profile
        self.memory = bytearray(65536)
        self.decoder = wire.StreamDecoder()
        self.calls = 0
        self.executions = {}
        self.requests = []

    def ready(self):
        caps = wire.LOADER_V2_CAPABILITIES
        layout = self.profile.memory
        low = min(r.start for r in layout.windows) >> 8
        high = max(r.end for r in layout.windows) >> 8
        return wire.encode_frame(
            wire.TYPE_LOADER_READY,
            bytes(
                (
                    2,
                    layout.max_chunk,
                    0,
                    0,
                    caps >> 8,
                    caps & 255,
                    low,
                    high,
                    high,
                    high + 0x10,
                    1,
                )
            ),
        )

    def transport(self):
        transport = LoopbackTransport(self.receive)
        transport.pending.append(self.ready())
        return transport

    @staticmethod
    def result(tx, command, address=0, count=0, crc=0, status=0, length=0):
        return wire.encode_frame(
            wire.TYPE_LOADER_V2_RESULT,
            bytes(
                (
                    tx,
                    status,
                    command,
                    length,
                    address >> 8,
                    address & 255,
                    count,
                    crc >> 8,
                    crc & 255,
                    0,
                )
            ),
        )

    def receive(self, data):
        reply = bytearray()
        for frame in self.decoder.feed(data):
            try:
                tx, body = wire.validate_loader_v2_command(frame)
            except ValueError:
                reply.extend(wire.encode_frame(wire.TYPE_LOADER_ERROR, b"\x06"))
                continue
            self.requests.append((frame.record_type, tx, body))
            command = frame.record_type
            address = int.from_bytes(body[:2], "big")
            if command == wire.TYPE_LOADER_V2_LOAD:
                payload = body[2:]
                try:
                    self.profile.memory.validate(address, len(payload))
                    if len(payload) > self.profile.memory.max_chunk:
                        raise ValueError("chunk")
                except ValueError:
                    reply.extend(self.result(tx, command, status=4))
                    continue
                self.memory[address : address + len(payload)] = payload
                reply.extend(
                    self.result(
                        tx, command, address, len(payload), crc16_ccitt(payload)
                    )
                )
            elif command == wire.TYPE_LOADER_V2_READ:
                if len(body) != 3:
                    reply.extend(self.result(tx, command, status=3))
                    continue
                count = body[2]
                try:
                    self.profile.memory.validate(address, count)
                except ValueError:
                    reply.extend(self.result(tx, command, status=4))
                    continue
                payload = bytes(self.memory[address : address + count])
                reply.extend(
                    wire.encode_frame(
                        wire.TYPE_LOADER_V2_DATA,
                        bytes((tx, 0, command, address >> 8, address & 255, count))
                        + payload,
                    )
                )
            elif command == wire.TYPE_LOADER_V2_RUN:
                if len(body) != 7 or body[2] != 0:
                    reply.extend(self.result(tx, command, status=3))
                    continue
                try:
                    self.profile.memory.validate(address, 1)
                except ValueError:
                    reply.extend(self.result(tx, command, status=4))
                    continue
                execution = body[3:]
                if execution in self.executions and self.executions[execution] != body:
                    reply.extend(self.result(tx, command, status=2))
                    continue
                if execution not in self.executions:
                    self.calls += 1
                    self.executions[execution] = body
                reply.extend(self.result(tx, command, address))
                reply.extend(
                    wire.encode_frame(wire.TYPE_LOADER_V2_RETURN, bytes((tx, 0, 0x42)))
                )
            else:
                reply.extend(self.result(tx, command, status=2))
        return bytes(reply)
