#pragma once

#include <Arduino.h>

// Command queue and executor. Moves are straight lines in DAC counts with a
// duration; the host plans speeds and acceleration and sends short timed segments.
namespace Motion
{
  enum class Type : uint8_t
  {
    move,
    penUp,
    penDown,
    wait
  };

  struct Command
  {
    Type type;
    uint16_t x, y; // move target, counts
    uint16_t ms;   // move or wait duration; a 0 ms move jumps
  };

  // Writes the starting position to the DAC: where the pen was before a reset, or the
  // park position after power-up. Returns whether it resumed.
  bool begin(uint16_t parkX, uint16_t parkY);

  bool hasRoom();
  void push(const Command &command);

  // Advances the current command. Call every loop.
  void update();

  // Drops everything queued, stops where the pen is and lifts it.
  void stop();

  bool isIdle();
  uint8_t queued();
  uint16_t x();
  uint16_t y();

  // How many timed commands found the queue had run dry (see Motion.cpp).
  uint16_t lateStarts();
}
