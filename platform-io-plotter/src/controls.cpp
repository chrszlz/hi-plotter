#include <SPI.h>

/// Debug
#define DEBUG
#ifdef DEBUG
  #define Log(...)    Serial.print(__VA_ARGS__)
  #define Logln(...)  Serial.println(__VA_ARGS__)
#else
  #define Log(...)    // no-op
  #define Logln(...)  //
#endif

/// Pin IO
const int PIN_CS = 10; // Clock sync - MCP 4822 12-bit DAC
const int GAIN_1 = 0x1; // UNUSED (?) - HIGH - SPI Output GAIN channel
const int GAIN_2 = 0x0; // LOW - SPI Output GAIN channel
const int PIN_RELAY = 9; // Relay - Controls pen up/down

// Plotter Physical Insets, in [0, 4096] space
// const int INSET = 128; // Inset increment
// const float X_INSET_MULT = 8.3;  // Inset coefficientsfor calibrated center (2048, 2048)
// const float Y_INSET_MULT = 12.2; //
const float X_INSET = 1062.4;
const float Y_INSET = 1561.6;

const float MIN_DIM = 0;
const float MAX_DIM = 4096;

// Represents dimension measurements in inches.
struct Dimension {
  float width, height;
};

// Represents a Point's offset in inches.
struct Offset {
  float x, y;
};

// A coordinate of arbitrary units.
struct Point {
  float x, y;
};

static void pp(Point point) {
  Log("(");
  Log(point.x);
  Log(", ");
  Log(point.y);
  Logln(")");
}

// Describes the Paper being used in terms of dimensions and origin offset;
struct Paper {
  // The type of paper being used - defines the inches dimensions.
  enum Type {
    letter,
    maximum
  };

  // Width and Height dimensions for a Paper type oriented to match Plotter plate.
  static Dimension dimensionForType(Type type) {
    switch (type) {
      case letter:
        return { 11.0, 8.5 };
      case maximum:
        return { 15.0, 10.0 };
      default:
        return { 0, 0 };
    }
  }

  // X and Y offsets to calibrate real-world Paper dimensions.
  static Offset offsetForType(Type type) {
    switch (type) {
      case letter:
        // X offset left, 0.8", Y inset up 0.5"
        return {0, 0};//{ -0.8, -0.5 };
      case maximum:
        return { 0, 0 };
      default:
        return { 0, 0 };
    }
  }

  Type type;

  // Returns the dimensions of the current Paper Type.
  Dimension getDimension() {
    return dimensionForType(type);
  }

  // Returns the origin for the current Paper Type.
  Point getOrigin() {
    Offset offset = offsetForType(type);
    Dimension dim = getDimension();
    Dimension maxDim = dimensionForType(maximum);

    Point origin;
    switch (type) {
      case letter:
        // X: center horizontally
        // Y: 0 - bottom
        origin = {
          (maxDim.width - dim.width) / 2.0,
          0
        };
        break;
      default:
        // Plotter corner origin
        origin = {0, 0};
        break;
    }

    return {
      origin.x + offset.x,
      origin.y + offset.y
    };
  }

  // Returns the center of the current Paper Type relative to the origin.
  Point getCenter() {
    Point origin = getOrigin();
    Dimension dim = getDimension();
    return {
      origin.x + (dim.width / 2.0),
      origin.y + (dim.height / 2.0)
    };
  }

};


class Plotter {
private:
  // Current coordinates in Paper dimension space.
  Point pos;


  // MARK: - Paper dimension handling

  // Converts a point in Paper dimension space [w_inches, h_inches] to
  // Plotter SPI output space [0, 4096].
  Point outputPointForPoint(Point point) {
    Serial.print("oP4P: ");
    pp(point);

    Point origin = paper.getOrigin();
    Serial.print("origin: ");
    pp(origin);
    Dimension maxDim = Paper::dimensionForType(Paper::Type::maximum);
    // Normalize and scale to output space.
    Point normalizedPoint = {
      (origin.x + point.x) / maxDim.width,
      (origin.y + point.y) / maxDim.height
    };
    Serial.print("Normalized: ");
    pp(normalizedPoint);

    Point newPoint = {
      normalizedPoint.x * MAX_DIM,
      normalizedPoint.y * MAX_DIM
    };
    Serial.print("returned: ");
    pp(newPoint);
    return newPoint;
  }

public:
  // The current paper media type.
  Paper paper;

