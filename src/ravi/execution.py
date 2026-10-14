"""Execution lifetime accounting, independent of a wire dialect."""

from dataclasses import dataclass

from .transport import TransportError


class OutcomeUnknown(TransportError):
    """Execution may have happened; reconciling side effects is caller policy."""


@dataclass
class CompletionDeadline:
    """STARTED can extend a request deadline once, never once per duplicate."""

    deadline: float
    started: bool = False

    def start(self, now: float, completion_timeout: float) -> None:
        if not self.started:
            self.started = True
            self.deadline = now + completion_timeout

    def remaining(self, now: float) -> float:
        return max(0.0, self.deadline - now)

    def check_retry(self) -> None:
        if self.started:
            raise OutcomeUnknown(
                "EXEC completion timed out after STARTED; outcome unknown; "
                "request was not retransmitted"
            )
