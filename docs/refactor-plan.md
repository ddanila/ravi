# RAVI generalization acceptance plan

RAVI owns the reusable host library. Jukuravi and DOSRAVI retain their product
commands, physical evidence, target firmware, and qualification gates. Their
existing wire dialects remain explicit, versioned backends; capability-level
operations do not pretend memory CALL and DOS EXEC are identical.

Completion requires:

1. A standalone, installable standard-library-only Python package, with
   transport ownership/deadline/logging contracts and shared integrity code.
2. Versioned protocol implementations separated from target memory maps,
   bootstrap/reset policy, diagnostics and physical symbol coding.
3. Working memory and file/execution target interfaces, implemented by both
   existing clients and used by their real entry points. Compatibility imports,
   CLI behavior, output evidence and qualified ROM bytes remain stable.
4. Explicit execution uncertainty and volatile replay scope; neither transport
   retries nor target reconnects may invent durable exactly-once guarantees.
5. A runnable target-extension example and contract tests using a distinct
   memory layout, to prove extension requires no Juku address/CPU assumptions.
   Robotron 1715 hardware initialization remains unimplemented until qualified.
6. Dependency pins and packaging proven from fresh checkouts/isolated installs;
   consumers cannot accidentally use a developer's sibling source directory.
7. Shared-library tests plus both consumer regression gates and economical CI.
   Tests must exercise real library behavior, malformed input, timeouts and
   side-effect replay, not merely check interface names or source text.
8. Architecture, protocol compatibility and target-author documentation;
   all repositories committed and pushed to ddanila-owned remotes, green CI.

The current golden baseline is DOSRAVI d09777a and 8080-cosim 4828c23a.
The source modules and their retained history remain available in those repos.
