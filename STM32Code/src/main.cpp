// Z-Axis Linear Motion Controller for Tungsten Tip Electrochemical Etching
// Hardware: Blue Pill (STM32F103C8) + DM542 Industrial Stepper Driver
//
// Ported from the Arduino Uno + A4988 version. See ../UnoCode/ for original.
// See PIN_SETUP.md for complete wiring documentation.
//
// ═══════════════════════════════════════════════════════════════════════════════
// WIRING — DM542 Driver (Active-Low Sinking from 5V Rail)
// ═══════════════════════════════════════════════════════════════════════════════
//
//  DM542 Pin  │  Connect To
//  ───────────┼──────────────────────────────────────────────────────────────────
//  PUL+       │  External 5V rail (NOT Blue Pill 3.3V!)
//  PUL−       │  Blue Pill PA0        (STEP — GPIO sinks current when LOW)
//  DIR+       │  External 5V rail
//  DIR−       │  Blue Pill PA1        (DIR  — GPIO sinks current when LOW)
//  ENA+       │  External 5V rail
//  ENA−       │  Blue Pill PA2        (ENABLE — GPIO sinks current when LOW)
//  A+, A−     │  Stepper coil 1
//  B+, B−     │  Stepper coil 2
//  V+         │  Motor power supply (+)  20–48 VDC
//  GND        │  Motor power supply (−)
//
// ═══════════════════════════════════════════════════════════════════════════════
// SERIAL — USART1 to Raspberry Pi (3.3V direct, no level shifter)
// ═══════════════════════════════════════════════════════════════════════════════
//
//  Blue Pill PA9  (TX)  ──►  Pi GPIO15 (RXD)
//  Blue Pill PA10 (RX)  ◄──  Pi GPIO14 (TXD)
//  Blue Pill GND        ───  Pi GND
//
//  Pi serial device: /dev/ttyAMA0  (or /dev/serial0)
//
// ═══════════════════════════════════════════════════════════════════════════════
// MICROSTEPPING — set via DM542 DIP switches (SW5–SW8), NOT software
// ═══════════════════════════════════════════════════════════════════════════════
//  The MICROSTEPPING constant below MUST match the physical DIP switch setting.
//  Default: 16 (SW5=ON, SW6=OFF, SW7=ON, SW8=ON → 3200 pulses/rev)
// ═══════════════════════════════════════════════════════════════════════════════

#include <AccelStepper.h>

// ---------------------------------------------------------------------------
//  PIN ASSIGNMENTS — Blue Pill (STM32F103C8)
// ---------------------------------------------------------------------------
const int PIN_STEP   = PA0;
const int PIN_DIR    = PA1;
const int PIN_ENABLE = PA2;

// NOTE: MS1/MS2/MS3 pins are REMOVED — DM542 uses physical DIP switches.

AccelStepper stepper(AccelStepper::DRIVER, PIN_STEP, PIN_DIR);

// ---------------------------------------------------------------------------
//  SERIAL PORT — Use USART1 (PA9/PA10) instead of USB
// ---------------------------------------------------------------------------
// On STM32duino, Serial1 = USART1 (PA9 TX, PA10 RX).
// We define a macro so all code below uses "SerialPort" for easy swapping.
#define SerialPort Serial1

// Direction semantics — adjust if your wiring is reversed
// NOTE: With DM542 sinking mode, the logic is inverted at the hardware level.
// When GPIO goes LOW, current flows and the opto-coupler activates.
// AccelStepper handles this through setPinsInverted().
const int DIR_UP   = HIGH;  // wire moves UP (out of etchant)
const int DIR_DOWN = LOW;   // wire moves DOWN (into etchant)

// ---------------------------------------------------------------------------
//  MECHANICAL PARAMETERS — adapt to your lead screw / stage
// ---------------------------------------------------------------------------
// Motor: 1.8°/step → 200 full steps/rev (standard hybrid stepper)
const int FULL_STEPS_PER_REV = 200;

// Lead screw / stage pitch: linear travel per revolution (µm)
// Example: M3×0.5 lead screw → 500 µm/rev.  Adjust this for your stage.
const float PITCH_UM = 500.0;

// Microstepping divisor — MUST match DM542 DIP switch setting!
// This is a compile-time constant. Change it here if you change the DIP switches.
const int MICROSTEPPING = 16;

// Derived: microsteps per revolution, and µm per microstep
float microstepsPerRev() { return (float)FULL_STEPS_PER_REV * MICROSTEPPING; }
float umPerMicrostep()   { return PITCH_UM / microstepsPerRev(); }

// ---------------------------------------------------------------------------
//  ENABLE / DISABLE DRIVER
// ---------------------------------------------------------------------------
// DM542 ENA input: When ENA− is pulled LOW (sinking), driver is ENABLED.
// This matches the A4988 active-low convention, so AccelStepper logic is same.
void enableDriver()  { stepper.enableOutputs();  }
void disableDriver() { stepper.disableOutputs(); }

