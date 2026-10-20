# Adding a target

Start with the target's actual operations and boot contract. A CPU family is
not an interface. For a plain board, a memory/CALL monitor may be useful long
before files or process execution exist.

1. Record CPU/address width, ROM placement, usable memory windows, monitor
   workspace and stack, clock/reset behavior and the physical transport.
2. Implement board bootstrap separately: initialize only the needed hardware,
   then establish an ordered byte link. Keep reset and early feedback explicit.
3. If firmware implements monitor API v2, supply a `MonitorProfile` and use
   `MonitorTarget`. Otherwise implement a versioned codec and the applicable
   target interface; transports and integrity helpers remain reusable.
4. Advertise only supported capabilities. Validate requested windows and reserved
   memory before sending bytes. Set `replay_safe=True` only after qualifying
   execution-ID caching and duplicate-command behavior in that firmware.
5. Run malformed-frame, fragmentation, lost-ACK, lost-RETURN, EOF, reset and
   reserved-range tests. Add a firmware/emulator fixture exercising the real
   instructions and peripheral path, then record physical qualification.

See [the executable example](../examples/memory_monitor.py) and
[the synthetic peer](../src/ravi/testing/monitor.py). Its `0x8000..0x9FFF`
window and 16-byte chunks exercise different parameters from Juku; its CALL
only counts invocations. It is a protocol test fixture, not target firmware.
For an already bootstrapped byte-stream monitor, integration looks like:

```python
from ravi.backends.monitor import MonitorProfile, MonitorTarget
from ravi.targets import AddressRange, Capability, MemoryLayout
from ravi.transport import FDTransport

# fd is already open, configured and nonblocking by the board driver.
profile = MonitorProfile(
    "my-qualified-monitor",
    MemoryLayout((AddressRange(0x8000, 0xA000),), max_chunk=16),
    frozenset({Capability.MEMORY_READ, Capability.MEMORY_WRITE}),
)
with FDTransport(fd) as transport:
    target = MonitorTarget(transport, profile).attach()
    target.write_memory(0x8000, b"test")
    assert target.read_memory(0x8000, 4) == b"test"
```

READY must be available after bootstrap. The raw adapter does not perform the
Juku solicitation handshake or automatically probe/reset an unknown board.
Attach can reject a profile even when its CPU and UART seem compatible.

## Robotron 1715 preparation

An experimental [plain-1715 stock-ROM bootstrap](robotron1715.md) now exists.
It uses the published R1715BT V.24 routine and includes a RAM/serial smoke
payload. It does not implement the memory/CALL monitor interface or a new
diagnostic ROM. Physical qualification of MB001, including cold startup with
the separate floppy controller absent, remains pending. A full monitor still
needs its own board profile and firmware acceptance fixture.

An early DTR/control-line indication is a reasonable board-level experiment:
it can show progress before framed serial traffic works, provided the chosen
output and its initialization are confirmed from the circuit. Keep this
feedback independent of RAM-dependent protocol code. Distinguish ROM entry,
minimal peripheral initialization, basic RAM/stack readiness and monitor READY
in the board's evidence. Do not assume that a connector pin, reset polarity or
printer/keyboard direction follows from another machine's design.

The first acceptance fixture should boot the new ROM, observe those milestones,
transfer verified bytes within an explicit safe window, CALL a returning stub,
and inject reset/lost-response failures. Physical success must be recorded
separately from synthetic host tests and any emulator result.
