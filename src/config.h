#pragma once

#include <Arduino.h>

// MARK: - Pins

// MCP4822 chip select. SCK (D13) and MOSI (D11) are fixed by the Uno's SPI hardware.
const uint8_t PIN_DAC_CS = 10;

// Relay that switches the recorder's pen lift.
const uint8_t PIN_PEN_RELAY = 9;

// MARK: - Serial

const unsigned long SERIAL_BAUD = 115200;

// MARK: - Motion

// Largest DAC value. At 2x gain the MCP4822 outputs 0-4.095 V, so 1 count = 1 mV.
const uint16_t DAC_MAX = 4095;

// Where the pen goes at boot, in DAC counts. Mid-scale is roughly the middle of the bed.
const uint16_t PARK_X = 2048;
const uint16_t PARK_Y = 2048;

// Queued commands. Each takes 7 bytes of the Uno's 2 KB of RAM.
const uint8_t QUEUE_SIZE = 32;

// A timed command that starts more than this late restarts the clock instead of
// rushing to catch up (the queue ran dry).
const unsigned long LATE_START_US = 5000;

// Lift the pen if it has been left down with nothing to do for this long, so a
// crashed or unplugged host can't leave the pen bleeding into the paper.
const unsigned long IDLE_PEN_LIFT_MS = 10000;
