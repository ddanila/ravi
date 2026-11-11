"""Exhaustive actual-opcode W4 CCITT CRC proof, including register contract."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from ravi.backends.robotron1715w.build import ROOT, build_rom

DAC = Path(os.environ.get("RAVI_W_EMULATOR", ROOT.parents[4] / "dac-emulation-wm"))


@unittest.skipUnless(
    (DAC / "common/cpu/z80.c").exists(), "set RAVI_W_EMULATOR for CPU CRC proof"
)
class CrcTests(unittest.TestCase):
    def test_exhaustive(self):
        image, labels = build_rom("W4")
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "rom.bin").write_bytes(image)
            (d / "test.c").write_text(r"""
#include "common/cpu/z80.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static unsigned char mem[65536];
static uint8_t rd(void *p,uint16_t a){(void)p;return mem[a];}
static void wr(void *p,uint16_t a,uint8_t v){(void)p;(void)a;(void)v;assert(0);}
static unsigned crc(unsigned c,unsigned b){c^=b<<8;for(int i=0;i<8;i++)c=((c<<1)^((c&0x8000)?0x1021:0))&65535;return c;}
int main(int argc,char **argv){assert(argc==3);FILE *f=fopen(argv[1],"rb");assert(f);assert(fread(mem,1,2048,f)==2048);fclose(f);mem[0x9000]=0x76;
unsigned entry=atoi(argv[2]);unsigned long long max=0;dac_z80 c;dac_z80_bus bus={.read=rd,.write=wr};
for(unsigned state=0;state<65536;state++)for(unsigned b=0;b<256;b++){
 dac_z80_init(&c,bus);c.cpu.bc=state;c.cpu.a=b;c.cpu.bc2=0x1234;c.cpu.de2=0x5678;c.cpu.hl2=0xabcd;c.cpu.ix=0x9000;c.cpu.iy=0x9876;c.cpu.sp=0x0201;c.cpu.i=0x42;
 c.pins=z80_prefetch(&c.cpu,entry);
 do{dac_z80_tick(&c,0,0);assert(c.cycles<200);}while(!(c.pins&Z80_HALT));
 assert(c.cpu.bc2==crc(state,b));assert(c.cpu.a==b);assert(c.cpu.bc==0x1234);assert(c.cpu.de==0x5678);assert(c.cpu.hl==0xabcd);assert(c.cpu.iy==0x9876);assert(c.cpu.sp==0x0201);assert(c.cpu.i==0x42);
 if(c.cycles>max)max=c.cycles;
}
printf("W4 CRC: all 16777216 combinations PASS; maximum %llu clocks including HALT\n",max);
}
""")
            subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-O2",
                    "-I" + str(DAC),
                    str(d / "test.c"),
                    str(DAC / "common/cpu/z80.c"),
                    "-o",
                    str(d / "test"),
                ],
                check=True,
            )
            subprocess.run(
                [str(d / "test"), str(d / "rom.bin"), str(labels["crc_byte"])],
                check=True,
            )
