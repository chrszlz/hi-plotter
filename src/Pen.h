#pragma once

#include <Arduino.h>

// Pen lift relay. Which relay level lifts the pen depends on how the relay is wired,
// so it's a setting saved in EEPROM rather than a constant.
namespace Pen
{
  // Lifts the pen before the relay pin starts driving, so boot never drops it.
  void begin();

  void up();
  void down();
  bool isDown();

  // The relay pin level (HIGH or LOW) that lifts the pen.
  uint8_t upLevel();

  // Saves a new up level and re-applies the current pen state with it.
  void setUpLevel(uint8_t level);
}
