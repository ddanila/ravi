# RAVI

RAVI is the reusable Python host library for Jukuravi and DOSRAVI. It shares
byte transports, integrity functions, monitor transactions and capability
contracts while preserving the existing DOS v1 and Juku monitor v2 protocols.
Target firmware, product commands and physical qualification remain in the
consumer repositories.

Python 3.10+ on POSIX hosts; runtime uses only the standard library.

```sh
python3 -m pip install -e '.[test]'
make check
python3 examples/memory_monitor.py
```

The example transfers and verifies memory at `0x8000` with 16-byte chunks on
a synthetic monitor. Its CALL increments a counter and returns `A=42`; it
does not emulate a CPU or initialize a Robotron board.

| Use case | Public interface | Implementation |
| --- | --- | --- |
| DOS files and processes | `FileTarget` | `ravi.backends.dos.client.Client` |
| Bootstrapped Juku resident monitor | `MemoryTarget` | `HostSession.as_target()` and its memory methods |
| Another byte-stream monitor v2 target | `MemoryTarget` | `MonitorTarget(transport, profile).attach()` |

Discover support through `target.target_info.capabilities`; unsupported
operations are not emulated. CALL returns an accumulator and target evidence;
EXEC retains DOS status, captured output and execution-journal behavior.

Read [architecture and ownership](docs/architecture.md),
[protocol compatibility](docs/protocols.md),
[adding a target](docs/adding-targets.md), and
[testing and dependency updates](docs/testing.md).
The [acceptance plan](docs/refactor-plan.md) records the extraction scope.

## Plain Robotron PC1715 stock-ROM bootstrap

The experimental [1715 bench procedure](docs/robotron1715.md) provides a V.24
handshake, raw binary upload/jump and a bundled Z80 RAM/serial smoke test:

```sh
python3 -m ravi.backends.robotron1715 --port /dev/ttyUSB0 \
  --log-dir sessions/MB001-first-smoke smoke
```

Connect the three-wire RS-232 cable described in that procedure and reset the
board while the command waits. No EPROM replacement or specimen ROM dump is
required. This is a separate stock-ROM protocol, not monitor API v2 or a full
Robotron port of Jukuravi. The published ROM's loader instructions pass the
optional Z80 harness; physical MB001 qualification remains pending.

## Provenance

The DOS v1 codec, transport and client were extracted from
[ddanila/dosravi](https://github.com/ddanila/dosravi) at `d09777a`.
The Juku host and monitor codec were extracted from
[ddanila/8080-cosim](https://github.com/ddanila/8080-cosim) at `4828c23a`.
Compatibility modules in both repositories retain their existing import paths
and entry points; each consumer pins this library by Git commit.
