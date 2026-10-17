#pragma once

#include <Arduino.h>

#define MSBFIRST 1
#define SPI_MODE0 0

class SPISettings
{
public:
  SPISettings(uint32_t, uint8_t, uint8_t) {}
};

class SPIClass
{
public:
  void begin() {}
  void beginTransaction(SPISettings) {}
  void endTransaction() {}
  uint16_t transfer16(uint16_t word);
};

extern SPIClass SPI;
