#include "Motion.h"

#include "Dac.h"
#include "Pen.h"
#include "config.h"

namespace
{
  Motion::Command queue[QUEUE_SIZE];
  uint8_t head = 0;
  uint8_t count = 0;

  // Last position written to the DAC.
  uint16_t posX = 0;
  uint16_t posY = 0;

  // The timed command in progress (a move or a wait).
  bool active = false;
  uint16_t fromX, fromY, toX, toY;
  unsigned long startUs = 0;
  unsigned long durationUs = 0;

  // Planned end of the last timed command. Back-to-back segments start from it rather
  // than from "now", so loop jitter never adds up into a slower plot.
  unsigned long clockUs = 0;

  // Timed commands that started late because the queue had run dry. Once at the start
  // of every job is expected; more means the host fell behind mid-plot.
  uint16_t lateStartCount = 0;

  void output(uint16_t x, uint16_t y)
  {
    if (x != posX || y != posY)
    {
      Dac::write(x, y);
      posX = x;
      posY = y;
    }
  }

  uint16_t lerp(uint16_t from, uint16_t to, float t)
  {
    float value = from + ((float)to - (float)from) * t;
    return (uint16_t)(value + 0.5f);
  }

  void startTimed(const Motion::Command &command, unsigned long now)
  {
    if ((long)(now - clockUs) > (long)LATE_START_US)
    {
      clockUs = now;
      lateStartCount++;
    }

    fromX = posX;
    fromY = posY;
    toX = command.type == Motion::Type::move ? command.x : posX;
    toY = command.type == Motion::Type::move ? command.y : posY;
    startUs = clockUs;
    durationUs = command.ms * 1000UL;
    clockUs += durationUs;
    active = true;
  }

  void execute(const Motion::Command &command, unsigned long now)
  {
    switch (command.type)
    {
    case Motion::Type::penUp:
      Pen::up();
      break;
    case Motion::Type::penDown:
      Pen::down();
      break;
    case Motion::Type::move:
      if (command.ms == 0)
      {
        output(command.x, command.y);
        break;
      }
      startTimed(command, now);
      break;
    case Motion::Type::wait:
      startTimed(command, now);
      break;
    }
  }
}

void Motion::begin(uint16_t x, uint16_t y)
{
  posX = x;
  posY = y;
  Dac::write(x, y);
  clockUs = micros();
}

bool Motion::hasRoom()
{
  return count < QUEUE_SIZE;
}

void Motion::push(const Command &command)
{
  queue[(head + count) % QUEUE_SIZE] = command;
  count++;
}

void Motion::update()
{
  unsigned long now = micros();

  if (active)
  {
    unsigned long elapsed = now - startUs;
    if (elapsed < durationUs)
    {
      float t = (float)elapsed / (float)durationUs;
      output(lerp(fromX, toX, t), lerp(fromY, toY, t));
      return;
    }
    output(toX, toY);
    active = false;
  }

  // Run instant commands (pen, jumps) back to back until a timed one starts.
  while (!active && count > 0)
  {
    Command command = queue[head];
    head = (head + 1) % QUEUE_SIZE;
    count--;
    execute(command, now);
  }
}

void Motion::stop()
{
  count = 0;
  active = false;
  Pen::up();
}

bool Motion::isIdle()
{
  return !active && count == 0;
}

uint8_t Motion::queued()
{
  return count + (active ? 1 : 0);
}

uint16_t Motion::x()
{
  return posX;
}

uint16_t Motion::y()
{
  return posY;
}

uint16_t Motion::lateStarts()
{
  return lateStartCount;
}
