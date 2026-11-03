# PC1715W/M custom ROM monitor W1

W1 is a new 2 KiB diagnostic ROM for the 2716 boot socket, not the stock S550
ROM and not the plain-PC1715 boot protocol. It starts its serial monitor without
floppies, OS, keyboard, or a working main-RAM stack. Source and binaries are in
`src/ravi/backends/robotron1715w/`. No PC001 hardware qualification is claimed.

## Build and host setup

Python 3.10+ and `z80asm` are required for development and relocatable helper
assembly. On the Mac, use Homebrew Python rather than Apple's Python 3.9:

```sh
brew install python z80asm
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m ravi.backends.robotron1715w.build --output build/w1/rom.bin
```

The builder writes a 2,048-byte image and a JSON hash/symbol map. The checked-in
binary must reproduce byte-for-byte. Unused EPROM bytes are FF. `helper.asm` is
assembled at the selected address; it is not part of the EPROM image.
The compact glyph designs are reused from DAC's original MIT diagnostic font.

The ROM configures **9600 8N1, no software or hardware flow control**. At the
reference 3.9936 MHz clock, CTC timer prescaler 16 and constant 26 provide 9600
SIO x1 clocks/s. Both ports 09h and 0Ah are programmed identically: the DAC model
routes channel 1, while MAME's W wiring routes channel 2. This discrepancy is
not resolved by emulator success. Confirm the actual board/straps and clocks
before assigning a hardware communication failure to RAM or this protocol.

```sh
.venv/bin/python -m ravi.backends.robotron1715w ports
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/probe-01 probe
```

Port discovery only lists candidates; it never opens them. All other commands
require an explicit port and a new log directory. The CLI closes the device
on success or failure and retains TX/RX streams, decoded events and a result.
TX logs record attempted transmission, not proof of physical delivery.

## Memory operations

Direct ROM operations use **selector 1's base physical RAM, 4000h–FFFFh**.
Read selector 0 remains active so instruction fetches continue from ROM; write
selector 0 addresses the same base RAM in that window. No main-RAM workspace is
reserved until a helper is installed.

```sh
# Destructive page survey; does not claim exhaustive DRAM qualification.
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/survey-01 survey 0x8000 0x1000
# Verified upload only; never implicitly executes.
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/load-01 load 0x8000 snippet.bin
# Stackless snippet with the ABI below.
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/run-01 run 0x8000
```

`fill address value` fills/verifies one aligned page. `read address length
--output file` refuses to overwrite an existing file. Surveys use 00/FF/55/AA
and low-address-byte patterns. They overwrite the selected pages. Passing these
checks is evidence for a candidate execution window, not proof of every cell,
refresh margin, address interaction or long-term reliability.

### Banked helper

`--helper address` surveys the complete pages containing the helper, uploads
and verifies it, then reserves its code, configuration, 64-byte buffer and
128-byte stack. This also overwrites those pages, even if they are outside the
requested diagnostic range. The CLI reinstalls it on each invocation; the Python
API can keep a verified helper for a whole campaign.

```sh
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/bank-load-01 --helper 0xf000 \
  load 0x0100 snippet.bin --bank 3
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/bank-run-01 --helper 0xf000 \
  run 0x0100 --bank 3
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/campaign-01 --helper 0xf000 \
  campaign 0x8000 0x1000 --banks 1 2 3 4
```

Addresses are `(bank selector, CPU address)`, not linear physical offsets:

| Selector | 0000–BFFF | C000–FFFF |
| --- | --- | --- |
| 1 | Base RAM | Base RAM |
| 2 | Second RAM bank | Base RAM, shared |
| 3 | Third RAM bank | Base RAM, shared |
| 4 | Fourth RAM bank | Base RAM, shared |

These are reference CAS-PROM mappings, not a dump of PC001's PROM. The reference
mapping exposes 208 KiB of distinct RAM through these selectors; do not count
the common upper region four times or claim all 256 KiB was tested.

