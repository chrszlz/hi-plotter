// hi-plotter firmware: drives a Houston Instrument Omnigraphic 2000 X-Y recorder
// through an MCP4822 DAC (X and Y inputs) and a relay (pen lift).
//
// Line protocol, 115200 baud. Every line is answered with "ok" or "error: ...".
// Lines starting with "#" are info, "<" is a status report.
//
//   M x y [ms]   move in a straight line to (x, y) DAC counts over ms (0 = jump)
//   U / D        pen up / down
//   W ms         wait
//   P [0|1]      show or set the relay level that lifts the pen (saved)
//   V            version
//   H            help
//
// Two single characters act immediately, even mid-line or with the queue full:
//   ?            status: <idle|run x=.. y=.. pen=up|down q=.. late=..>
//   !            stop: clear the queue and lift the pen
//
// M, U, D and W are queued and run in order. Words work too ("up", "move 10 20").

#include <Arduino.h>
#include <stdlib.h>

#include "Dac.h"
#include "Motion.h"
#include "Pen.h"
#include "config.h"

namespace
{
  const char VERSION[] = "hi-plotter 1.0";

  const uint8_t LINE_MAX = 48;
  char line[LINE_MAX];
  uint8_t lineLength = 0;
  bool lineOverflow = false;

  // A complete line waiting for room in the queue.
  bool lineReady = false;

  // Last time a line arrived or a command ran, for the idle pen lift.
  unsigned long lastActivityMs = 0;

  // MARK: - Replies

  void reply(const __FlashStringHelper *text)
  {
    Serial.println(text);
  }

  void replyError(const __FlashStringHelper *reason)
  {
    Serial.print(F("error: "));
    Serial.println(reason);
  }

  void printStatus()
  {
    Serial.print(Motion::isIdle() ? F("<idle x=") : F("<run x="));
    Serial.print(Motion::x());
    Serial.print(F(" y="));
    Serial.print(Motion::y());
    Serial.print(Pen::isDown() ? F(" pen=down q=") : F(" pen=up q="));
    Serial.print(Motion::queued());
    Serial.print(F(" late="));
    Serial.print(Motion::lateStarts());
    Serial.println('>');
  }

  void printHelp()
  {
    reply(F("# M x y [ms]  straight line to (x, y) DAC counts 0-4095 over ms (0 = jump)"));
    reply(F("# U / D       pen up / down"));
    reply(F("# W ms        wait"));
    reply(F("# P [0|1]     show or set the relay level that lifts the pen (saved)"));
    reply(F("# V           version"));
    reply(F("# ?           status (immediate)"));
    reply(F("# !           stop: clear queue, lift pen (immediate)"));
  }

  void printPenLevel()
  {
    Serial.print(F("# pen up level: "));
    Serial.println(Pen::upLevel() == HIGH ? F("1 (relay pin HIGH lifts the pen)") : F("0 (relay pin LOW lifts the pen)"));
  }

  void clearLine()
  {
    lineLength = 0;
    lineOverflow = false;
    lineReady = false;
  }

  void stop()
  {
    Motion::stop();
    clearLine();
    reply(F("# stopped"));
  }

  // MARK: - Parsing

  // Parses up to `max` integers separated by spaces or commas, after skipping the
  // rest of the command word. Returns the count, or -1 if something isn't a number.
  int parseArgs(const char *text, long *args, int max)
  {
    while (isalpha(*text))
    {
      text++;
    }

    int found = 0;
    while (true)
    {
      while (*text == ' ' || *text == ',' || *text == '\t')
      {
        text++;
      }
      if (*text == '\0')
      {
        return found;
      }
      if (found == max)
      {
        return -1;
      }

      char *end;
      args[found] = strtol(text, &end, 10);
      if (end == text)
      {
        return -1;
      }
      found++;
      text = end;
    }
  }

  uint16_t clampCounts(long value)
  {
    return (uint16_t)constrain(value, 0L, (long)DAC_MAX);
  }

  void handleLine()
  {
    lastActivityMs = millis();

    if (lineOverflow)
    {
      replyError(F("line too long"));
      return;
    }

    const char *text = line;
    while (*text == ' ' || *text == '\t')
    {
      text++;
    }

    long args[3];
    int argc = parseArgs(text, args, 3);
    if (argc < 0)
    {
      replyError(F("bad number"));
      return;
    }

    switch (toupper(*text))
    {
    case 'M':
      if (argc < 2)
      {
        replyError(F("usage: M x y [ms]"));
        return;
      }
      Motion::push({Motion::Type::move,
                    clampCounts(args[0]),
                    clampCounts(args[1]),
                    (uint16_t)constrain(argc == 3 ? args[2] : 0L, 0L, 65535L)});
      break;
    case 'U':
      Motion::push({Motion::Type::penUp, 0, 0, 0});
      break;
    case 'D':
      Motion::push({Motion::Type::penDown, 0, 0, 0});
      break;
    case 'W':
      if (argc != 1)
      {
        replyError(F("usage: W ms"));
        return;
      }
      Motion::push({Motion::Type::wait, 0, 0, (uint16_t)constrain(args[0], 0L, 65535L)});
      break;
    case 'P':
      if (argc == 1)
      {
        Pen::setUpLevel(args[0] ? HIGH : LOW);
      }
      printPenLevel();
      break;
    case 'V':
      Serial.print(F("# "));
      Serial.println(VERSION);
      break;
    case 'H':
      printHelp();
      break;
    default:
      replyError(F("unknown command, send H for help"));
      return;
    }

    reply(F("ok"));
  }

  // MARK: - Serial input

  void readSerial()
  {
    while (Serial.available())
    {
      int c = Serial.peek();

      if (c == '!')
      {
        Serial.read();
        stop();
        continue;
      }
      if (c == '?')
      {
        Serial.read();
        printStatus();
        continue;
      }

      // Leave the next line in the buffer until this one is handled.
      if (lineReady)
      {
        return;
      }

      Serial.read();
      if (c == '\n' || c == '\r')
      {
        if (lineLength > 0 || lineOverflow)
        {
          line[lineLength] = '\0';
          lineReady = true;
        }
      }
      else if (c == '\b' || c == 0x7F)
      {
        if (lineLength > 0)
        {
          lineLength--;
        }
      }
      else if (lineLength < LINE_MAX - 1)
      {
        line[lineLength++] = (char)c;
      }
      else
      {
        lineOverflow = true;
      }
    }
  }

  void liftIdlePen()
  {
    if (!Motion::isIdle())
    {
      lastActivityMs = millis();
      return;
    }

    if (Pen::isDown() && millis() - lastActivityMs > IDLE_PEN_LIFT_MS)
    {
      Pen::up();
      reply(F("# pen lifted: down with nothing to do for 10 s"));
    }
  }
}

void setup()
{
  // Pen first: the relay pin floats during reset, so get it to pen-up right away.
  Pen::begin();
  Dac::begin();
  Motion::begin(PARK_X, PARK_Y);

  Serial.begin(SERIAL_BAUD);
  Serial.print(F("# "));
  Serial.print(VERSION);
  Serial.println(F(" ready, pen up. Send H for help."));
  lastActivityMs = millis();
}

void loop()
{
  readSerial();

  if (lineReady && Motion::hasRoom())
  {
    handleLine();
    clearLine();
  }

  Motion::update();
  liftIdlePen();
}
