#pragma once

// Just enough of the Arduino API to run the firmware on a Mac. See sim_main.cpp.

#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1

#define constrain(x, low, high) ((x) < (low) ? (low) : ((x) > (high) ? (high) : (x)))

class __FlashStringHelper;
#define F(text) (reinterpret_cast<const __FlashStringHelper *>(text))

unsigned long millis();
unsigned long micros();
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t value);

class SimSerial
{
public:
  void begin(unsigned long baud);
  int available();
  int peek();
  int read();

  void print(const char *text);
  void print(const __FlashStringHelper *text);
  void print(char c);
  void print(unsigned char number);
  void print(int number);
  void print(unsigned int number);
  void print(long number);
  void print(unsigned long number);
  void println();

  template <typename T>
  void println(T value)
  {
    print(value);
    println();
  }
};

extern SimSerial Serial;
