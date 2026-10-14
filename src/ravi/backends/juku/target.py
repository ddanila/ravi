"""Capability interface over a qualified, already bootstrapped Juku session."""

from ...execution import OutcomeUnknown
from ...targets import CallResult, Capability, TargetInfo
from .host import SessionError
from .profile import JUKU_MEMORY


class JukuTarget:
    target_info = TargetInfo(
        "juku",
        "monitor-v2+juku-symbols",
        frozenset(
            {
                Capability.MEMORY_READ,
                Capability.MEMORY_WRITE,
                Capability.MEMORY_CALL,
            }
        ),
        JUKU_MEMORY,
        replay_scope="bounded-agent-ram-cache",
    )

    def __init__(self, session, *, timeout=60.0):
        self.session = session
        self.timeout = timeout
        if (
            session.loader is None
            or session.loader.get("ready", {}).get("api_version") != 2
        ):
            raise SessionError("JukuTarget requires a bootstrapped loader v2 session")

    def read_memory(self, address, length):
        JUKU_MEMORY.validate(address, length)
        operation = self.session.run_resident_loader_v2(
            b"",
            "<ravi-read>",
            address,
            None,
            self.timeout,
            control_read_address=address,
            control_read_length=length,
        )
        return bytes.fromhex(operation["control_read"]["hex"])

    def write_memory(self, address, data):
        JUKU_MEMORY.validate(address, len(data))
        self.session.run_resident_loader_v2(
            data, "<ravi-write>", address, None, self.timeout
        )

    def call(self, address):
        JUKU_MEMORY.validate(address, 1)
        try:
            operation = self.session.run_resident_loader_v2(
                b"", "<ravi-call>", address, address, self.timeout
            )
        except (OSError, SessionError) as error:
            raise OutcomeUnknown(f"Juku CALL outcome unknown: {error}") from error
        run = operation["run"]
        return CallResult(
            int(run["execution_id"], 16), int(run["return_a"], 16), operation
        )
