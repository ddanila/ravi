# PC1715 CRT diagnostic ROM kit

A standalone **ordinary PC1715**, **K7222.25 / 80×24** monitor diagnostic.
It needs the CPU, enough working main RAM, the display logic and the monitor.
There is no keyboard, disk, serial or external-bus dependency. This is not a
complete motherboard/RAM diagnostic, and cannot show a failure if the CPU or
video path cannot run.

**Status: emulator-qualified; not yet qualified on physical hardware.** No
physical machine was accessed or ROM programmed during development.

Ready images: [cycle kit](images/cycle), [fixed circle](images/fixed-circle),
and [all variants](images). See the [qualification record](qualification/README.md)
and [pattern contact sheet](qualification/contact-sheet.png).

## Build and qualify

From the ravi repository, with Python 3.10+ and `z80asm` installed:

```sh
python3 tools/build_robotron1715_crt.py
python3 tools/build_robotron1715_crt.py --pattern circle --out build/crt-circle
python3 tools/qualify_robotron1715_crt.py --dac ../dac-emulation
```

The first command creates `build/robotron1715-crt`. The qualifier builds and
executes the actual ROM on DAC's plain-PC1715 CPU/display model, checks two full
cycles, checks every fixed build at 10 and 20 seconds, and exercises rejected
screen RAM, rejected work RAM, screen/work aliasing, all-RAM failure and reset.
It produces raw 640×288 PNG/PPM captures, 640×480 aspect-correct previews,
`contact-sheet.png`, and `qualification.json` with measured dwell times,
addresses, counters, image hashes and the DAC source revision. Qualification
requires the companion DAC video implementation, not the older headless model.

The normal test suite checks compression round trips, stream grammar and FIFO
limits. DAC's independent hand-written device vectors check register aliases,
status, glyph addressing and bit order, bank XOR, reverse, intensity, cursor,
FIFO overflow, refresh-gated fetches, nominal timing, reset and runtime loading.
The qualifier's independent whole-frame renderer compares every captured pixel;
additional stripe, dot and all-black/all-white assertions check simple patterns.

## Images and sockets

| Output | Size | Socket / use |
|---|---:|---|
| `boot.bin` | 2048 | Mainboard A25.3, 2716 |
| `glyph-standard.bin` | 2048 | Standard character generator A25.2, 2716 |
| `glyph-alternate.bin` | 2048 | Additional character generator A25.1, 2716 |
| `glyphs.bin` | 4096 | Emulator only: standard followed by alternate |

All three physical images are exactly 2 KiB. The boot image is padded with FFh;
unused glyph bytes are zero. `manifest.json` records size, SHA-256, source hashes,
pattern variant, ROM use and socket mapping. `boot.asm` in the output directory
is the complete assembled source, including the generated compressed streams.
Do not program the combined `glyphs.bin` into either 2716.

Before a hardware trial, read and preserve **all three original ROMs**, including
socket labels and hashes; check that the board has the standard glyph wiring
and the intended 80×24 monitor configuration. Power down for ROM changes and
match each image to its labelled socket and orientation. Restore the original
three images together when finished. These glyphs replace the normal alphabet
and are intended only for this diagnostic kit. The optional quasi-graphics
jumper modification is not used.

## Screens

The cycle and contact-sheet order, left to right then top to bottom, is:

1. `identity`: version, configuration, selected screen and work addresses.
2. `grid`: outer border, central cross and grid.
3. `circle`: large circle and grid, corrected for the monitor's 4:3 active area.
4. `vertical`: alternating one-pixel vertical stripes.
5. `horizontal`: alternating one-scanline horizontal stripes.
6. `dots`: one lit pixel per 8×12 cell.
7. `checker`: one-pixel checkerboard.
8. `black`: all black.
9. `white`: all white at normal intensity.
10. `window`: small central white rectangle.
11. `glyphs`: both 128-code glyph banks.
12. `intensity`: normal/high patches and explicitly labelled 50% dithering.

Use any name with `--pattern` to hold it indefinitely; `cycle` is the default.
Reset restarts RAM selection and the first screen. A fixed build keeps scanout
running continuously, including across its internal 513-frame timer boundaries.

The raw circle looks elliptical on square-pixel software viewers. Use the 4:3
preview, or view the active raster at 4:3 on the CRT. Dithering is spatial
black/white texture, not additional analog grey levels. There are two actual
brightness outputs. These are original generated patterns and a small original
font; no Nokia or other proprietary artwork/ROM content is included.

## Firmware design and limits

The ROM stays mapped at 0000h–07FFh. Interrupts stay disabled. Before using a
stack it destructively probes 2 KiB screen candidates from F800h down to 0800h,
then 256-byte work candidates from FF00h down to 0800h outside that block.
Each probe fills and verifies address-dependent bytes and their complements.
It restores the screen signature before each work probe and verifies the screen
again afterwards to reject screen/work aliases. Stack and state occupy the
selected work page. This is a minimum-memory suitability check, **not** an
exhaustive RAM fault or retention test. A bad bank can cause a longer start.

If no suitable pair exists, the ROM repeats a finite search with video disabled;
it never calls a subroutine or pushes a return address onto untested RAM.
There is no visible all-RAM-failed message. If frame status stops arriving, a
bounded polling loop reinitializes the CRT. The screen reports hexadecimal
addresses; typical clean RAM selection is F800h with work page F700h.

The 8275 configuration is 80 columns, 24 visible plus 2 blank rows, 12 scanlines
per row and 28 horizontal blank character clocks. With the 13.824 MHz dot clock
this gives 16 kHz horizontal and about 51.282 Hz frame rate. A dwell is 513 frame
status events (about ten seconds), plus a short blanked decompression interval.
STOP blanks the display without stopping sync. There are at most 16 invisible
attributes per row; the builder/reference checks the FIFO and 2048-byte stream
limits. Pattern data uses a small LZ decoder and overlapping backward copies.

The schematic's A25.2 is bank zero and A25.1 bank one. Glyph address is
`line * 128 + code`; serial pixels are D7 first. Attribute GPA0 XOR latch DB6
selects the bank. The latch's five low bits select the 2 KiB main-RAM block.
Custom circle/grid tiles occupy bank one and spare low codes in bank zero.

The emulator models digital behavior and refresh-slot fetch availability. It
does not qualify electrical margins, CRT deflection, phosphor response, analog
levels, the monostable component tolerances or the physical EPROM wiring.

Sources: [PC1715 ZRE schematic, sheet 2](https://www.sax.de/~zander/pc1715/pc_zres.pdf),
[service manual, display section](https://www.sax.de/~zander/pc1715/doku/pc_serv.pdf),
and [Intel 8275 data sheet](https://bitsavers.org/components/intel/8275/1981_8275.pdf).