// ---------------------------------------------------------------------------
//  CORE MOTION PRIMITIVE
//  Move `steps` microsteps at the given speed (µm/s).
//  Positive steps = UP, negative = DOWN.
//  Returns actual steps requested.
// ---------------------------------------------------------------------------
// Global flag to track if we are in continuous velocity mode
bool continuousMode = false;

long moveSteps(long steps, float speedUmPerSec) {
  if (steps == 0 || speedUmPerSec <= 0)
    return 0;

  continuousMode = false; // Switch to positional mode
  float stepsPerSec = speedUmPerSec / umPerMicrostep();
  stepper.setMaxSpeed(stepsPerSec);
  stepper.setAcceleration(stepsPerSec *
                          10.0); // High acceleration for quick start

  stepper.move(steps);
  // Non-blocking: stepper.run() is called in loop()

  return steps;
}

// ---------------------------------------------------------------------------
//  HIGH-LEVEL MOTION: move a given distance (µm) at a given speed (µm/s)
// ---------------------------------------------------------------------------
void moveUm(float distanceUm, float speedUmPerSec) {
  long steps = (long)(distanceUm / umPerMicrostep());
  SerialPort.print(F("Moving "));
  SerialPort.print(distanceUm, 1);
  SerialPort.print(F(" um at "));
  SerialPort.print(speedUmPerSec, 1);
  SerialPort.print(F(" um/s  ("));
  SerialPort.print(abs(steps));
  SerialPort.println(F(" microsteps)"));

  moveSteps(steps, speedUmPerSec);
  reportPosition();
}

// ---------------------------------------------------------------------------
//  HIGH-LEVEL MOTION: move for a given duration (seconds) at a given speed
// ---------------------------------------------------------------------------
void moveForDuration(float speedUmPerSec, float durationSec) {
  float distUm = speedUmPerSec * durationSec;
  moveUm(distUm, fabs(speedUmPerSec));
}

// ---------------------------------------------------------------------------
//  POSITION REPORTING
// ---------------------------------------------------------------------------
void reportPosition() {
  long posSteps = stepper.currentPosition();
  float posUm = posSteps * umPerMicrostep();
  SerialPort.print(F("Position: "));
  SerialPort.print(posUm, 2);
  SerialPort.print(F(" um  ("));
  SerialPort.print(posSteps);
  SerialPort.println(F(" steps)"));
}

// ---------------------------------------------------------------------------
//  SERIAL COMMAND INTERFACE
//  Commands (newline-terminated):
//    U <um> <um/s>       Move up by <um> at <um/s>
//    D <um> <um/s>       Move down by <um> at <um/s>
//    S <steps> <um/s>    Move raw steps (+ = up, − = down) at <um/s>
//    T <um/s> <sec>      Move at speed for duration (+ = up)
//    V <um/s>            Move continuously at given speed (+ = up)
//    M <div>             (IGNORED — DM542 uses DIP switches)
//    P                   Report current position
//    H                   Set current position as home (zero)
//    X                   Disable driver (free-spin / release torque)
//    R                   Re-enable driver
//    ?                   Print help
// ---------------------------------------------------------------------------
void processCommand(const String &cmd) {
  if (cmd.length() == 0)
    return;

  char op = cmd.charAt(0);
  String args = cmd.substring(1);
  args.trim();

  switch (op) {
  case 'U':
  case 'u': {
    int spaceIdx = args.indexOf(' ');
    float dist = args.substring(0, spaceIdx).toFloat();
    float spd = args.substring(spaceIdx + 1).toFloat();
    if (spd <= 0) {
      SerialPort.println(F("ERR: speed must be > 0"));
      break;
    }
    moveUm(fabs(dist), spd);
    break;
  }
  case 'D':
  case 'd': {
    int spaceIdx = args.indexOf(' ');
    float dist = args.substring(0, spaceIdx).toFloat();
    float spd = args.substring(spaceIdx + 1).toFloat();
    if (spd <= 0) {
      SerialPort.println(F("ERR: speed must be > 0"));
      break;
    }
    moveUm(-fabs(dist), spd);
    break;
  }
  case 'S':
  case 's': {
    int spaceIdx = args.indexOf(' ');
    long st = args.substring(0, spaceIdx).toInt();
    float spd = args.substring(spaceIdx + 1).toFloat();
    if (spd <= 0) {
      SerialPort.println(F("ERR: speed must be > 0"));
      break;
    }
    moveSteps(st, spd);
    reportPosition();
    break;
  }
  case 'T':
  case 't': {
    int spaceIdx = args.indexOf(' ');
    float spd = args.substring(0, spaceIdx).toFloat();
    float dur = args.substring(spaceIdx + 1).toFloat();
    if (dur <= 0) {
      SerialPort.println(F("ERR: duration must be > 0"));
      break;
    }
    moveForDuration(spd, dur);
    break;
  }
  case 'V':
  case 'v': {
    float spd = args.toFloat();
    float stepsPerSec = spd / umPerMicrostep();
    stepper.setMaxSpeed(20000.0); // DM542 supports up to 200kHz — generous headroom
    stepper.setSpeed(stepsPerSec);
    continuousMode = true;
    SerialPort.print(F("Continuous velocity: "));
    SerialPort.print(spd, 2);
    SerialPort.println(F(" um/s"));
    break;
  }
  case 'M':
  case 'm': {
    // DM542 microstepping is set via physical DIP switches, not software.
    SerialPort.println(F("NOTE: Microstepping is set via DM542 DIP switches (SW5-SW8)."));
    SerialPort.print(F("Firmware assumes 1/"));
    SerialPort.print(MICROSTEPPING);
    SerialPort.println(F(". Change DIP switches and update MICROSTEPPING constant if needed."));
    break;
  }
  case 'P':
  case 'p':
    reportPosition();
    break;
  case 'H':
  case 'h':
    stepper.setCurrentPosition(0);
    SerialPort.println(F("Home position set (0 um)"));
    break;
  case 'X':
  case 'x':
    disableDriver();
    SerialPort.println(F("Driver DISABLED (free-spin)"));
    break;
  case 'R':
  case 'r':
    enableDriver();
    SerialPort.println(F("Driver ENABLED"));
    break;
  case '?':
    printHelp();
    break;
  default:
    SerialPort.print(F("Unknown command: "));
    SerialPort.println(op);
    printHelp();
    break;
  }
}

