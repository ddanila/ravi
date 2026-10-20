# Tests and updates

`make check` runs the library contract tests, the distinct-layout example,
Ruff and formatting. Tests include frozen DOS/Juku wire vectors, every split
of those frames, malformed replies, inner/outer checksum distinctions, stale
reply deadlines, capability/range rejection, replay/uncertain outcomes, and
real POSIX PTY/socket transport ownership, EOF and partial-I/O behavior.

Library CI checks Python 3.10 and 3.12 and installs the built wheel into a fresh
virtual environment outside the source checkout. The product compatibility workflow checks out pinned consumer harnesses and
explicitly replaces each consumer's `third_party/ravi` checkout with the candidate
library commit. It runs DOS native/8086 agent integration and Juku T28/T34 ROM
integration. Backend-only changes select that product; shared or unknown changes
select both; prose-only changes skip both. Consumer revisions are fixed in the
workflow so unrelated consumer changes cannot silently alter a library result.
Advance those harness pins deliberately when product tests evolve.

The consumers retain their full regression gates:

| Consumer | Gate |
| --- | --- |
| DOSRAVI | `make check`; `make dos-test` (8086 and 80186 locally, 8086 ordinary CI); C decoder fuzz on decoder changes |
| Jukuravi | T28 loader/attach/replay and public memory API; T34 PIT initialization; all T36 contract/RAM/raster groups; retained older regression lane |

Firmware build checks compare generated Juku ROMs to the checked-in bytes.
These tests do not add physical qualification for either machine or for a 1715.

The [plain-1715 bootstrap procedure](robotron1715.md) includes an optional
historical-ROM Z80 instruction fixture. On 2026-10-20, all 43 library tests
passed with that fixture enabled, including the CLI/logging path and injected
RAM failure. The smoke payload rebuild matched its shipped binary. An isolated
wheel installation includes the CLI, assembly source and binary. This does not
qualify physical MB001 or cold boot without its floppy controller.

## Updating a consumer pin

1. Test the candidate library, including the affected consumer against that
   candidate checked out inside `third_party/ravi`.
2. Publish the library commit to `ddanila/ravi`.
3. Advance the consumer gitlink. In DOSRAVI also update the exact Git revision
   in its `ravi-core` package dependency; they must agree.
4. Run the consumer gates, commit and push the consumer update. Check its hosted
   results. To test a new library candidate, change the submodule checkout
   explicitly; do not use a sibling `PYTHONPATH` override.

Fresh source setup is `git submodule update --init third_party/ravi` after
cloning either consumer. Juku's emulator gates also require the existing
`third_party/dac-emulation`, `third_party/zmac` and `third_party/juku-common`
submodules as specified by each gate.

CI skips expensive product checks for documentation-only changes. A RAVI pin
change selects DOS native/actual-agent tests or the Juku consumers respectively;
it does not require unrelated analog/LVS work. Unknown changes remain
conservative. Consumer firmware and physical evidence stay in their own repos.


## Extraction evidence (2026-10-14)

The implementation revision `c07e38c` passed 27 library behavior tests and the
synthetic extension example, plus isolated wheel installation. Hosted library
CI passed on Python 3.10 and 3.12. Three additional selector tests cover the
product compatibility CI policy.

DOSRAVI `1cd4676` passed its 51-test native suite, C protocol tests, Ruff,
cppcheck, real DOSBox-X agent integration on both 8086 and 80186, and isolated
installed-CLI verification. Jukuravi `9e8059b7` passed T28 (including the shared
memory API), T34 and all T36 groups locally, including full RAM and raster
retention. Follow-up `6589ccd4` adds the RAVI checkout to the rev B serial-vector
consumer's CI job and includes that consumer in dependency selection. Its serial
console test and selector checks passed locally. The consumer workflow retains
the older ROM regressions as well.

Published checks:

- [RAVI Python 3.10/3.12 contracts and installed wheel](https://github.com/ddanila/ravi/actions/runs/38515759787)
- [RAVI candidate against DOS and Juku product harnesses](https://github.com/ddanila/ravi/actions/runs/38515759740)
- [DOSRAVI native, packaging, fuzz and actual-agent CI](https://github.com/ddanila/dosravi/actions/runs/38515705086)
- [Juku full consumer CI after the dependency correction](https://github.com/ddanila/8080-cosim/actions/runs/38516019995)

The first three completed successfully; the linked Juku run records the final
hosted outcome. None of these results adds physical qualification.

Both consumers pin the implementation revision; subsequent library CI and prose
changes need no consumer pin bump because they do not alter installed code.
