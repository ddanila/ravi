"""Run with `python examples/memory_monitor.py` after installing ravi-core.

This is a protocol simulator: it does not execute Z80/8080 instructions or
claim that a Robotron board is initialized, working, or safe to CALL.
"""

from ravi.backends.monitor import MonitorTarget
from ravi.testing.monitor import MonitorPeer

peer = MonitorPeer()
target = MonitorTarget(peer.transport(), peer.profile).attach()
try:
    payload = b"target-independent chunked memory transfer"
    target.write_memory(0x8000, payload)
    assert target.read_memory(0x8000, len(payload)) == payload
    result = target.call(0x8000)
    print(
        f"{target.target_info.target}: verified transfer, simulated A={result.accumulator:02X}"
    )
finally:
    target.close()