void printHelp() {
  SerialPort.println(F(""));
  SerialPort.println(F("═══ Z-Axis Controller Commands ═══"));
  SerialPort.println(F("  U <um> <um/s>                 Move UP"));
  SerialPort.println(F("  D <um> <um/s>                 Move DOWN"));
  SerialPort.println(
      F("  S <steps> <um/s>              Move raw microsteps (+/-)"));
  SerialPort.println(
      F("  T <um/s> <sec>                Move at speed for duration"));
  SerialPort.println(F("  V <um/s>                      Continuous velocity mode"));
  SerialPort.println(F("  M <div>                       (DM542: use DIP switches)"));
  SerialPort.println(F("  P                             Report position"));
  SerialPort.println(F("  H                             Set home (zero)"));
  SerialPort.println(F("  X                             Disable driver"));
  SerialPort.println(F("  R                             Enable driver"));
  SerialPort.println(F("  ?                             This help"));
  SerialPort.println(F(""));
}

// ---------------------------------------------------------------------------
//  SETUP
// ---------------------------------------------------------------------------
void setup() {
  // AccelStepper configuration
  stepper.setEnablePin(PIN_ENABLE);
  stepper.setPinsInverted(
      (DIR_UP == LOW), false,
      true); // Invert dir if DIR_UP is LOW, Enable is Active-Low

  // Default state: driver enabled
  enableDriver();

  // Start USART1 for communication with Raspberry Pi
  SerialPort.begin(115200);
  delay(200);

  SerialPort.println(F(""));
  SerialPort.println(F("╔══════════════════════════════════════════════════════╗"));
  SerialPort.println(F("║  Z-Axis Motor Controller — Tungsten Tip Etching     ║"));
  SerialPort.println(F("║  STM32 Blue Pill + DM542 Industrial Driver          ║"));
  SerialPort.println(F("╚══════════════════════════════════════════════════════╝"));
  SerialPort.print(F("  Step resolution: "));
  SerialPort.print(umPerMicrostep(), 4);
  SerialPort.println(F(" um/microstep"));
  SerialPort.print(F("  Microstepping:   1/"));
  SerialPort.print(MICROSTEPPING);
  SerialPort.println(F("  (DM542 DIP switches)"));
  SerialPort.print(F("  Lead pitch:      "));
  SerialPort.print(PITCH_UM, 1);
  SerialPort.println(F(" um/rev"));
  SerialPort.println(F(""));
  printHelp();
}

// ---------------------------------------------------------------------------
//  MAIN LOOP — serial command processing
// ---------------------------------------------------------------------------
String serialBuffer = "";

void loop() {
  while (SerialPort.available()) {
    char c = SerialPort.read();
    if (c == '\n' || c == '\r') {
      serialBuffer.trim();
      if (serialBuffer.length() > 0) {
        processCommand(serialBuffer);
      }
      serialBuffer = "";
    } else {
      serialBuffer += c;
    }
  }

  // Non-blocking motion execution
  if (continuousMode) {
    stepper.runSpeed();
  } else {
    stepper.run();
  }
}
