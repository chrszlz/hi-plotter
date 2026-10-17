// Runs the plotter firmware on a Mac, for testing without the hardware.
//
// Serial is stdin/stdout. Every DAC or pen change is appended to $SIM_LOG as
// "t_us x y pen" (pen 1 = down). The sim exits once stdin closes and the queue
// has drained. Built and driven by host/hiplot/sim.py.

#include <Arduino.h>
#include <EEPROM.h>
#include <SPI.h>

#include <chrono>
#include <deque>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>

#include "Motion.h"
#include "Pen.h"
#include "config.h"

void setup();
void loop();

SimSerial Serial;
SPIClass SPI;
EEPROMClass EEPROM;

namespace
{
  const auto start = std::chrono::steady_clock::now();

  std::deque<uint8_t> input;
  bool inputClosed = false;

  FILE *logFile = nullptr;
  bool dacWritten = false;
  uint16_t dacX = 0;
  uint16_t dacY = 0;

  uint8_t eeprom[1024];

  void pollInput()
  {
    uint8_t buffer[256];
    ssize_t count;
    while ((count = ::read(STDIN_FILENO, buffer, sizeof buffer)) > 0)
    {
      input.insert(input.end(), buffer, buffer + count);
    }
    if (count == 0)
    {
      inputClosed = true;
    }
  }

  void logState()
  {
    // Before the first DAC write the outputs are off, so there's no position to log.
    if (logFile && dacWritten)
    {
      fprintf(logFile, "%lu %u %u %d\n", micros(), dacX, dacY, Pen::isDown() ? 1 : 0);
    }
  }
}

// MARK: - Arduino API

unsigned long micros()
{
  auto elapsed = std::chrono::steady_clock::now() - start;
  return (unsigned long)std::chrono::duration_cast<std::chrono::microseconds>(elapsed).count();
}

unsigned long millis()
{
  return micros() / 1000;
}

void pinMode(uint8_t, uint8_t) {}

void digitalWrite(uint8_t pin, uint8_t)
{
  if (pin == PIN_PEN_RELAY)
  {
    logState();
  }
}

uint16_t SPIClass::transfer16(uint16_t word)
{
  if (!(word & 0x1000) || (word & 0x2000))
  {
    fprintf(stderr, "sim: DAC word %04x has the output off or 1x gain\n", word);
  }

  // Dac::write sends X then Y, so log once both have landed.
  if (word & 0x8000)
  {
    dacY = word & 0x0FFF;
    dacWritten = true;
    logState();
  }
  else
  {
    dacX = word & 0x0FFF;
  }
  return 0;
}

uint8_t EEPROMClass::read(int address)
{
  return eeprom[address];
}

void EEPROMClass::update(int address, uint8_t value)
{
  eeprom[address] = value;
}

void SimSerial::begin(unsigned long) {}

int SimSerial::available()
{
  pollInput();
  return (int)input.size();
}

int SimSerial::peek()
{
  pollInput();
  return input.empty() ? -1 : input.front();
}

int SimSerial::read()
{
  pollInput();
  if (input.empty())
  {
    return -1;
  }
  int c = input.front();
  input.pop_front();
  return c;
}

void SimSerial::print(const char *text) { fputs(text, stdout); }
void SimSerial::print(const __FlashStringHelper *text) { fputs(reinterpret_cast<const char *>(text), stdout); }
void SimSerial::print(char c) { fputc(c, stdout); }
void SimSerial::print(unsigned char number) { printf("%u", number); }
void SimSerial::print(int number) { printf("%d", number); }
void SimSerial::print(unsigned int number) { printf("%u", number); }
void SimSerial::print(long number) { printf("%ld", number); }
void SimSerial::print(unsigned long number) { printf("%lu", number); }

void SimSerial::println()
{
  fputc('\n', stdout);
  fflush(stdout);
}

// MARK: - Main

int main()
{
  memset(eeprom, 0xFF, sizeof eeprom);

  const char *logPath = getenv("SIM_LOG");
  if (logPath)
  {
    // Line buffered, so the log can be read while the sim runs.
    logFile = fopen(logPath, "w");
    setvbuf(logFile, nullptr, _IOLBF, 0);
  }

  fcntl(STDIN_FILENO, F_SETFL, fcntl(STDIN_FILENO, F_GETFL) | O_NONBLOCK);

  setup();
  while (!(inputClosed && input.empty() && Motion::isIdle()))
  {
    loop();
    usleep(20);
  }

  if (logFile)
  {
    fclose(logFile);
  }
  return 0;
}
