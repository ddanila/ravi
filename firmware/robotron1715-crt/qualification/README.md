# Qualification record — 2026-11-21

The corrected **1.1** kit passed emulator qualification against DAC revision
`07449fbb51b256ced62739540fde8cbce616ac6d` with a clean DAC working tree.
See [machine-readable evidence](qualification.json) and the labelled
[contact sheet](contact-sheet.png). Raw rasters preserve the 640×288 pixel grid;
`*-4x3.png` previews correct the aspect ratio to 640×480.

- Two complete cycles, 24 measured dwell intervals: **9.9849–10.0224 seconds**.
- Negative controls with the old floppy-port write and old address-bit mapping
  both produced incorrect rasters; the former also reached external/floppy I/O.
- All 25 captured cycle images exactly matched the independent stream renderer.
- All twelve fixed builds matched at initial capture, 10 seconds and 20 seconds.
- Zero display underruns, FIFO overflows, unexpected I/O or unclaimed reads.
- Clean pseudorandom RAM: screen F800h, work F700h.
- Failed top screen block: screen F000h, work EF00h.
- Failed preferred work page or work-to-screen alias: screen F800h, work F600h.
- All RAM failed: no display fetches, no stack use, bounded ROM search retries.
- Native reset: booted again and reproduced the initial screen/addresses.
- The ROM overlay remained enabled in every run.

The previous 1.0 qualification was invalid for screen selection: the ROM and
emulator shared the wrong port (22h instead of 34h) and wrong address-bit
assignment (D0–D4 instead of D1–D5). Version 1.1 corrects both and this report
supersedes the old model-dependent result. The service-manual I/O table and
schematic A23.2/A22.4/X12 wiring are the independent references.

Reproduce with `python3 tools/qualify_robotron1715_crt.py --dac ../dac-emulation`.
The JSON records ROM and raster hashes, the two rejected mutants, DAC revision
and clean-tree status. Each image manifest records firmware/generator hashes.
The ready images are under [../images](../images).

Only **A25.3 boot.bin** changes; both 2716 glyph images are byte-identical to 1.0.
Previously burned A25.3 1.0 images need replacement/reprogramming before testing
this fix. No physical hardware was accessed and no EPROM was programmed during
this investigation. Digital emulator success does not qualify the analog monitor.
