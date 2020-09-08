// A coordinate of arbitrary units.
struct Point
{
  float x, y;
};

// Represents dimension measurements in inches.
struct Dimension
{
  float width, height;
};

// Describes the Paper being used in terms of dimensions and origin offset;
struct Paper
{
  // The type of paper being used - defines the inches dimensions.
  enum Type
  {
    letter,
    marker,
    maximum
  };

  Type type;

  // {width, height} in inches for the given paper. Oriented
  // landscape to align with the plotter plate.
  static Dimension dimensionForType(Type type)
  {
    switch (type)
    {
    case letter:
      return {11.0, 8.5};
    case marker:
      return {12.0, 9.0};
    case maximum:
      return {15.0, 10.0};
    default:
      return {0, 0};
    }
  }

  // {width, height} in inches for the given paper. See above.
  Dimension getDimension()
  {
    return dimensionForType(type);
  }

  // Returns the {x, y} origin for the current Paper Type in inches
  // in plotter space 15x10 in.
  Point getOriginOffset()
  {
    switch (type)
    {
    case letter:
      // X: inset by delta of horizontal center
      // Y: 0 - bottom
      return {1.25, 0.0};
    case marker:
      return {0.5, 0.0};
    default:
      // Plotter corner origin
      return {0.0, 0.0};
    }
  }

  // Returns the center {x, y} of the current Paper Type in
  // inches in paper space.
  Point getCenter()
  {
    Dimension dim = getDimension();
    return {
        dim.width / 2.0,
        dim.height / 2.0};
  }
};