A helper in C000h–FFFFh can switch all four read selectors while retaining its
code and stack. A helper below C000h supports selector 1, including its low RAM,
but rejects other read banks. This version does **not** execute unverified copies
in other banks to work around failed common RAM. If there is no working common
window, the ROM/direct monitor and a lower selector-1 helper remain usable.

Host APIs are `Monitor` (Ravi `MemoryTarget` contract, direct window) and
`BankedMonitor`, with `BankAddress(bank, address)`. Installing a helper requires
an explicit candidate address; the survey report helps choose one. Host code
checks helper instructions before every execution. Writes/fills/surveys cannot
overwrite the active helper region through these APIs. Move/reinstall a helper
in a new session to test its previous region.

Banked campaigns apply 00/FF/55/AA and low/high-address patterns, retaining failed
comparisons. Transport or execution uncertainty stops the campaign. They do not
silently reset the target or repeat an uncertain RUN.

## Execution and recovery ABI

ROM address 0000h is cold startup. **0003h is the cooperative return vector.**
The ROM uses CPU registers (including alternate registers, IX/IY byte registers
and I), not main RAM or display SRAM, for protocol state. NMI must remain
inactive: even a Z80 NMI pushes to a RAM stack. Maskable interrupts stay disabled.

**Direct stackless RUN:** entry is in base RAM 4000h–FFFFh, with ROM visible and
interrupts disabled. Preserve C, which holds the transaction ID. No valid SP is
provided. To return, disable interrupts, restore banking byte 00h through port
24h, put the result byte in A, and `JP 0003h`. Avoid CALL/RET/PUSH/POP unless the
snippet establishes a separately tested stack. Example: `LD A,42; JP 0003h`.

**Helper CALL:** entry may be in any supported bank/range. The helper establishes
read selector `bank`, write selector 1, and its tested 128-byte stack. The
snippet may clobber registers and returns A using `RET`. It must preserve a
mapping that exposes the helper and its stack, keep interrupts disabled, stay
within its stack, and leave the helper/workspace intact. The initial asymmetric
mapping is deliberate: stores target base RAM, not automatically the entry bank.
A snippet testing other banks must manage write selection explicitly. The helper
restores ROM visibility, retrieves the saved transaction ID and returns via 0003h.

`STARTED` is fully transmitted before execution begins. A returning snippet
causes serial reinitialization and a `RETURN` response, then command reception.
The host never retries RUN. Missing STARTED or RETURN makes execution
`OutcomeUnknown` and invalidates that host session. There is no durable execution
cache or remote boot identity. Creating a new host object is not evidence that
the board reset or a previous operation did not run.

Bounded ROM routines recover from bad frames, timeouts, receive errors and
reported RAM mismatches. A hung snippet, damaged helper/stack, physical bus
stall, failed ROM/CPU or lost return mapping needs an external reset. No external
watchdog/reset wiring is implemented here. The default execution deadline is
5 seconds; increase it explicitly for bounded longer snippets.

## Wire protocol W1

One outstanding request. All fields are bytes; address is little-endian.
CRC is CRC-16/CCITT-FALSE (1021h polynomial, FFFFh initial, no reflection/xorout),
sent high byte first. Sync is excluded from CRC. ROM has no packet buffer.

Request: `A5 op transaction bank address_lo address_hi value crc_hi crc_lo`.
Reply: `5A status transaction bank address_lo address_hi value crc_hi crc_lo`.
Transaction IDs 1–255 correlate requests; 0 is reserved for unsolicited startup.

| Op | Header value | Effect |
| --- | --- | --- |
| `I` | ignored | OK: bank=0, address=0800h, value=1 (W1) |
| `R` | count 1–64 | One DATA reply per byte, ascending address |
| `W` | count 1–64 | Receive `count` data bytes followed by a separate CRC16 |
| `F` | fill byte | Fill and verify one page; address must be page-aligned |
| `G` | ignored | STARTED, jump to address, cooperative RETURN |

