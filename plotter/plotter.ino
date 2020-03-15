#include <SPI.h>

/// Debug
#define DEBUG
#ifdef DEBUG
  #define LOG(...)    Serial.print(__VA_ARGS__)
  #define LOGLN(...)  Serial.println(__VA_ARGS__)
#else
  #define LOG(...)    // no-op
  #define LOGLN(...)  //
#endif

/// Arduino 
const int PIN_POT = 2; // Pot
const int PIN_CS = 10; // Clock sync - MCP 4822 12-bit DAC
const int GAIN_1 = 0x1; // UNUSED (?) - HIGH - SPI Output GAIN channel
const int GAIN_2 = 0x0; // LOW - SPI Output GAIN channel
const int PIN_RELAY = 9; // Relay - Controls pen up/down

/// Coordinate / Dimensions
const int MIN_DIM = 0;
const int MAX_DIM = 4096;
const int INSET = 128; // Inset increment
const float X_INSET_MULT = 8.3;  // Inset coefficientsfor calibrated center (2048, 2048)
const float Y_INSET_MULT = 12.2; //

// Drawing
const int DELAY = 20;
 
void setup() {
  Serial.begin(9600); 
  pinMode(PIN_CS, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  SPI.begin();  
  SPI.setClockDivider(SPI_CLOCK_DIV2);

//  int pos = 128 * 16;
//  setPos(pos, pos);
}

// MARK: - Loop
 
void loop() {
  diagonalLoop();
}

void diagonalLoop() {
  int stepSize = (MAX_DIM / 256);
  
  // Forward 
  for (int i = MIN_DIM; i < MAX_DIM; i += stepSize) {
    setPos(i, i);

    if (i > 1000 && i < 3000) {
      penDown();
    } else {
      penUp();
    }
    
    delay(DELAY);
  }

  // Reverse
  for (int i = MAX_DIM; i > MIN_DIM; i -= stepSize) {
    setPos(i, i);

    if (i > 1000 && i < 3000) {
      penDown();
    } else {
      penUp();
    }
    
    delay(DELAY);
  }
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

// Sets the `x` axis to the given position [0, 4096].
void setXPos(int x) {
  int scaledPos = scaledXPos(x);
  setOutput(0, GAIN_2, 1, scaledPos);
}

// Sets the `y` axis to the given position [0, 4096].
void setYPos(int y) {
  int scaledPos = scaledYPos(y);
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
