# Architecture and ownership

RAVI shares mechanisms that have the same contract. The two wire protocols
remain separate. A target advertises capabilities through immutable
`TargetInfo`; `MemoryTarget` and `FileTarget` describe distinct operation sets.
A DOS process exit status is not a monitor's returned accumulator.

| Layer | Responsibility | Kept outside it |
| --- | --- | --- |
| `transport.py` | ordered bytes, deadlines, ownership, logging | reset, reconnect, commands, execution retry |
| `integrity.py` | CRC-8/ATM, CRC-16/CCITT-FALSE, incremental CRC-32 | framing and board configuration |
| `protocols/dos_v1.py` | existing DOS framing, TLVs and commands | filesystems and UART setup |
| `protocols/monitor_v2.py` | monitor framing, strong command CRC, layout-aware codec | Juku addresses and symbol coding |
| `monitor.py` | bounded, transaction-correlated monitor exchange | physical symbol transmission, memory layout |
| `backends/dos/client.py` | file transfer, EXEC, execution journal | DOS agent firmware and product CLI |
| `backends/juku/` | Juku handshake, Nano link, refresh, diagnostics, resident operations | other board initialization |
| `backends/monitor.py` | raw byte-stream monitor adapter with explicit profile | bootstrap, reset, clock, SIO setup |

Juku's host module remains substantial: its diagnostic policies, evidence and
solicited physical link are target-specific. Its command exchange engine and
wire codec are shared with the raw monitor adapter. The compatibility CLI in
8080-cosim supplies the historical log directory. DOSRAVI keeps its CLI,
reference agent, DOS agent, launchers and programmer workflows.

## Transport contract

`write(data)` sends all bytes or raises. Failure can mean a prefix was sent.
`read(size, timeout)` returns up to size bytes, returns empty bytes for idle or
zero-size reads, and raises on EOF. No transport reconnects or replays commands.
Serial and socket writes have an independent five-second total timeout; partial
progress does not restart it. Monitor response processing has one deadline per
attempt, so stale frames cannot extend that wait. A transport's blocking write
is bounded by its own timeout, not interrupted by the protocol response timer.

`SerialTransport` owns its descriptor, configures raw 8N1 and restores the
original attributes on close; descriptor release still occurs if restoration
fails. Opening a physical adapter can itself affect control lines according to
the OS/driver: target reset wiring must be qualified. `FDTransport` accepts an
already nonblocking descriptor, owns a duplicate by default, or borrows it with
`duplicate=False`; it never changes baud, termios or DTR. Closing the wrapper
closes only owned resources. `SocketTransport` owns its connection.
`LoggedTransport` delegates close to its underlying transport; callers own the
log streams. TX logs record attempted transmission, not proof of delivery.

## Execution uncertainty

`OutcomeUnknown` means the caller must reconcile the remote result before
submitting another side effect. DOS STARTED starts one completion deadline;
duplicate STARTED cannot extend it and timeout after STARTED never triggers an
automatic EXEC retry. Existing DOS execution journals and recovery entry points
are preserved.

Monitor retries retain the same transaction and execution ID. The raw adapter
permits RUN retries only when both the qualified profile and READY advertise
replay support; otherwise it makes one attempt. Missing RETURN, disconnect or
an observed new boot makes CALL uncertain and invalidates that adapter. The
Juku capability facade also invalidates the shared session after an uncertain
CALL and always selects CALL mode, independent of a CLI JUMP setting. Creating
another facade over that same session does not clear the invalidation.

Both existing wire protocols have volatile, bounded execution caches and no
remote boot identity: `boot_identity` remains `None`. An unobserved target reset
can erase replay state. Nothing here promises durable exactly-once execution.
The legacy Juku CLI retains its qualified retry/evidence behavior; the new
capability facade adds the explicit uncertainty boundary. A caller must not
silently reconnect and repeat an unknown operation.

## Dependency ownership

Consumers check out `third_party/ravi` at a reviewed Git revision. Their source
bootstraps select that checkout regardless of working directory and reject an
already-imported library from another source, even if its version matches.
DOSRAVI's wheel declares the same exact Git revision as a package dependency.
Juku's source entry point requires its submodule. Neither searches sibling
working trees or relies on a global editable installation.
