#pragma once

#include <Arduino.h>

class EEPROMClass
{
public:
  uint8_t read(int address);
  void update(int address, uint8_t value);
};

extern EEPROMClass EEPROM;
