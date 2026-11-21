# Qualification record — 2026-11-21

The **1.2** kit passed emulator qualification against clean DAC revision
`e078e8709ce4be98bfd9e6d1c941e3b353b127c9`. See [machine-readable evidence](qualification.json),
[contact sheet](contact-sheet.png), and the [ready ROMs](../images).

## Physical report and reproduced defect

The user's photo `PXL_20261121_103202676.MP.jpg` shows CRT 1.1's identity
screen with RAM F800h/work F700h. They report blinking about every 1.5 seconds
and no progression after two minutes. Version 1.1 incorrectly read CRT status
through the one-way A23.1 DS8282 latch shown on
[ZRE schematic sheet 2](https://www.sax.de/~zander/pc1715/pc_zres.pdf).
The emulator had incorrectly supplied readable 8275 status.

The regression reassembles the old polling loop into real firmware and injects
zero for unclaimed CRT input reads: it remains on pattern zero, with five
display starts and 274603 status reads in six seconds. This is a missing-flag
fault injection, not a claim that all physical floating buses read zero.
A separate run of the original 1.1 binary measured restarts every 1.378425
seconds, matching the reported symptom. The default emulated open bus is FFh.

Version 1.2 uses a calibrated CPU delay and executes no input instructions.
Under the same missing-flag condition, it advances through patterns 0, 1 and 2
in 22 seconds, with exactly three display starts and zero input reads.

## Completed checks

- Two complete cycles; 24 measured dwell intervals: **9.9996–10.0374 seconds**.
- All 25 cycle captures match the independent whole-frame renderer exactly.
- All twelve fixed builds match at initial capture, 10 seconds and 20 seconds;
  each starts the display exactly once, without periodic blanking/restarts.
- Zero input instructions in every positive run. Zero underruns, FIFO
  overflows, unexpected external writes or unclaimed reads.
- Wrong screen-port and address-bit mutations still fail raster comparison.
- Screen/work RAM failures, aliasing, all-RAM failure and native reset pass.
- DAC full test suite passes. RAVI: 106 tests, 47 skips; targeted lint passes.

This supersedes 1.1 qualification, which omitted the real board's one-way
CRT bus. Version 1.0 additionally had incorrect latch port/address selection.

Reproduce with `python3 tools/qualify_robotron1715_crt.py --dac ../dac-emulation`.
The JSON records DAC revision, image hashes, read/start counters and all three
negative controls. Raw rasters are 640×288; 4:3 previews are 640×480.

Only **A25.3 boot.bin** changes; both diagnostic glyph ROMs are byte-identical
to 1.0/1.1. Label the new chip **A25.3 vidtest 1.2**. Version 1.2 has not been
flashed or tested on hardware during this fix; physical validation is pending.