  Plotter() {
      // Setup IO
      pinMode(PIN_CS, OUTPUT);
      pinMode(PIN_RELAY, OUTPUT);

      SPI.begin();
      SPI.setClockDivider(SPI_CLOCK_DIV2);

      // Initialize coords to origin.
      pos = {0, 0};

      // Setup default paper size - Plotter max dimensions.
      paper.type = Paper::Type::maximum;
  }


  // MARK: - Plotter Controls

  // Moves the Pen to the origin of the current paper type.
  void goToOrigin() {
    Logln("\n[Origin]");
    goTo({0, 0});
  }

  // Centers the Pen within the current paper type.
  void goToCenter() {
    Logln("\n[Center]");
    Point center = paper.getCenter();
    goTo(center);
  }

  void goToMaxDimension() {
    Logln("\n[Max]");
    Dimension dim = paper.getDimension();
    goTo({ dim.width, dim.height });
  }

  void visualizePaperDimensions() {
    Dimension dim = paper.getDimension();

    delay(300);

    goToOrigin();
    delay(500);

    goTo({ 0, dim.height });
    delay(500);

    goToMaxDimension();
    delay(500);

    goTo({ dim.width, 0 });
    delay(500);

    goToOrigin();
    delay(500);

    goToCenter();
    delay(500);
  }


  // MARK: - Pen Controls

  // Set Pen position within the Paper type's dimension space.
  //
  // Ex. Paper.type = letter (width 8.5, height 11.0)
  //     valid point: ([0, 8,5], [0, 11.0])
  void goTo(Point point) {
    Log("\n");
    pp(point);

    Point scaledPoint = outputPointForPoint(point);
    pp(scaledPoint);
    setOutputXPos(scaledPoint.x);
    setOutputYPos(scaledPoint.y);
  }
  //
  // // Set plotter X-axis position within Paper type dimension.
  // //
  // // Ex. Paper.type = letter (width 8.5)
  // //     valid x-coordinate: [0, 8.5]
  // void setXPos(float xPos) {
  //   Dimension dim = paper.getDimension();
  //   if (0 <= xPos && xPos <= dim.width) {
  //     pos.x = xPos;
  //     setOutputXPos((xPos / dim.width) * 4096);
  //   }
  // }
  //
  // // Set plotter Y-axis position within Paper type dimension.
  // //
  // // Ex. Paper.type = letter (height 11.0)
  // //     valid y-coordinate: [0, 11.0]
  // void setYPos(float yPos) {
  //   Dimension dim = paper.getDimension();
  //   if (0 <= yPos && yPos <= dim.height) {
  //     pos.y = yPos;
  //     setOutputYPos((yPos / dim.height) * 4096);
  //   }
  // }

  // Set plotter X-axis position - [0, 4096]
  void setOutputXPos(float pos) {
    float insetDim = MAX_DIM - X_INSET;
    float scaledPos = (pos / MAX_DIM) * insetDim;
    if (MIN_DIM <= scaledPos && scaledPos <= MAX_DIM) {
      setOutput(0, GAIN_2, 1, (X_INSET / 2.0) + scaledPos);
    } else {
      Serial.print("\n** [SPI][Error] X pos: ");
      Serial.print(pos);
      Serial.println();
    }
  }

  // Set plotter Y-axis position - [0, 4096]
  void setOutputYPos(float pos) {
    float insetDim = MAX_DIM - Y_INSET;
    float scaledPos = (pos / MAX_DIM) * insetDim;
    if (MIN_DIM <= pos && pos <= MAX_DIM) {
      setOutput(1, GAIN_2, 1, (Y_INSET / 2.0) + scaledPos);
    } else {
      Serial.print("\n** [SPI][Error] Y pos: ");
      Serial.print(pos);
      Serial.println();
    }
  }

  // Raise pen.
  void penUp() {
    digitalWrite(PIN_RELAY, HIGH);
  }

  // Lower pen.
  void penDown() {
    digitalWrite(PIN_RELAY, LOW);
  }


  // MARK: - SPI, Utility

  // Sets voltage of output pin using SPI.
  //
  // channel  - `0` (x axis) or `1` (y axis)
  // gain     - `GAIN_2` (low) or `GAIN_1` (high)
  // shutdown - `1` (?)
  // val      - value to write [0, 4096]
  void setOutput(byte channel, byte gain, byte shutdown, unsigned int val) {
    byte lowByte = val & 0xff;
    byte highByte = ((val >> 8) & 0xff) | channel << 7 | gain << 5 | shutdown << 4;

    PORTB &= 0xfb;
    SPI.transfer(highByte);
    SPI.transfer(lowByte);
    PORTB |= 0x4;
  }

};
