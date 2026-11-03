# W1 baseline

Unchanged ROM from Ravi commit `345a4fd69c32d37c92589d04d3052765aa54c06f`.
SHA-256: `646d9b812b277b967024d2b31aff7c567b5004823d07ea1f7dbb1cae319b09e7`.

The current host identifies W1 and retains its legacy per-byte read protocol.
This baseline has no serial-first stages, build fingerprint or ROM CRC sweep.
Its assembler output is the final image; W2 requires the Python build step to
insert its fingerprint and CRC. Neither image is physically qualified on PC001.
