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
        if getattr(session, "ravi_invalidated", False):
            raise SessionError(
                "Juku capability session invalidated; establish a new session explicitly"
            )
        if (
            session.loader is None
            or session.loader.get("ready", {}).get("api_version") != 2
        ):
            raise SessionError("JukuTarget requires a bootstrapped loader v2 session")

    def _check(self, address, length):
        if getattr(self.session, "ravi_invalidated", False):
            raise SessionError("Juku capability session invalidated")
        JUKU_MEMORY.validate(address, length)

    def read_memory(self, address, length):
        self._check(address, length)
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
        self._check(address, len(data))
        self.session.run_resident_loader_v2(
            data, "<ravi-write>", address, None, self.timeout
        )

    def call(self, address):
        self._check(address, 1)
        saved_mode = self.session.loader_run_mode
        self.session.loader_run_mode = "call"
        self.session.ravi_call_active = True
        try:
            operation = self.session.run_resident_loader_v2(
                b"", "<ravi-call>", address, address, self.timeout
            )
        except (OSError, SessionError) as error:
            self.session.ravi_invalidated = True
            raise OutcomeUnknown(f"Juku CALL outcome unknown: {error}") from error
        finally:
            self.session.loader_run_mode = saved_mode
            self.session.ravi_call_active = False
        run = operation["run"]
        return CallResult(
            int(run["execution_id"], 16), int(run["return_a"], 16), operation
        )