Except I, direct commands require bank=1 and address>=4000h. Blocks must not
wrap past FFFFh. A valid W header authorizes streaming writes immediately;
failed/truncated payloads may leave **partial or complete unverified writes**.
A failed payload CRC is not a rollback. Every byte is immediately compared;
VERIFY reports a failing address and observed value (the last mismatch for W,
first for F). The host retains expected data and performs a second full readback
before claiming upload success. Successful W reports the exclusive end address
(modulo 65536) and value=0. Mutating operations are not automatically replayed.

Statuses: 0 OK, 1 STARTED, 2 RETURN, 3 BAD_CRC, 4 RANGE, 5 TIMEOUT, 6 UART,
7 VERIFY, 8 BAD_OP, 9 DATA. Only STARTED and RETURN describe execution, not OK.
An incomplete-header error can have transaction=0 or partial address fields;
these must not be treated as a completed request. Timeouts abandon parser state;
scan for the next sync and validate CRC before any action. Idle error flags are
cleared so a previous framing/overrun error cannot poison the next request.

The ROM waits indefinitely for commands but bounds individual byte and transmit
waits with CPU loops (roughly sub-second at the reference clock). After an
interrupted transfer, let the ROM's byte deadline expire before a fresh command.
Host default response deadline is 3 seconds. Serial failures may prevent an error
reply; the ROM still returns to reception instead of waiting forever to report it.

The display is output-only: title, WAIT HOST/LOAD, status word, hexadecimal
address/value, and RX received/total **within the current block**. Full-transfer
progress and detailed errors are in host logs. Screen updates never supply
protocol state or recovery information.

## Qualification and physical bring-up

```sh
python tools/qualify_robotron1715w.py --emulator ../dac-emulation \
  --cas ../dac/public/media/robotron/cas.bin --output build/w1-qualification
```

The emulator commit is pinned in `tools/robotron1715w-emulator.json`. With no
`--cas`, the runner generates explicitly synthetic CAS test data for CI; it is
not a specimen PROM. The runner executes assembled instructions through the
modeled CPU, banking, CTC/SIO and display, without guest-PC shortcuts. Tests trap
main-RAM accesses at startup, randomize display memory, inject faults and serial
failures, exercise banked copies/returns and stop on hung snippets. The emulator's
independent fixed-baud output decoder also has an x1 start-bit regression test.

For PC001, first retain/read back the original EPROM and identify the exact chip,
board and CAS PROM. Program a spare compatible 2716, verify the entire 2 KiB,
and install only with power off. Confirm X5 RS-232 TX/RX/GND and the serial clock
route. Start with identification and display only, then survey a deliberately
chosen scratch range, verify an upload, and run a short cooperative snippet.
Only then install the helper and expand to banked diagnostics. Keep the original
S550 intact. Record physical results under PC001 separately from emulator tests.

No hardware serial port is opened by builds or qualification. Emulator results
cannot establish analog timing, real DRAM retention/refresh, PC001 ROM/PROM
identity or recovery from arbitrary CPU faults.

## Bounded diagnostic snippets

The `diagnose` command builds, surveys, uploads and runs a small **stackless**
RAM diagnostic, then reads a structured result and rechecks the immutable code.
It never retries execution. These are destructive tests: the selected target
range and the complete pages containing the workspace are overwritten.

```sh
# Sixteen walking-one/walking-zero comparisons at a single byte.
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/data-lines-01 \
  diagnose data-lines 0x8000 1 --workspace 0xf000
# Fill the entire range, then verify it, for 00/FF/55/AA.
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/ram-patterns-01 \
  diagnose ram-patterns 0x8000 0x1000 --workspace 0xf000
# Separate low/high CPU-address-byte passes expose aliases within this range.
.venv/bin/python -m ravi.backends.robotron1715w \
  --port /dev/cu.usbserial-110 --log-dir sessions/address-lines-01 \
  diagnose address-lines 0x0100 0x1000 --workspace 0xf000 --bank 3
```

Ranges are limited to 4096 bytes per invocation; `data-lines` requires exactly
one byte. A passing address test covers distinctions **within the selected
range**, not every address pin or interactions with other banks/ranges. The
pattern test is not a March/coupling/retention test. Longer campaigns should run
explicitly selected bounded windows and retain each result.

