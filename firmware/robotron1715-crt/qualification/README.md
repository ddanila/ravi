# CRT 1.3 qualification — 2026-11-21

Passed against clean DAC revision `97a82a98f2c17e7328337dc2ae6a96bcfa16835a`.
See [full results](qualification.json), [pattern gallery](contact-sheet.png),
[title-card example](title-example.png) and [ready images](../images).

## Defect and correction

The [1.2 hardware observations](hardware-observations-1.2.json) show gaps
repeated at character-row boundaries. The 8275's underline position above 7
blanks the first and last physical scanline; firmware incorrectly used BBh
(underline 11), and the emulator omitted this effect. Version 1.3 uses 6Bh
(underline 6), preserving twelve scanlines and all glyph data.

The [Intel datasheet](https://bitsavers.org/components/intel/8275/1984_8275.pdf),
Underline Placement, establishes the threshold. ZRE sheet 2 A16.3/A16.2
establishes that LTEN overrides VSP/reverse processing. Device tests cover
positions 7/8 and 6/11, both line-counter modes, cursor and field underline.

## Executed checks

- Two complete cycles plus the next title/pattern: 50 captures, all pixel-exact.
- Titles: **1.0175–1.0220 s**. Clean patterns:
  **10.0163–10.0171 s**.
- Each of twelve fixed builds displays its title once, then holds its pattern;
  exact captures after title removal, at 10 s and at 20 s.
- BBh negative variants reproduce boundary-line losses exactly in grid, circle,
  white and window images. The clean reference loses none of those pixels.
- Previous wrong-port, wrong-address and missing-status negative controls pass.
- Reset during title and pattern restarts correctly; screen/work RAM faults,
  aliases and all-RAM failure behave as specified.
- Positive runs have no CPU input operations, underruns, FIFO overflows or
  unexpected/unclaimed I/O. Two display starts per title/pattern pair.
- Full DAC test suite passes. RAVI: 106 tests, 47 skips; targeted lint passes.
- Both ordinary CP/M platform builds pass their actual-raster regression on
  the corrected model: [results](cpm-display-regression.json).

## Deliverable

Cycle A25.3 SHA-256:
`fd4afbddec93baf878ac7111149cf16168b69d0628643a46f81bc97929a07abd`.
The boot uses 2034 bytes, padded to 2048. Suggested label:
**A25.3 vidtest 1.3**. Both diagnostic glyph images are byte-identical to 1.0–1.2.

Version 1.3 has not been flashed or tested on physical hardware in this task.
This record supersedes 1.2's raster qualification; 1.2 did fix its predecessor's
status-polling stall, but its emulator did not model boundary-line suppression.

Reproduce: `python3 tools/qualify_robotron1715_crt.py --dac ../dac-emulation`.
