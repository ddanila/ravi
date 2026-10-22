// ATmega328P Uno: passive rising-edge counter on D5 (T1).
// No pull-up and no signal output. Timer0 remains available for micros().
#include <Arduino.h>
#include <avr/interrupt.h>
#if !defined(__AVR_ATmega328P__) || F_CPU != 16000000UL
#error "Requires a 16 MHz ATmega328P Uno"
#endif
volatile uint16_t wraps = 0;
ISR(TIMER1_OVF_vect) { ++wraps; }
void setup() {
  pinMode(5, INPUT);
  digitalWrite(5, LOW); // Explicitly disable pull-up.
  TCCR1A = 0;
  TCCR1B = 0;
  TIMSK1 = 0;
  Serial.begin(115200);
  Serial.println(F("D5/T1 passive counter; floating input readings are meaningless"));
  Serial.println(F("gate_us,edges,approx_hz,end_level"));
}
void loop() {
  noInterrupts();
  TCCR1B = 0;
  TCNT1 = 0;
  wraps = 0;
  TIFR1 = _BV(TOV1);
  TIMSK1 = _BV(TOIE1);
  uint32_t start = micros();
  TCCR1B = _BV(CS12) | _BV(CS11) | _BV(CS10); // External T1 rising edge.
  interrupts();
  while ((uint32_t)(micros() - start) < 100000UL) {}
  noInterrupts();
  TCCR1B = 0;
  uint32_t end = micros();
  uint16_t low = TCNT1;
  uint16_t high = wraps;
  if (TIFR1 & _BV(TOV1)) { ++high; TIFR1 = _BV(TOV1); }
  TIMSK1 = 0;
  interrupts();
  uint32_t count = ((uint32_t)high << 16) | low;
  uint32_t elapsed = end - start;
  Serial.print(elapsed); Serial.print(',');
  Serial.print(count); Serial.print(',');
  Serial.print((double)count * 1000000.0 / elapsed, 0); Serial.print(',');
  Serial.println(digitalRead(5));
  delay(400);
}