The workspace must begin at 4000h or above; banks 2–4 require C000h or above so
code and its result remain visible while both read and write selectors switch.
Unlike helper CALL's asymmetric initial mapping, these snippets deliberately
select the **same target bank for reads and writes** and restore ROM visibility
before returning. They do not need a helper or a RAM stack. Target bytes may not
overlap workspace survey pages or an installed helper. Candidate workspace
failure stops before RUN. The ABI preserves the transaction ID in the verified
workspace and returns through ROM vector 0003h.

Each run writes `diagnostic/snippet.asm`, `snippet.bin`, `manifest.json` and
`result.json` alongside the usual serial evidence. The generated assembly can be
rebuilt directly with `z80asm`; source templates ship in the wheel. The manifest
records relocation, target bank/range, hash, result address, zero stack usage and
a conservative bound of `20000 + 1000 * length` Z80 T-states for the snippet
itself on the reference mapping, without external WAIT/bus stalls. Preparation,
serial transfers and ROM return handling are additional. Execution has a
five-second host deadline. A fault that changes instructions/control flow may
violate the intended bound and require external reset.

The ten-byte result record is `WD1`, kind (1=data, 2=patterns, 3=address), status
(0=pass, 1=mismatch), failure address (little-endian), expected byte, actual byte,
and completion marker A5. The marker is written last; untouched status is FF.
The host checks signature, kind, marker, returned accumulator and code readback.
Missing/corrupt/inconsistent results invalidate the session. Failure results
contain the first observed mismatch and do not claim successful restoration of
original contents. Use the JSON `passed` flag or CLI exit status for automation;
transport/execution errors stop the run and remain in the evidence.

## Independent MAME qualification and additional faults

```sh
.venv/bin/python tools/qualify_robotron1715w_mame.py \
  --mame mame --media ../dac/public/media/robotron --output build/w1-mame
```

Tested with MAME 0.289 `rt1715w`, using the supplied CAS and keyboard ROM and the
unchanged W1 boot image. The harness connects only a loopback TCP socket to
MAME's null-modem device at its default 9600 8N1, flow control off. CPU execution,
SIO/CTC2 clocking, bank transfers, helper CALL/RET and the three diagnostics all
run inside unmodified MAME. Lua only reads PC and captures startup/final screens;
it neither patches memory nor implements commands. Historical ROM files are
removed from the output after execution; hashes, serial bytes, logs, generated
observer script, screenshots and report remain. The custom boot-ROM checksum
warning is expected. MAME is optional and this test needs caller-supplied media;
the normal CI still runs the pinned DAC fixture with synthetic CAS test data.

The Homebrew 0.289 build crashed when an earlier observer installed Lua I/O taps.
The released runner avoids those taps. Main-RAM-free startup is checked by DAC's
access traps, not claimed as a separately instrumented MAME result. MAME's actual
screen scanout is captured independently; this is still not physical validation.
Reference wiring is in [MAME's versioned driver](https://github.com/mamedev/mame/blob/mame0289/src/mame/robotron/rt1715.cpp),
with serial framing in its [null-modem device](https://github.com/mamedev/mame/blob/mame0289/src/devices/bus/rs232/null_modem.cpp).

The expanded DAC suite drops/duplicates each byte of command headers and write
payloads, corrupts replies, injects resets at partial-frame boundaries and during
an active write, corrupts a helper return address, injects address aliases and
invalidates corrupted diagnostic results. The fixture's reset retains RAM but
resets CPU/devices; it is not a power-cycle/DRAM-retention model.

A startup banner received after a matched response now invalidates the host
session. It cannot be mistaken for successful completion of an interrupted
write or RUN. Initial attach accepts the startup banner; there is still no
persistent boot identity, so a lost banner cannot provide reset detection.
Partial writes survive reset in the fixture and are never represented as rolled
back. The ROM does not deduplicate complete valid frames: duplicated valid RUNs
could execute twice. The host never automatically retransmits mutations or RUN,
and no exactly-once guarantee is claimed for a transport that duplicates frames.
