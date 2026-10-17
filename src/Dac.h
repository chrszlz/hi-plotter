#pragma once

#include <Arduino.h>

// MCP4822 dual 12-bit DAC. Channel A drives the recorder's X input, channel B drives Y.
namespace Dac
{
  void begin();

  // Sets both outputs, in counts. Values above DAC_MAX are clamped.
  void write(uint16_t x, uint16_t y);
}
