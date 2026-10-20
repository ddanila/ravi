/* RAVI test harness, MIT. External chips/z80.h and historical ROM required.
 * Executes the actual V.24 routine after the ROM->RAM copy, not a cold board.
 * Ideal byte-level SIO: no line timing, CTC or floppy-controller emulation.
 */
#define _POSIX_C_SOURCE 200809L
#define CHIPS_IMPL
#include "z80.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static unsigned char mem[65536];
int main(int argc, char **argv) {
    if (argc != 2 && argc != 3) return 2;
    FILE *rom = fopen(argv[1], "rb");
    if (!rom || fread(mem, 1, 2048, rom) != 2048 || fgetc(rom) != EOF) return 2;
    fclose(rom);
    int fault = argc == 3;
    fcntl(0, F_SETFL, O_NONBLOCK);
    z80_t cpu;
    z80_init(&cpu);
    cpu.sp = 0x993;
    mem[0x993] = 0x00; mem[0x994] = 0x07; mem[0x700] = 0x76;
    uint64_t pins = z80_prefetch(&cpu, 0x5d7);
    int pending = -1;
    struct timespec pause = {0, 100000};
    for (unsigned long ticks = 0; ticks < 500000000; ticks++) {
        pins = z80_tick(&cpu, pins);
        unsigned addr = Z80_GET_ADDR(pins);
        if (pins & Z80_MREQ) {
            if (pins & Z80_RD) {
                unsigned char value = mem[addr];
                if (fault && addr == 0x8055) value ^= 1;
                Z80_SET_DATA(pins, value);
            } else if (pins & Z80_WR) mem[addr] = Z80_GET_DATA(pins);
        } else if (pins & Z80_IORQ) {
            unsigned port = addr & 255;
            if (pins & Z80_RD) {
                if (port == 0x0f) {
                    if (pending < 0) {
                        unsigned char byte;
                        ssize_t n = read(0, &byte, 1);
                        if (n == 0) return 0;
                        if (n == 1) pending = byte;
                        else if (errno != EAGAIN && errno != EINTR) return 3;
                        else nanosleep(&pause, NULL);
                    }
                    Z80_SET_DATA(pins, 4 | (pending >= 0));
                } else if (port == 0x0d) {
                    if (pending < 0) return 4;
                    Z80_SET_DATA(pins, pending);
                    pending = -1;
                } else { Z80_SET_DATA(pins, 0xff); }
            } else if ((pins & Z80_WR) && port == 0x0d) {
                unsigned char byte = Z80_GET_DATA(pins);
                if (write(1, &byte, 1) != 1) return 5;
            }
        }
        if (pins & Z80_HALT) return fault ? 0 : 6;
    }
    return 7;
}
