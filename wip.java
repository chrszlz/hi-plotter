#include <SPI.h>
//#include <TM1637Display.h>

// Module connection pins (Digital Pins)
//#define CLK 2
//#define DIO 3

//TM1637Display display(CLK, DIO);

const int PIN_POT = 2;
const int PIN_CS = 10;
const int GAIN_1 = 0x1;
const int GAIN_2 = 0x0;
const int PIN_STICK_X = 0;
const int PIN_STICK_Y = 1;
const int PIN_RELAY = 9;

const int W_INSET_LETTER = 128 * 4;
const int H_INSET_LETTER = 128 * 7;

const bool LOOP_ENABLED = true;
const bool DEBUG = true;

// Joystick values
int stickX = 0;
int stickY = 0;

// Current position
int x = 2048;
int y = 2048;

// Dimensions
const int MIN_DIM = 0;
const int MAX_DIM= 4096;

const int INSET = 128;
const float X_INSET_MULT = 8.3;
const float Y_INSET_MULT = 12.2;

void setup()
{
  Serial.begin(9600);
  pinMode(PIN_CS, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  SPI.begin();
  SPI.setClockDivider(SPI_CLOCK_DIV2);

//  int pos = 128 * 32;
//  setPos(pos, pos);

//  display.setBrightness(0x0f);
}

// MARK: - Loop

void loop()
{



//  Serial.println(delaySpeed());
//  int delayInterval = delaySpeed();
//  Serial.println(analogRead(PIN_POT));
//  if (LOOP_ENABLED) {
    diagonalLoop();
//  } else {
//    readValues();
//    setPosFromJoystick(stickX, stickY);
//  }
}

void diagonalLoop() {
  int delayInterval = delaySpeed();
//  Serial.println(delayInterval);
  if (delayInterval == -1) {
    return;
  }

//  diagonal(1, delayInterval);
//  diagonal(-1, delayInterval);
  penDown();
  for (int i = 0; i < 4096; i += (4096 / 256)) {
    Serial.println(i);
    setPos(i, i);

//    if (i % 2 == 0) {
//      delayInterval = delaySpeed();
//    }

//    if (i > 1000 && i < 3000) {
//      penDown();
//    } else {
//      penUp();
//    }

    delay(delayInterval);
  }

  penUp();
  for (int i = 4096; i > 0; i -= (4096 / 256)) {
    Serial.println(i);
    setPos(i, i);

//    if (i % 2 == 0) {
//      delayInterval = delaySpeed();
//    }

//    if (i > 1000 && i < 3000) {
//      penDown();
//    } else {
//      penUp();
//    }

    delay(delayInterval);
  }
}

//// dir:  1 = forward   [0, 4096]
//// dir: -1 = backwards [4096, 0]
//void diagonal(int dir, int delayInterval) {
//  int startDim;
//  int endDim;
//  switch (dir) {
//    case 1:
//      startDim = MIN_DIM;
//      endDim = MAX_DIM;
//      break;
//    case -1:
//      startDim = MIN_DIM;
//      endDim = MAX_DIM;
//      break;
//    default:
//      Serial.println("*** Invalid Diagonal Dimension ***");
//      return;
//  }
//
//  /// Directional step size. (+, -)
//  int stepSize = (MAX_DIM / 256) * dir;
//
//  for (int i = startDim; i == endDim; i += stepSize) {
//    setPos(i, i);
//
//    if (i % 2 == 0) {
//      delayInterval = delaySpeed();
//    }
//
////    if (i > 1000 && i < 3000) {
////      penDown();
////    } else {
////      penUp();
////    }
//
//    delay(delayInterval);
//  }
//}

const float MAX_SPEED = 3; // max speed = min delay in ms
const float MIN_SPEED = 25; // min speed = max delay in ms
const float OFF_SPEED = -1; // -1 indicates that we should not run at all
float previousSpeed = OFF_SPEED;
float delaySpeed() {
  int val = analogRead(PIN_POT);
  if (val == 0) {
    return OFF_SPEED;
  }
  float interval = max((MIN_SPEED - ((val / 1023.0) * MIN_SPEED)), MAX_SPEED);

  if (previousSpeed != interval) {
    previousSpeed = interval;
//    Serial.print("Delay: ");
//    Serial.println(interval);
//    display.showNumberDec(int(interval), false);
  }

  return interval;
}


// MARK: - Pen Controls

void penUp() {
  digitalWrite(PIN_RELAY, LOW);
}

void penDown() {
  digitalWrite(PIN_RELAY, HIGH);
}


// MARK: - Scaling, Position

// Sets the `x` and `y` axes to the given position ([0, 4096], [0, 4096]).
void setPos(int x, int y) {
  setXPos(x);
  setYPos(y);
}

void setPosFromJoystick(int x, int y) {
  setPos(x * 4, (1024 - y) * 4);
}

// Sets the `x` axis to the given position [0, 4096].
void setXPos(int x) {
  int scaledPos = scaledXPos(x);
//  log("> x: " + String(x) + " => " + String(scaledPos));
  setOutput(0, GAIN_2, 1, scaledPos);
}

// Sets the `y` axis to the given position [0, 4096].
void setYPos(int y) {
  int scaledPos = scaledYPos(y);
//  log("> y: " + String(y) + " => " + String(scaledPos));
  setOutput(1, GAIN_2, 1, scaledPos);
}

// Scales the [0, 4096] input position to the `x` axis' calibrated/scaled/inset position.
int scaledXPos(int x) {
  return scaledPosition(x, INSET, X_INSET_MULT);
}

// Scales the [0, 4096] input position to the `Y` axis' calibrated/scaled/inset position.
int scaledYPos(int y) {
  return scaledPosition(y, INSET, Y_INSET_MULT);
}

int scaledPosition(int pos, int inset, float insetMultiplier) {
  float scaledInset = inset * insetMultiplier;
  float dimension = MAX_DIM - scaledInset;
  return (scaledInset / 2.0) + (float(pos) / MAX_DIM) * dimension;
}


// MARK: - Joystick

int scaledJoystickValue(int value) {
  return (value * 9 / 1024) + 48;
}

void readValues() {
  stickX = analogRead(PIN_STICK_X);
  delay(100); // delay to prevent duplicate read
  stickY = analogRead(PIN_STICK_Y);
  delay(100);

  log("(" + String(stickX) + ", " + String(stickY) + ")");
}


// MARK: - SPI, Utility

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

void log(String text) {
  if (!DEBUG) { return; }
  Serial.println(text);
}
