#include <SPI.h>
#include "paper.cpp"

/// Debug
#define DEBUG
#ifdef DEBUG
#define Log(...) Serial.print(__VA_ARGS__)
#define Logln(...) Serial.println(__VA_ARGS__)
#else
#define Log(...)   // no-op
#define Logln(...) //
#endif

/// Pin IO
const int PIN_CS = 10;   // Clock sync - MCP 4822 12-bit DAC
const int GAIN_1 = 0x1;  // UNUSED (?) - HIGH - SPI Output GAIN channel
const int GAIN_2 = 0x0;  // LOW - SPI Output GAIN channel
const int PIN_RELAY = 9; // Relay - Controls pen up/down

// Plotter min and max dimension space. 4096 x 4096
const float PLOTTER_MIN_DIM = 0;
const float PLOTTER_MAX_DIM = 4096;

// Plotter Physical Insets, in [0, 4096] space
const float PLOTTER_X_INSET = 532;
const float PLOTTER_Y_INSET = 1048;

// Plotter Physics max dimensions in plotter space [0, 4096]
static int PLOTTER_X_MAX = PLOTTER_MAX_DIM - (2 * PLOTTER_X_INSET);
static int PLOTTER_Y_MAX = PLOTTER_MAX_DIM - (2 * PLOTTER_Y_INSET);

// Delta from ruler position to actual pen-tip drawing position.
// Ensures that drawings will sit in the correct position on the 
// paper as the axis arm has a large discrepancy between ruler and pen.
const float PLOTTER_PEN_X_OFFSET = (0.8 / 15.0) * PLOTTER_X_MAX; 
const float PLOTTER_PEN_Y_OFFSET = (-0.5 / 10.0) * PLOTTER_Y_MAX; 

// Data type to record the last input position with relative metadata preserved.
struct Position
{
  // The current pen position as {x, y};
  Point point;
  
  // Whether the point is relative to the paper's origin.
  // true indicates the point is relative to the paper's origin.
  // false indicates the point is relative to the plotter's origin.
  boolean relative;
};

class Plotter
{
public:
  // The current paper media type.
  Paper paper;

  // Current coordinates with relative metadata preserved.
  Position pos;

  Plotter()
  {
    // Setup IO
    pinMode(PIN_CS, OUTPUT);
    pinMode(PIN_RELAY, OUTPUT);

    SPI.begin();
    SPI.setClockDivider(SPI_CLOCK_DIV2);

    // Setup default paper size - Plotter max dimensions.
    paper.type = Paper::Type::maximum;

    // Set inital point
    pos.point = paper.getCenter();
    pos.relative = true;
  }


  // MARK: - Pen Controls

  // Raise Pen.
  void penUp()
  {
    digitalWrite(PIN_RELAY, HIGH);
  }

  // Lower Pen.
  void penDown()
  {
    digitalWrite(PIN_RELAY, LOW);
  }

  // Move Pen {x, y} inches relative to the current position.
  //
  // delta: Point - x, y inches to translate from current pos
  void move(Point delta)
  {
    moveTo({pos.point.x + delta.x,
          pos.point.y + delta.y},
         pos.relative);
  }

  // Set Pen to absolute {x, y} position in inches. Optionallity 
  // relative to the paper space origin.
  //
  // point: Point - x, y coordinate for pen
  // relative: boolean - whether `point` is relative to the 
  //           paper's origin (rather than plotter device origin).
  void moveTo(Point point, boolean relative)
  {
    // Update current position and relativity.
    pos.point = point;
    pos.relative = relative;

    // Add offset w/ origin if relative point
    Point originOffset = {0, 0};
    if (relative)
    {
      originOffset = paper.getOriginOffset();
    }
    Point normalizedPoint = normalizePoint({originOffset.x + point.x,
                                            originOffset.y + point.y});
    setXY(normalizedPoint);
  }


  // MARK: - Plotter Controls, Utility

