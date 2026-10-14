import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from ravi.backends.dos.client import Client
from ravi.backends.juku.target import JukuTarget
from ravi.backends.monitor import MonitorTarget
from ravi.execution import CompletionDeadline, OutcomeUnknown
from ravi.monitor import SessionError
from ravi.protocols import monitor_v2 as wire
from ravi.targets import (
    AddressRange,
    Capability,
    FileTarget,
    MemoryLayout,
    MemoryTarget,
    UnsupportedOperation,
)
from ravi.testing.monitor import DEMO_PROFILE, MonitorPeer
from ravi.transport import LoopbackTransport


class TargetTests(unittest.TestCase):
    def target(self, peer=None, profile=DEMO_PROFILE):
        peer = peer or MonitorPeer(profile)
        target = MonitorTarget(peer.transport(), profile, timeout=0.01).attach()
        self.addCleanup(target.close)
        return peer, target

    def test_non_juku_layout_chunked_verified_transfer_and_call(self):
        peer, target = self.target()
        self.assertIsInstance(target, MemoryTarget)
        self.assertFalse(isinstance(target, FileTarget))
        payload = bytes(range(117))
        target.write_memory(0x8107, payload)
        self.assertEqual(target.read_memory(0x8107, len(payload)), payload)
        result = target.call(0x8107)
        self.assertEqual(result.accumulator, 0x42)
        self.assertEqual(peer.calls, 1)
        self.assertEqual(
            [len(body) - 2 for cmd, _, body in peer.requests if cmd == 0x25],
            [16] * 7 + [5],
        )

    def test_range_and_capability_rejection_precede_any_wire_write(self):
        peer, target = self.target()
        for address, length in [
            (0x4000, 1),
            (0x9FFF, 2),
            (0xA000, 1),
            (-1, 1),
            (0x8000, 0),
        ]:
            with (
                self.subTest(address=address, length=length),
                self.assertRaises(ValueError),
            ):
                target.read_memory(address, length)
        self.assertEqual(peer.requests, [])
        read_only = replace(
            DEMO_PROFILE, capabilities=frozenset({Capability.MEMORY_READ})
        )
        peer, target = self.target(profile=read_only)
        with self.assertRaises(UnsupportedOperation):
            target.write_memory(0x8000, b"x")
        self.assertEqual(peer.requests, [])
        client = Client(LoopbackTransport(lambda data: b""))
        self.assertIsInstance(client, FileTarget)
        self.assertFalse(isinstance(client, MemoryTarget))
        with self.assertRaises(UnsupportedOperation):
            client.target_info.require(Capability.MEMORY_CALL)

    def test_reserved_regions_and_address_wrap(self):
        layout = MemoryLayout(
            (AddressRange(0x8000, 0xC000),), (AddressRange(0xA000, 0xB000),)
        )
        for address, length in [(0x9FFF, 2), (0xA800, 1), (0xFFFF, 2)]:
            with self.assertRaises(ValueError):
                layout.validate(address, length)
        with self.assertRaises(ValueError):
            MemoryLayout((AddressRange(0, 0x10001),))
        with self.assertRaises(ValueError):
            MemoryLayout((AddressRange(0, 10), AddressRange(9, 11)))

    def test_boot_contract_mismatch_is_rejected(self):
        for payload in (
            b"\x02",
            bytes((2, 8, 0, 0, 0x3F, 0xFF, 0x80, 0xA0, 0xA0, 0xB0, 1)),
            bytes((2, 16, 0, 0, 0, 0, 0x80, 0xA0, 0xA0, 0xB0, 1)),
            bytes((2, 16, 0, 0, 0x3F, 0xFF, 0x80, 0xA0, 0x90, 0xB0, 1)),
        ):
            transport = LoopbackTransport(lambda data: b"")
            transport.pending.append(wire.encode_frame(wire.TYPE_LOADER_READY, payload))
            with self.assertRaises(SessionError):
                MonitorTarget(transport, DEMO_PROFILE).attach()

    def test_lost_run_ack_replays_same_id_without_second_side_effect(self):
        peer, target = self.target()
        handler = target.transport.handler
        dropped = False

        def lose_once(data):
            nonlocal dropped
            reply = handler(data)
            if not dropped:
                dropped = True
                return b""
            return reply

        target.transport.handler = lose_once
        self.assertEqual(target.call(0x8000).accumulator, 0x42)
        self.assertEqual(peer.calls, 1)
        self.assertEqual(len(peer.requests), 2)
        self.assertEqual(peer.requests[0], peer.requests[1])

    def test_lost_return_is_unknown_and_does_not_auto_reexecute(self):
        peer, target = self.target()
        handler = target.transport.handler
        target.transport.handler = lambda data: handler(data)[
            :-8
        ]  # drop RETURN, retain ACK
        with self.assertRaises(OutcomeUnknown):
            target.call(0x8000)
        self.assertEqual(peer.calls, 1)
        self.assertEqual(len(peer.requests), 1)
        with self.assertRaises(SessionError):
            target.call(0x8000)
        self.assertEqual(peer.calls, 1)

    def test_no_replay_capability_never_retries_uncertain_run(self):
        profile = replace(DEMO_PROFILE, replay_safe=False)
        peer, target = self.target(profile=profile)
        handler = target.transport.handler

        def lose(data):
            handler(data)
            return b""

        target.transport.handler = lose
        with self.assertRaises(OutcomeUnknown):
            target.call(0x8000)
        self.assertEqual(peer.calls, 1)
        self.assertEqual(len(peer.requests), 1)

    def test_new_boot_during_call_prevents_replay(self):
        peer, target = self.target()
        target.transport.handler = lambda data: peer.ready()
        with self.assertRaises(OutcomeUnknown):
            target.call(0x8000)
        self.assertTrue(target.invalidated)

    def test_repaired_frame_crc_cannot_hide_wrong_read_or_write_ack(self):
        for operation, index in (("read", 4), ("read", 5), ("write", 5), ("write", 8)):
            with self.subTest(operation=operation, index=index):
                _, target = self.target()
                handler = target.transport.handler

                def corrupt(data):
                    frame = wire.StreamDecoder().feed(handler(data))[0]
                    payload = bytearray(frame.payload)
                    payload[index] ^= 1
                    return wire.encode_frame(frame.record_type, bytes(payload))

                target.transport.handler = corrupt
                with self.assertRaises(SessionError):
                    if operation == "read":
                        target.read_memory(0x8000, 2)
                    else:
                        target.write_memory(0x8000, b"ab")

    def test_juku_call_forces_call_mode_and_invalidates_after_uncertainty(self):
        session = SimpleNamespace(
            loader={"ready": {"api_version": 2}}, loader_run_mode="jump"
        )

        def fail(*args):
            self.assertEqual(session.loader_run_mode, "call")
            self.assertTrue(session.ravi_call_active)
            raise SessionError("lost return")

        session.run_resident_loader_v2 = Mock(side_effect=fail)
        target = JukuTarget(session)
        with self.assertRaises(OutcomeUnknown):
            target.call(0x4000)
        self.assertEqual(session.loader_run_mode, "jump")
        self.assertFalse(session.ravi_call_active)
        with self.assertRaises(SessionError):
            target.call(0x4000)
        with self.assertRaises(SessionError):
            JukuTarget(session)
        session.run_resident_loader_v2.assert_called_once()

    def test_completion_deadline_is_not_extended_by_duplicate_started(self):
        completion = CompletionDeadline(10)
        completion.start(2, 3)
        completion.start(4, 3)
        self.assertEqual(completion.deadline, 5)
        self.assertEqual(completion.remaining(6), 0)
        with self.assertRaises(OutcomeUnknown):
            completion.check_retry()


if __name__ == "__main__":
    unittest.main()
