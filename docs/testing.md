# Tests and updates

`make check` runs the library contract tests, the distinct-layout example,
Ruff and formatting. Tests include frozen DOS/Juku wire vectors, every split
of those frames, malformed replies, inner/outer checksum distinctions, stale
reply deadlines, capability/range rejection, replay/uncertain outcomes, and
real POSIX PTY/socket transport ownership, EOF and partial-I/O behavior.

Library CI checks Python 3.10 and 3.12 and installs the built wheel into a fresh
virtual environment outside the source checkout. Product compatibility remains
covered by actual consumer integration, not just the synthetic peer:

| Consumer | Gate |
| --- | --- |
| DOSRAVI | `make check`; `make dos-test` (8086 and 80186 locally, 8086 ordinary CI); C decoder fuzz on decoder changes |
| Jukuravi | T28 loader/attach/replay and public memory API; T34 PIT initialization; all T36 contract/RAM/raster groups; retained older regression lane |

Firmware build checks compare generated Juku ROMs to the checked-in bytes.
These tests do not add physical qualification for either machine or for a 1715.

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
