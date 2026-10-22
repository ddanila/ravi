# Uno clock counter

Bench aid for checking clock activity on a plain Robotron PC 1715. Requires a
16 MHz ATmega328P Uno. Timer1 counts rising edges on D5/T1 during approximately
100 ms windows, including overflow handling; serial output at 115200 baud reports
window duration, edge count, approximate frequency and final digital level.
D5 remains an input without a pull-up. No test waveform is generated.

## Build and upload

With only USB attached (upload replaces the existing sketch):

```sh
arduino-cli compile --fqbn arduino:avr:uno tools/uno_clock_counter
arduino-cli upload --fqbn arduino:avr:uno --port /dev/ttyUSB0 tools/uno_clock_counter
```

Verify the port belongs to the Uno; other USB serial adapters can use this name.

## Wiring

Make connections with the motherboard off, using secure insulated leads:

- Motherboard internal X1/X2 A1 (verified ground) to Uno GND.
- Motherboard A21 (TAKT-X1/TAKT-X2) to Uno D5, preferably through a 1 kohm
  series resistor near the Uno as limited accidental-contention protection.
- Keep Uno powered by USB during measurement. Do not connect motherboard power
  rails to Uno 5V, 3.3V or VIN. Do not use RS-232 signals or negative/12V rails.
- Verify connector numbering before powering the motherboard. Disconnect the
  logic analyzer signal lead during this independent check.

This measures edges, not waveform quality or analogue voltage. A floating input
has no useful meaning. A zero count can also indicate a wrong pin, poor contact,
insufficient logic level or an unsuitable pulse width/frequency.

The Microchip datasheet recommends external timer clocks below CPU clock / 2.5
(6.4 MHz for a 16 MHz Uno), with high and low durations each exceeding one CPU
cycle. Input logic thresholds also apply; this is not a substitute for a scope.
Frequency accuracy depends on the Uno oscillator and software gate timing.

Source: [ATmega328P datasheet, external timer clock source](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf).

## Verification

2026-10-22: Compiled with Arduino AVR core 1.8.8 for `arduino:avr:uno`, uploaded
to the owner's CH340-equipped ATmega328P board, and verified serial reporting.
With only USB connected, reported zero edges. No known-frequency input validation
or motherboard measurement has yet been performed.
