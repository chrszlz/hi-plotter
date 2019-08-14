#include <SPI.h>
 
const int PIN_CS = 10;
const int GAIN_1 = 0x1;
const int GAIN_2 = 0x0;

const int W_INSET = 128;
const int H_INSET = 128 * 6;

const bool LOOP_ENABLED = false;
 
void setup()
{
  pinMode(PIN_CS, OUTPUT);
  SPI.begin();  
  SPI.setClockDivider(SPI_CLOCK_DIV2);

  setXPos(2048);
  setYPos(2048d);4
}
 
//assuming single channel, gain=2
void setOutput(unsigned int val)
{
  byte lowByte = val & 0xff;
  byte highByte = ((val >> 8) & 0xff) | 0x10;
   
  PORTB &= 0xfb;
  SPI.transfer(highByte);
  SPI.transfer(lowByte);
  PORTB |= 0x4;
}
 
void setOutput(byte channel, byte gain, byte shutdown, unsigned int val)
{
  byte lowByte = val & 0xff;
  byte highByte = ((val >> 8) & 0xff) | channel << 7 | gain << 5 | shutdown << 4;
   
  PORTB &= 0xfb;
  SPI.transfer(highByte);
  SPI.transfer(lowByte);
  PORTB |= 0x4;
}

float width() {
  return 4096 - W_INSET * 2;
}

float height() {
  return 4096 - H_INSET * 2;
}

int xPos(int index) {
  // this does work
  return W_INSET + (float(index) / 4096) * width();
}

int yPos(int index) {
  return H_INSET + (float(index) / 4096) * height();
}

void setXPos(int index) {
  setOutput(0, GAIN_2, 1, xPos(index));
}

void setYPos(int index) {
  setOutput(1, GAIN_2, 1, yPos(index));
}

 
void loop()
{
  if (!LOOP_ENABLED) { return; }
  
 //high-res triangular wave
 for (int i=0; i < 4096; i+=32)   
 {
  setXPos(i);
  setYPos(i);
  delay(25);
 }
}
