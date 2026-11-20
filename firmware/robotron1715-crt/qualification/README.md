# Qualification record — 2026-11-20

The packaged kit passed emulator qualification against DAC revision
`9d9915fdc32e2d8727a7a10a9bac48db808e6e5b` with a clean DAC working tree.
See [machine-readable evidence](qualification.json) and the labelled
[contact sheet](contact-sheet.png). Raw rasters preserve the 640×288 pixel grid;
`*-4x3.png` previews correct the aspect ratio to 640×480.

- Two complete cycles, 24 measured dwell intervals: **9.9992–10.0203 seconds**.
- All 25 captured cycle images exactly matched the independent stream renderer.
- All twelve fixed builds matched at initial capture, 10 seconds and 20 seconds.
- Zero display underruns, FIFO overflows, unexpected I/O or unclaimed reads.
- Clean pseudorandom RAM: screen F800h, work F700h.
- Failed top screen block: screen F000h, work EF00h.
- Failed preferred work page or work-to-screen alias: screen F800h, work F600h.
- All RAM failed: no display fetches, no stack use, bounded ROM search retries.
- Native reset: booted again and reproduced the initial screen/addresses.
- The ROM overlay remained enabled in every run.

Additional checks:

- DAC `make test` passed, including existing plain-PC1715 serial/IRQ and W/M
  regression tests plus the new CRT device vectors.
- DAC runtime, plain-PC1715 and new CRT tests passed AddressSanitizer and UBSan.
- ravi unittest suite: 106 tests, OK with 47 fixture-dependent skips.
- New Python files passed Ruff lint and formatting checks.
- Repository-wide `make check` reached lint and failed on 146 existing lint
  errors in local bench scripts and unrelated existing files; those files were
  not changed for this work.

Reproduce with `python3 tools/qualify_robotron1715_crt.py --dac ../dac-emulation`.
The JSON records ROM and raster hashes. Each image manifest also records hashes
of the generator and firmware source. The ready images are under
[../images](../images); generated assembly is included alongside each variant.

This evidence qualifies the software against the documented digital emulator
model. It does not qualify the physical board, monitor or EPROM programming.
