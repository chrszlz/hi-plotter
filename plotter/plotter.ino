#include <SPI.h>
 
const int PIN_CS = 10;
const int GAIN_1 = 0x1;
const int GAIN_2 = 0x0;
const int PIN_STICK_X = 0;
const int PIN_STICK_Y = 1;

const int W_INSET = 128;
const int H_INSET = 128 * 6;

const int W_INSET_LETTER = 128 * 4;
const int H_INSET_LETTER = 128 * 7;

const bool LOOP_ENABLED = false;
const bool DEBUG = true;

// Joystick values
int stickX = 0;
int stickY = 0;

// Current position
int x = 2048;
int y = 2048;
 
void setup()
{
  Serial.begin(9600); 
  pinMode(PIN_CS, OUTPUT);
  SPI.begin();  
  SPI.setClockDivider(SPI_CLOCK_DIV2);
}

// MARK: - Loop
 
void loop()
{
  readValues();
  setPosFromJoystick(stickX, stickY);
  
  if (!LOOP_ENABLED) { return; }
  diagonalLoop();
}

void diagonalLoop() {
  for (int i = 0; i < 4096; i += (4096 / 256)) {
    setPos(i, i);
    delay(25);
  }
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
  int width = 4096 - W_INSET * 2;
  return W_INSET + (float(x) / 4096) * width;
}

// Scales the [0, 4096] input position to the `Y` axis' calibrated/scaled/inset position.
int scaledYPos(int y) {
  int height = 4096 - H_INSET * 2;
  return H_INSET + (float(y) / 4096) * height;
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
