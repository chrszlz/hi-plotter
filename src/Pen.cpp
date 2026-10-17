#include "Pen.h"

#include <EEPROM.h>

#include "config.h"

namespace
{
  // EEPROM layout: a marker byte, then the up level.
  const int EEPROM_MARKER_ADDRESS = 0;
  const int EEPROM_UP_LEVEL_ADDRESS = 1;
  const uint8_t EEPROM_MARKER = 0xA7;

  // The 2020 sketch lifted the pen with HIGH.
  uint8_t penUpLevel = HIGH;
  bool penIsDown = false;

  void apply()
  {
    uint8_t downLevel = penUpLevel == HIGH ? LOW : HIGH;
    digitalWrite(PIN_PEN_RELAY, penIsDown ? downLevel : penUpLevel);
  }
}

void Pen::begin()
{
  if (EEPROM.read(EEPROM_MARKER_ADDRESS) == EEPROM_MARKER)
  {
    penUpLevel = EEPROM.read(EEPROM_UP_LEVEL_ADDRESS) ? HIGH : LOW;
  }

  // Set the output latch first so the pin comes up at the pen-up level.
  penIsDown = false;
  apply();
  pinMode(PIN_PEN_RELAY, OUTPUT);
}

void Pen::up()
{
  penIsDown = false;
  apply();
}

void Pen::down()
{
  penIsDown = true;
  apply();
}

bool Pen::isDown()
{
  return penIsDown;
}

uint8_t Pen::upLevel()
{
  return penUpLevel;
}

void Pen::setUpLevel(uint8_t level)
{
  penUpLevel = level ? HIGH : LOW;
  EEPROM.update(EEPROM_MARKER_ADDRESS, EEPROM_MARKER);
  EEPROM.update(EEPROM_UP_LEVEL_ADDRESS, penUpLevel == HIGH ? 1 : 0);
  apply();
}