  // Moves the Pen to the origin of the plotter device.
  void goToHome()
  {
    moveTo({0, 0}, false);
  }

  // Moves Pen to the origin of the current paper type.
  void goToOrigin()
  {
    moveTo({0, 0}, true);
  }

  // Moves Pen to the center of the current paper type.
  void goToCenter()
  {
    moveTo(paper.getCenter(), true);
  }

  // Moves Pen to the top-right corner of the current paper type.
  void goToMaxDimension()
  {
    Dimension dim = paper.getDimension();
    moveTo({dim.width, dim.height}, true);
  }

  // Demo sequence to track the perimeter of the current paper 
  // type. End at paper center.
  void visualizePaperDimensions()
  {
    Dimension dim = paper.getDimension();

    // Origin / Bottom Left
    goToOrigin();
    delay(500);

    // Top Left
    moveTo({0, dim.height}, true);
    delay(500);

    // Top Right
    goToMaxDimension();
    delay(500);

    // Bottom Right
    moveTo({dim.width, 0}, true);
    delay(500);

    // Origin / Bottom Left
    goToOrigin();
    delay(500);

    // Center
    goToCenter();
    delay(500);
  }


private:

  // MARK: - Paper Dimension, Utility

  Point normalizePoint(Point point)
  {
    // Plotter max paper size in inches
    Dimension maxDim = Paper::dimensionForType(Paper::Type::maximum);

    // Point normalized to plotter space 15x10 in
    Point pointNormal = {
        point.x / maxDim.width,
        point.y / maxDim.height};

    // Return in normal space [0.0, 1.0]
    return pointNormal;
  }


  // MARK: - Axis Position, Utility

  // point ({x: [0.0, 1.0], y: [0.0, 1.0]}) normalized position for the physical plotter
  // Note: You should not need to set this directly.
  void setXY(Point point)
  {
    setX(point.x);
    setY(point.y);
  }

  // pos: [0.0, 1.0] normalized position for the physical plotter
  // Note: You should not need to set this directly.
  void setX(float pos)
  {
    float outputPos = PLOTTER_X_INSET + PLOTTER_PEN_X_OFFSET + (pos * PLOTTER_X_MAX);
    if (max(PLOTTER_X_INSET, min(outputPos, PLOTTER_X_INSET + PLOTTER_X_MAX)))
    {
      setOutput(0, GAIN_2, 1, outputPos);
    }
    else
    {
      Log("\n** [SPI][Error] X pos: ");
      Logln(pos);
    }
  }

  // pos: [0.0, 1.0] normalized position for the physical plotter
  // Note: You should not need to set this directly.
  void setY(float pos)
  {
    float outputPos = PLOTTER_Y_INSET + PLOTTER_PEN_Y_OFFSET + (pos * PLOTTER_Y_MAX);
    if (max(PLOTTER_Y_INSET, min(outputPos, PLOTTER_Y_INSET + PLOTTER_Y_MAX)))
    {
      setOutput(1, GAIN_2, 1, outputPos);
    }
    else
    {
      Log("\n** [SPI][Error] Y pos: ");
      Logln(pos);
    }
  }


  // MARK: - SPI, Utility
  // Set SPI channel voltage level to control X,Y 
  // position of pen plotter through DAC;

  // Sets voltage of output pin using SPI.
  //
  // channel  - `0` (x axis) or `1` (y axis)
  // gain     - `GAIN_2` (low) or `GAIN_1` (high)
  // shutdown - `1` (?)
  // val      - value to write [0, 4096]
  void setOutput(byte channel, byte gain, byte shutdown, unsigned int val)
  {
    byte lowByte = val & 0xff;
    byte highByte = ((val >> 8) & 0xff) | channel << 7 | gain << 5 | shutdown << 4;

    PORTB &= 0xfb;
    SPI.transfer(highByte);
    SPI.transfer(lowByte);
    PORTB |= 0x4;
  }

};
