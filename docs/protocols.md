# Protocol compatibility

This extraction does not change either wire format or the qualified firmware
bytes. `0.1.0` is the Python package version; it is not a shared wire version.

## DOS v1

`ravi.protocols.dos_v1` retains COBS framing with zero delimiters, the little-
endian `<BBBBIIH` header, CRC-16/CCITT-FALSE, TLVs, sequence numbers, command
IDs and existing limits (4096-byte payload, 4608-byte encoded-frame bound).
File checksums use CRC-32. File transfer, EXEC/EXEC_RESULT, update operations
and response/event semantics are unchanged.
The full field and command specification remains in
[DOSRAVI's protocol document](https://github.com/ddanila/dosravi/blob/main/docs/protocol.md).
C fixtures in the consumer and frozen independent byte vectors in RAVI guard
compatibility. Do not renumber commands to align them with the monitor.

## Monitor API v2

`ravi.protocols.monitor_v2` retains `A5 5A`, one-byte type, one-byte payload
length, payload and CRC-8/ATM over type/length/payload. The outer banner
protocol version remains 1, while the resident loader API version is 2.
V2 commands carry a one-byte transaction followed by command body and a
big-endian CRC-16/CCITT-FALSE over type, final payload length, transaction and
body. Address fields are 16-bit big-endian. LOAD/READ/CRC/RUN IDs and RESULT,
DATA, RETURN records are unchanged; the shared parser validates their lengths.

The raw adapter verifies READY's API, capabilities, maximum chunk, memory
window, workspace and one-vote byte coding against an explicit profile. The
historical 11-byte READY has page-sized bounds and no encoding for an exclusive
`0x10000` endpoint. It is unsuitable for arbitrary 32-bit addressing or every
possible 16-bit map. Such a target needs a separately versioned backend;
changing `MemoryLayout.address_bits` alone cannot change a wire protocol.
`MonitorCodec` consequently accepts only 16-bit layouts and chunks up to 249
bytes. Profile authorization can be narrower than READY's advertised window.

Juku's `0x4000..0xBFFF` authorized window, `0xC000..0xCFFF` workspace,
32-byte chunks, refresh commands, RAM survey encodings, Nano symbol repetitions,
solicited requests and reset policy live in its backend. A CPU with a similar
instruction set does not imply the same initialization or electrical link.

`tests/test_protocols.py` checks standard CRC vectors, frozen encoded packets,
all two-part stream splits, corruption and resynchronization. Consumer gates
also execute the unchanged C agent and Juku ROM against the extracted host.

## Extension rule

Reuse a codec only when the firmware really implements that dialect. Add new
optional capabilities without making unsupported operations appear available.
A wire-incompatible change requires another versioned codec/backend and its
own cross-language fixtures; retain the original codecs for existing targets.
