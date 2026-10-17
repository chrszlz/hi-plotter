#include "plotter.cpp"

/// Debug
#define DEBUG
#ifdef DEBUG
#define LOG(...) Serial.print(__VA_ARGS__)
#define LOGLN(...) Serial.println(__VA_ARGS__)
#else
#define LOG(...)   // no-op
#define LOGLN(...) //
#endif

/// Arduino
// const int PIN_POT = 2; // Pot
// const float stepSize = 0.005;

// Delay Utility
const int DELAY_SHORT = 5;   // Shape drawing
const int DELAY = 20;        // Linear coords
const int DELAY_LONG = 1000; // Step pause
const int DELAY_PEN = 150;   // Pen up/down

void DS() { delay(DELAY_SHORT); }
void D() { delay(DELAY); }
void DL() { delay(DELAY_LONG); }
void DP() { delay(DELAY_PEN); }

Plotter plotter;
boolean hasDrawn = false;

void setup()
{
  Serial.begin(9600);

  // Setup plotter
  plotter.penUp();
  delay(750);

  // Setup paper
  plotter.paper.type = Paper::Type::marker;
}

// MARK: - Loop

void loop()
{
  // Draw on first loop only
  if (!hasDrawn)
  {
    draw();
    hasDrawn = true;

    // Return home.
    plotter.goToOrigin();
  }
}

// Draw in me
void draw()
{
  // plotter.visualizePaperDimensions();
  drawSquares();
}

void drawSquares()
{
  // Outer
  plotter.goToCenter();
  delay(1000);
  plotter.penDown();
  delay(750);

  // Up
  plotter.move({0, 1.5});
  delay(500);

  // Right
  plotter.move({3, 0});
  delay(500);

  // Down
  plotter.move({0, -3});
  delay(500);

  // Left
  plotter.move({-2, 0});
  delay(500);

  plotter.penUp();
  delay(750);

  // Inner

  // Up
  plotter.move({0, 1});
  delay(500);

  plotter.penDown();
  delay(750);

  // Up
  plotter.move({0, 1});
  delay(500);

  // Right
  plotter.move({1, 0});
  delay(500);

  // Down
  plotter.move({0, -1});
  delay(500);

  // Left
  plotter.move({-1, 0});
  delay(500);

  plotter.penUp();
  delay(750);
}

  //////////////////////////
 ////////// Test //////////
//////////////////////////

// void drawCircles() {
//   float x = 0.5;
//     float y = 0.15;
//     float rad = 0.02;
//     for (float i = 0; i <= 0.1; i += 0.05) {
//       float z = pow(i, 2) / 0.5;
//       drawCircle(x - (z * 0.75), y, rad + z, true);
//     }
// }

// void drawCircle(float x,float y, float radius, boolean dryRun) {
//   // Set initial coords
//   double px = x + radius * cos(0);
//   double py = y + radius * sin(0);
//   setPos(px, py);

//   if (!dryRun) {
//     // Pause and pen down
//     drawWillBegin();
//   }

//   // Draw circle
//   for (float i=0; i<(360 * 1.04); i+= 0.25) { // Coeff for extra steps depending upon radius a bigger radius might need more steps
//     double radians = i * PI / 180;
//     double px = x + radius * cos(radians);
//     double py = y + radius * sin(radians);
//     setPos(px, py);

//     delay(1); // Coord delay
//   }

//   if (!dryRun) {
//     // Pause and pen up
//     drawDidEnd();
//   }
// }

// float dist(float x0, float y0, float x1, float y1)
// {
//   return sqrt(pow(x1 - x0, 2) + pow(y1 - y0, 2));
// }

// void draw(float x0, float x1)
// {
//   float delta = fabs(x1 - x0);
//   for (float i = 0.0; i < delta; i += stepSize)
//   {
//     float n = i / delta;
//     float x = smoothstep(x0, x1, n);
//     Serial.println(x);
//   }
// }

// float smoothstep(float x0, float x1, float val)
// {
//   // Scale, bias and saturate x to 0..1 range
//   val = clamp((val - x0) / (x1 - x0), 0.0, 1.0);
//   // Evaluate polynomial
//   return val * val * (3 - 2 * val);
// }

// float clamp(float x, float lowerlimit, float upperlimit)
// {
//   if (x < lowerlimit)
//     x = lowerlimit;
//   if (x > upperlimit)
//     x = upperlimit;
//   return x;
// }
