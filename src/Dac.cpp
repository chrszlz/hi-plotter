#include "Dac.h"

#include <SPI.h>

#include "config.h"

namespace
{
  // Write command bits, MCP4822 datasheet register 5-1. The gain bit (13) is left
  // clear, which selects 2x gain: 0-4.096 V from the internal 2.048 V reference.
  const uint16_t CHANNEL_B = 0x8000; // bit 15: 0 = DAC A, 1 = DAC B
  const uint16_t ACTIVE = 0x1000;    // bit 12: 1 = output on, 0 = shut down

  const SPISettings DAC_SPI(8000000, MSBFIRST, SPI_MODE0);

  void writeChannel(uint16_t channel, uint16_t value)
  {
    if (value > DAC_MAX)
    {
      value = DAC_MAX;
    }

    SPI.beginTransaction(DAC_SPI);
    digitalWrite(PIN_DAC_CS, LOW);
    SPI.transfer16(channel | ACTIVE | value);
    digitalWrite(PIN_DAC_CS, HIGH);
    SPI.endTransaction();
  }
}

void Dac::begin()
{
  digitalWrite(PIN_DAC_CS, HIGH);
  pinMode(PIN_DAC_CS, OUTPUT);
  SPI.begin();
}

void Dac::write(uint16_t x, uint16_t y)
{
  writeChannel(0, x);
  writeChannel(CHANNEL_B, y);
}
