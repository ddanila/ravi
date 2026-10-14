# RAVI

Reusable host library for remote diagnostics. The Juku monitor and DOS agent
are separate protocol backends behind shared transport and target contracts.

See [the acceptance plan](docs/refactor-plan.md) for the migration scope.

## Provenance

The DOS v1 codec, transport and client were extracted from
[ddanila/dosravi](https://github.com/ddanila/dosravi) at d09777a.
The Juku host and monitor codec were extracted from
[ddanila/8080-cosim](https://github.com/ddanila/8080-cosim) at 4828c23a.
Target firmware and physical evidence remain in their original repositories.
