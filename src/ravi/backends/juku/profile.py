"""Qualified Juku monitor RAM ABI; no generic core defaults to this map."""

from ...targets import AddressRange, MemoryLayout

JUKU_MEMORY = MemoryLayout(
    writable=(AddressRange(0x4000, 0xC000),),
    reserved=(AddressRange(0xC000, 0xD000),),
    max_chunk=32,
)
