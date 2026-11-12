"""Read-only connection discovery; never retries memory writes or execution."""

import fcntl
import struct
import sys
import termios
import time

from . import protocol as p
from .host import Monitor, MonitorError


def configure_rate(port, path, baud):
    if baud in (41600, 62400):
        if sys.platform != "darwin":
            raise ValueError(
                "Custom W4 rates currently require the qualified macOS PL2303HXD adapter; use 9600"
            )
        from .usb_rate import USBRate, check_device

        device = check_device(path)
        usb = USBRate()
        try:
            fcntl.ioctl(port.fd, 0x80085402, struct.pack("Q", baud))
            return dict(device=device, **usb.set(baud))
        finally:
            usb.close()
    if baud not in (9600, 1200):
        raise ValueError("Unsupported W/M speed")
    attrs = termios.tcgetattr(port.fd)
    attrs[4] = attrs[5] = getattr(termios, f"B{baud}")
    termios.tcsetattr(port.fd, termios.TCSANOW, attrs)
    if termios.tcgetattr(port.fd)[4:6] != attrs[4:6]:
        raise RuntimeError("Serial rate readback mismatch")
    return dict(requested=baud, calculated_actual=baud)


def identify_at_rate(wire, timeout=3.0, *, monitor=None):
    """Allow a full discovery cycle; only identity/handshake operations repeat."""
    deadline = time.monotonic() + timeout
    monitor = monitor if monitor is not None else Monitor(wire, timeout)
    monitor.timeout = min(timeout, 0.35)
    last = None
    while time.monotonic() < deadline:
        try:
            monitor.identify()
            monitor.timeout = timeout
            return monitor
        except (TimeoutError, MonitorError) as exc:
            last = exc
            if (
                not monitor.usable
                or isinstance(exc, MonitorError)
                and exc.reply.status
                not in (p.UART, p.BAD_CRC, p.TIMEOUT, p.NOT_CONNECTED)
            ):
                raise
    raise TimeoutError(f"No complete ROM identification during discovery: {last}")


def discover(port, wire, path, baud="auto", timeout=3.0):
    attempts = []
    for rate in (62400, 41600, 9600, 1200) if baud == "auto" else (int(baud),):
        attempt = {"requested": rate}
        attempts.append(attempt)
        try:
            attempt["configuration"] = configure_rate(port, path, rate)
        except (ValueError, RuntimeError, OSError) as exc:
            attempt["error"] = str(exc)
            if baud != "auto":
                raise
            continue
        # Discard bytes decoded at the previous speed, but never reset the target.
        while port.read(4096, 0):
            pass
        try:
            m = identify_at_rate(wire, max(3.0, timeout))
            if m.identity.get("baud", rate) != rate:
                raise ValueError("ROM and host disagree about serial rate")
            return m, attempts
        except TimeoutError as exc:
            attempt["error"] = str(exc)
    raise TimeoutError(f"ROM discovery failed: {attempts}")
