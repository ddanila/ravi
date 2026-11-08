# Plain PC1715 stock-ROM bootstrap / MB001 bench procedure

Status, 2026-11-01: **MB001 stock-ROM handshake and serial-loaded code execution
verified on hardware** with a Prolific PL2303. The original smoke payload took
its RAM-failure path for `8000h..80FFh`; this does not identify a failed RAM chip.
The recoverable monitor below is emulator-tested and ready for its first board
run. This target is the plain 64 KB PC1715, not the 1715M/S550 profile in DAC.

## Cable and serial setup

Use motherboard **X5 V.24**, not X4 printer. Three wires to a conventional
PC DTE DE-9 RS-232 adapter:

| Robotron contact | Direction/function | Host DE-9 contact |
| --- | --- | --- |
| A1 | signal ground | 5 |
| A3 | Robotron TX -> host RX | 2 |
| B4 | host TX -> Robotron RX | 3 |

The authoritative contact drawing is in the [service manual, printed p.112,
PDF p.114](https://www.tiffe.de/Robotron/PC1715/PC-1715-Servicemanual.pdf#page=114).
Its numbering alternates rows: A1, B2, A3, B4, etc. Confirm the connector
orientation from that drawing; the cable solder side is mirrored. Some web
instructions incorrectly call TX "A2". Do not copy that label.

Use actual RS-232 voltage levels, not a bare TTL USB UART. Power the motherboard
normally and separately. Leave RTS/CTS/DSR/DTR/DCD unconnected; the ROM sets
WR3=C1h (auto-enables off), WR5=68h and polls RR0. No flow-control loops are
needed. Disable host hardware flow control and XON/XOFF.

Nominal speed: 9600 baud. The ROM writes WR4=49h: x16, eight-bit data configured
in WR3/WR5, odd parity, **1.5 stop bits**. POSIX termios cannot express 8O1.5.
The tool deliberately requests **8O2** on the host, giving additional transmit
idle time. Reception of the ROM's 1.5-stop-bit response depends on the adapter;
this combination succeeded on MB001 with the PL2303 on 2026-11-01. `--stop-bits 1` is an explicit
alternative for an adapter that cannot receive that response in 8O2. Neither
setting changes the Robotron. Record the actual setting in the session.

## Ready-to-run commands

From this repository:

```sh
python3 -m pip install -e .

# Handshake only. Power on while this waits.
python3 -m ravi.backends.robotron1715 --port /dev/ttyUSB0 \
  --log-dir sessions/MB001-probe-01 probe

# Power-cycle again: the probe leaves the ROM waiting for commands.
python3 -m ravi.backends.robotron1715 --port /dev/ttyUSB0 \
  --log-dir sessions/MB001-smoke-01 smoke

# Own raw binary, linked for 4000h, optionally execute it.
python3 -m ravi.backends.robotron1715 --port /dev/ttyUSB0 \
  --log-dir sessions/MB001-upload-01 upload program.bin \
  --address 0x4000 --entry 0x4000
```

Use a fresh log directory for each run. It contains exact `tx.bin`, `rx.bin`
and `result.json`, including serial settings and what was actually verified.
On macOS use the adapter's `/dev/cu.*` device. No physical port has been opened
during preparation.

Defaults: 30-second handshake deadline and 2 ms additional delay after each
uploaded byte. `--timeout`, `--byte-delay`, `--baud` and `--stop-bits` precede
the subcommand. Byte pacing is conservative, not a qualified throughput limit.
After timeout, interrupted upload, disconnect or unexpected output, power-cycle and
start a new stock-loader session. The onboard button is not the CPU reset. There is no automatic LOAD/EXEC replay.

`probe` succeeds only on `12 12`. `upload` success means bytes were sent after
that handshake, **not** that RAM contents or execution were verified.
`smoke` succeeds only after the payload's exact success banner and all 256
echoed byte values match. A blank display is expected; no keyboard or display
initialization is used by the payload.

## ROM contract and memory

Source: Christian Corti's [annotated R1715BT disassembly](https://www.tiffe.de/Robotron/PC1715/EPROM/r1715bt.lst)
and [2048-byte ROM](https://www.tiffe.de/Robotron/PC1715/EPROM/r1715bt.bin).
Reference ROM SHA-256:

```
51cb80639b5667f2611da71ce7305061566cf3474bda7db6fc82709d08e46d01
```

The ROM copies 0000h..07FFh into RAM, removes the ROM overlay, establishes
SP=0995h and clears working memory. It attempts four floppy drive numbers,
then calls `BootV24` at 05D7h, repeating if unsuccessful. Whether an absent
floppy controller permits this path on MB001 is not yet established.

| Exchange | Bytes |
| --- | --- |
| Host solicitation | `11 11` |
| ROM reply | `12 12` |
| Host LOAD | `0A address_lo address_hi length_lo length_hi data...` |
| Host EXEC | `AA entry_lo entry_hi` |

Words are little-endian. The command parser and UART polling use ports 0Fh
(SIO B control/status) and 0Dh (data); CTC channel 1 is port 09h. LOAD has no
checksum, ACK or readback. The ROM supports repeated LOAD commands; this
initial host intentionally permits one image per session and an entry inside
that image. Zero length would underflow the ROM counter, so it is rejected.
After a LOAD, an invalid command byte can return to the floppy loop.

The host authorizes only **4000h..BFFFh**, with no wrapping. This conservatively
preserves copied loader code, its stack/workspace and upper memory. It is
narrower than the ROM's own 0800h lower-bound check. An uploaded program must
establish its own execution environment; EXEC is a jump, not a supported
returning CALL.

## Bundled smoke payload

Original MIT-licensed [Z80 source](../src/ravi/backends/robotron1715/smoke.asm)
and matching binary ship with the package. It runs at 4000h, disables interrupts,
uses no stack/ROM calls, and preserves the loader's serial/CTC configuration.
It destructively tests **8000h..80FFh** using 00/FF/55/AA per-byte patterns,
then writes and checks a page-wide low-address pattern. It emits:

- `R1715 RAM OK\r\n`, then polls and echoes bytes indefinitely; or
- `R1715 RAM FAIL!`, then halts.

The host sends 00..FF one byte at a time, waiting for each exact echo. This
checks eight-bit binary transparency, including NUL, 11h, 12h, 13h and AAh.
It is a small RAM/serial smoke test, not a complete RAM, address-bus or CPU
qualification. It does not verify every uploaded byte.

Rebuild (Debian `z80asm`):

```sh
z80asm -o src/ravi/backends/robotron1715/smoke.bin \
  src/ravi/backends/robotron1715/smoke.asm
```

## Validation and remaining hardware work

`make check` covers framing vectors, bounds, handshake fragmentation/noise,
lost responses, partial writes, failed EXEC/no replay, input validation before
opening a port, and serial configuration with existing 8N1 defaults preserved.
With `z80asm` installed it also verifies that the shipped binary matches source.

An optional harness executes the **unmodified historical loader instructions**
on the external chips Z80 core, with ideal byte-level SIO I/O:

```sh
RAVI_PC1715_ROM=/path/to/r1715bt.bin \
RAVI_CHIPS_DIR=../dac-emulation/third_party/cpu/chips \
PYTHONPATH=src python3 -m unittest discover -s tests -p test_robotron1715.py -v
```

This test checks the ROM hash before use and does not download or redistribute
the ROM. Preparation used the core in dac-emulation commit
`d71829a993c864e4583bf209c1babf19f739c079`.
It enters BootV24 after the ROM-to-RAM stage, exercises handshake, actual LOAD
and EXEC instructions, the RAM test and all 256 echoes. Injecting a stuck/error
read at 8055h produces the failure banner. Both paths passed on 2026-10-20.
It does **not** emulate cold boot, floppy detection, CTC baud timing, SIO FIFO
timing, RS-232 hardware, or the actual board.

Next physical evidence: MB001 reaches `12 12` with its actual attached hardware;
record adapter/framing settings; run the smoke test and retain its logs. Until
then this remains experimental. A full resident memory/CALL monitor, custom
diagnostic ROM and RAM-independent DTR milestones are separate work.

## Recoverable serial diagnostic

Load the 720-byte `monitor.bin` at `4000h`. All feedback and commands use the
same serial cable; no screen, keyboard or logic analyzer is required. It keeps
interrupts disabled and retains the stock SIO setup. A normal test failure
reports details and returns to `READY`, rather than HALTing.

```sh
# Board initially OFF. Run this, then power on when the host is waiting.
PYTHONPATH=src python3 -m ravi.backends.robotron1715.monitor_cli \
  --port /dev/ttyUSB0 --log-dir sessions/MB001-diag-01 deploy \
  --reference-rom /path/to/verified-2048-byte-ROM.bin

# Subsequent commands: leave the board powered, no ROM handshake or restart.
PYTHONPATH=src python3 -m ravi.backends.robotron1715.monitor_cli \
  --port /dev/ttyUSB0 --log-dir sessions/MB001-page-81 test 81
PYTHONPATH=src python3 -m ravi.backends.robotron1715.monitor_cli \
  --port /dev/ttyUSB0 --log-dir sessions/MB001-read-8000 read 8000 256
```

`deploy` handshakes with the stock ROM, uploads/executes the monitor, then reads
back **every uploaded code byte** and requires an exact match before any tests.
It saves the low page `0000h..00FFh` and optionally compares it with the reference
ROM, runs the same RAM test on page `00` and page `80`, verifies the low page
was restored, and verifies that the monitor still answers afterwards. The
reference file is a comparison, not a ROM replacement.

The boot ROM copies itself to RAM and disables its overlay; the low page is
therefore an especially useful control area. Its startup clears memory but
does not perform a real RAM test. A working low page does not prove page `80`
is good. Test outcomes are separate from command success in `result.json`:
`success` means the requested exchange completed; `all_tested_pages_passed`
and individual `passed` fields describe RAM results.

Each page test saves 256 bytes, fills and verifies twenty patterns (00, FF,
55, AA, walking ones and walking zeros), then an address-byte pattern, and
attempts to restore the saved page on both pass and failure. It stops at the
first mismatch. Failure lines have this form:

```text
TEST 80
FAIL P 8055 FF FB 04 FB
READY
```

Fields: phase (`P` uniform pattern or `A` address pattern), address, expected
byte, first actual byte, XOR difference, second immediate read. In this example
D2 read low when expected high. These results localize an effect, not a chip.
Failed storage or physical aliasing can prevent perfect restoration.

Memory layout: code `4000h..42CFh`; backup buffer `4C00h..4CFFh`; variables at
`4E00h`; stack starts at `0990h`, in the already-used boot-stack area. Page tests
reject `08..0F` and `40..4F`. They allow the low ROM-copy pages `00..07` because
execution is elsewhere and interrupts are disabled. Physical address aliasing
can bypass software protection; CPU/monitor corruption still needs a restart.
This is not a full RAM-retention/refresh test or a hardware watchdog.

The host also supports `write ADDRESS FILE` for a 1–256-byte chunk within one
page and `call ADDRESS`. Writes below `1000h` and within `4000h..4FFFh` are
rejected. The monitor receives the complete chunk into scratch memory before
writing, then returns actual memory readback; the host verifies it. A callable
payload can `RET` to the monitor, retaining serial recovery. It must preserve
the stack and serial configuration. A payload that never returns takes control
and is not automatically recoverable. The resident monitor itself is protected
from overwrite; replacing it requires a fresh loader session.

Wire commands: `?`; `R` plus little-endian address and count; `T` plus page;
`W` plus address/count/data; `G` plus address. Count zero means 256. All responses
end with `READY\r\n`. Invalid commands/ranges and incomplete parameters return
an error. Incomplete writes time out before committing; idle reception waits
for commands, and transmitter polling is bounded. There is no automatic replay
on a lost response. These are binary commands: use the host tool, not a terminal
that appends newline characters.

Validation uses the actual assembled monitor and historical ROM loader on the
chips Z80 core: healthy RAM, read-bit inversion, stuck-low/high D2, lost writes,
A0 aliasing, continued commands after failures, control-page restoration,
protected ranges, partial-write timeout, upload/readback and call/return. The
original smoke test is also checked on healthy/faulty RAM. This is a byte-level
SIO model, not electrical/baud-rate validation of the new monitor on MB001.

## Handing the open transport to a runtime service

`Monitor.start(address, timeout=15)` sends the monitor G command and consumes
exactly `GO\r\n`. It does not wait for another READY prompt, close the port,
flush input, or retry execution after a timeout. Bytes sent by the guest after
GO remain queued for the runtime service. Use this method instead of a normal
monitor command when transferring ownership to an N4/NetDisk host; pass the
same open descriptor to that service. The caller must verify the uploaded
program before starting it. A failed handoff requires diagnosis, not replay of
the execution command. `tests/test_robotron_handoff.py` exercises this boundary.

`SerialTransport(..., exclusive=True)` acquires a nonblocking descriptor lock
and POSIX TIOCEXCL before changing termios. The owner can pass inherited copies
to a runtime service and retain its original descriptor across service restarts.
Close releases exclusivity even when restoring disconnected-device settings
fails. The default remains non-exclusive for existing callers. The Robotron
CP/M unattended supervisor additionally checks visible existing owners before
opening the physical device.
