"""PL2303HXD endpoint-zero rate override; leaves Apple serial driver attached."""

import atexit
import ctypes as c
import plistlib
import struct
import subprocess
import sys


def check_device(serial):
    if sys.platform != "darwin":
        raise RuntimeError("PL2303 override currently requires macOS")
    roots = plistlib.loads(
        subprocess.check_output(["ioreg", "-a", "-l", "-p", "IOService"])
    )
    found = {}

    def walk(node):
        if (
            node.get("idVendor") == 0x067B
            and node.get("idProduct") == 0x2303
            and "bDeviceClass" in node
        ):
            found[node.get("locationID")] = node
        for child in node.get("IORegistryEntryChildren", []):
            walk(child)

    for root in [roots] if isinstance(roots, dict) else roots:
        walk(root)
    if len(found) != 1:
        raise RuntimeError("Need exactly one connected PL2303 adapter")
    node = next(iter(found.values()))
    if node.get("bcdDevice") != 0x400 or node.get("bcdUSB") != 0x110:
        raise RuntimeError("Only verified PL2303HXD descriptors are supported")

    def has_port(n):
        return n.get("IOCalloutDevice") == serial or any(
            has_port(x) for x in n.get("IORegistryEntryChildren", [])
        )

    if not has_port(node):
        raise RuntimeError("Serial path does not belong to the PL2303 device")
    return {
        "location": node["locationID"],
        "vid": 0x067B,
        "pid": 0x2303,
        "revision": 0x400,
    }


class USBRate:
    def __init__(self):
        u = self.u = c.CDLL("/opt/homebrew/lib/libusb-1.0.dylib")
        u.libusb_init.argtypes = [c.POINTER(c.c_void_p)]
        u.libusb_init.restype = c.c_int
        u.libusb_open_device_with_vid_pid.argtypes = [
            c.c_void_p,
            c.c_uint16,
            c.c_uint16,
        ]
        u.libusb_open_device_with_vid_pid.restype = c.c_void_p
        u.libusb_control_transfer.argtypes = [
            c.c_void_p,
            c.c_uint8,
            c.c_uint8,
            c.c_uint16,
            c.c_uint16,
            c.c_void_p,
            c.c_uint16,
            c.c_uint,
        ]
        u.libusb_control_transfer.restype = c.c_int
        u.libusb_close.argtypes = [c.c_void_p]
        u.libusb_exit.argtypes = [c.c_void_p]
        self.ctx = c.c_void_p()
        assert u.libusb_init(c.byref(self.ctx)) == 0
        self.h = u.libusb_open_device_with_vid_pid(self.ctx, 0x067B, 0x2303)
        if not self.h:
            raise RuntimeError("Cannot open PL2303 device")
        atexit.register(self.close)

    def close(self):
        if self.h:
            self.u.libusb_close(self.h)
            self.h = None
            self.u.libusb_exit(self.ctx)

    def get(self):
        b = (c.c_ubyte * 7)()
        r = self.u.libusb_control_transfer(self.h, 0xA1, 0x21, 0, 0, b, 7, 1000)
        if r != 7:
            raise RuntimeError(f"GET_LINE_CODING failed {r}")
        return bytes(b)

    def set(self, rate):
        if rate == 9600:
            encoded = struct.pack("<I", rate)
            actual = rate
        else:
            mantissa = 384000000 // rate
            exponent = 0
            while mantissa >= 512:
                mantissa >>= 2
                exponent += 1
            assert 1 <= mantissa <= 511 and exponent <= 7
            encoded = bytes(
                [mantissa & 255, (exponent << 1) | (mantissa >> 8), 0, 0x80]
            )
            actual = (384000000 // mantissa) >> (exponent * 2)
        # Explicit 8N1: do not inherit unreliable GET_LINE_CODING framing.
        coding = encoded + bytes([0, 0, 8])
        b = (c.c_ubyte * 7).from_buffer_copy(coding)
        r = self.u.libusb_control_transfer(self.h, 0x21, 0x20, 0, 0, b, 7, 1000)
        if r != 7:
            raise RuntimeError(f"SET_LINE_CODING failed {r}")
        readback = self.get()
        if readback != coding:
            raise RuntimeError(
                f"line coding mismatch {readback.hex()} != {coding.hex()}"
            )
        return {
            "requested": rate,
            "calculated_actual": actual,
            "coding": coding.hex(),
            "error_percent": 100 * (actual / rate - 1),
        }
