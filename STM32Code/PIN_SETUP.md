# Blue Pill (STM32F103C8) + DM542 — Complete Pin Setup

> This document describes the **new** hardware configuration using a
> Blue Pill (STM32F103C8) and a DM542 industrial stepper motor driver.
> For the original Arduino Uno + A4988 setup, see `../UnoCode/PIN_SETUP.md`.

---

## Blue Pill Pin Assignments

| Function       | Blue Pill Pin | Direction | Notes                                            |
|----------------|:-------------:|:---------:|--------------------------------------------------|
| STEP (PUL−)    | PA0           | OUTPUT    | Step pulse — sinks current from DM542 PUL+ (5V)  |
| DIR (DIR−)     | PA1           | OUTPUT    | Direction — sinks current from DM542 DIR+ (5V)    |
| ENABLE (ENA−)  | PA2           | OUTPUT    | Enable — sinks current from DM542 ENA+ (5V)       |
| UART TX        | PA9           | OUTPUT    | USART1 TX → Raspberry Pi GPIO15 (RXD)            |
| UART RX        | PA10          | INPUT     | USART1 RX ← Raspberry Pi GPIO14 (TXD)            |

> **MS1/MS2/MS3 pins are NOT used.** Microstepping on the DM542 is set via
> physical DIP switches (SW5–SW8) on the driver body.

---

## DM542 Wiring — 5V Sinking Configuration

The DM542 has **optically isolated** differential inputs. The Blue Pill outputs
3.3V logic, which is **not enough** to reliably drive the opto-coupler LEDs
directly. The solution is to wire in **active-low sinking mode**:

```
              5V Rail (external)
                 │
    DM542        │
  ┌──────┐       │
  │ PUL+ ├───────┘
  │ PUL− ├───────────── PA0  (Blue Pill)
  │      │
  │ DIR+ ├───────┐
  │ DIR− ├───────│───── PA1  (Blue Pill)
  │      │       │
  │ ENA+ ├───────┤      5V Rail
  │ ENA− ├───────│───── PA2  (Blue Pill)
  └──────┘       │
                 └── All (+) pins share the same 5V source
```

### How it works:
- When GPIO goes **LOW** → current flows: 5V → opto LED → GPIO (sink) → GND
- When GPIO goes **HIGH** (3.3V) → voltage difference is only ~1.7V → opto LED stays OFF
- The internal opto-coupler has ~150–200Ω series resistance → ~19 mA at 5V, well within spec
- Blue Pill GPIOs can safely sink up to 25 mA per pin

> **CAUTION:** The 5V rail for PUL+/DIR+/ENA+ must be a **separate 5V supply**
> or the Raspberry Pi's 5V pin — do **NOT** use the Blue Pill's 3.3V output.
> The Blue Pill 5V pin (from USB) can also work if connected via USB.

---

## DM542 Motor Wiring

```
  DM542 Pin     │  Connect To
  ──────────────┼──────────────────────────────
  A+            │  Stepper coil 1 (A+)
  A−            │  Stepper coil 1 (A−)
  B+            │  Stepper coil 2 (B+)
  B−            │  Stepper coil 2 (B−)
  V+            │  Motor power supply (+)  20–48 VDC
  GND           │  Motor power supply (−)
```

---

## DM542 Microstepping — DIP Switch Settings

Microstepping is set **physically** using DIP switches SW5–SW8 on the DM542 body.
**No software control.** The firmware assumes a fixed microstep divisor that must
match the physical switch setting.

| SW5 | SW6 | SW7 | SW8 | Microstep | Pulses/Rev |
|:---:|:---:|:---:|:---:|:---------:|:----------:|
| ON  | ON  | ON  | ON  | Full step | 200        |
| ON  | ON  | ON  | OFF | 1/2 step  | 400        |
| ON  | ON  | OFF | ON  | 1/4 step  | 800        |
| ON  | ON  | OFF | OFF | 1/8 step  | 1600       |
| ON  | OFF | ON  | ON  | 1/16 step | 3200       |
| ON  | OFF | ON  | OFF | 1/32 step | 6400       |
| ON  | OFF | OFF | ON  | 1/64 step | 12800      |
| ON  | OFF | OFF | OFF | 1/128 step| 25600      |
| OFF | ON  | ON  | ON  | 1/256 step| 51200      |
| OFF | ON  | ON  | OFF | 5 µstep   | 1000       |
| OFF | ON  | OFF | ON  | 10 µstep  | 2000       |
| OFF | ON  | OFF | OFF | 25 µstep  | 5000       |
| OFF | OFF | ON  | ON  | 50 µstep  | 10000      |
| OFF | OFF | ON  | OFF | 125 µstep | 25000      |
| OFF | OFF | OFF | ON  | 250 µstep | 50000      |
| OFF | OFF | OFF | OFF | Reserved  | —          |

> **IMPORTANT:** If you change the DIP switches, you **must** also update the
> `MICROSTEPPING` constant in `src/main.cpp` and re-flash the Blue Pill.
> Default is **16** (SW5=ON, SW6=OFF, SW7=ON, SW8=ON → 3200 pulses/rev).

---

## DM542 Current Limit — DIP Switch Settings

Set motor peak current using DIP switches SW1–SW3:

| SW1 | SW2 | SW3 | Peak Current |
|:---:|:---:|:---:|:------------:|
| ON  | ON  | ON  | 1.00 A       |
| ON  | ON  | OFF | 1.46 A       |
| ON  | OFF | ON  | 1.91 A       |
| ON  | OFF | OFF | 2.37 A       |
| OFF | ON  | ON  | 2.84 A       |
| OFF | ON  | OFF | 3.31 A       |
| OFF | OFF | ON  | 3.76 A       |
| OFF | OFF | OFF | 4.20 A       |

**SW4** controls idle current reduction: ON = 50% at standstill, OFF = full current always.

---

## Serial Communication (Blue Pill → Raspberry Pi)

- **Interface:** USART1 hardware UART (PA9 TX, PA10 RX)
- **Pi device:** `/dev/ttyAMA0` (or `/dev/serial0`)
- **Baud rate:** 115200
- **Protocol:** ASCII commands, newline-terminated (same as the Arduino version)
- **Voltage:** Both sides are 3.3V — **direct connection, no level shifter needed**

### Wiring:
```
  Blue Pill PA9  (TX)  ───────►  Pi GPIO15 (RXD)
  Blue Pill PA10 (RX)  ◄───────  Pi GPIO14 (TXD)
  Blue Pill GND        ────────  Pi GND
```

> **NOTE:** You must disable the Pi's serial console before using UART:
> `sudo raspi-config` → Interface Options → Serial → "No" for login shell,
> "Yes" for serial hardware.

---

## Raspberry Pi Side (Unchanged except serial port)

| Function       | Pi Pin / Bus          | Notes                            |
|----------------|:---------------------:|----------------------------------|
| INA219 Sensor  | I2C Bus 1 (0x40)      | Current sensing via `smbus2`     |
| Relay          | GPIO 17                | Active-LOW, cuts etch power      |
| DHT22          | GPIO 27                | Temperature & humidity logging   |
| Serial RX      | GPIO15 (`/dev/ttyAMA0`)| From Blue Pill PA9 (TX)          |
| Serial TX      | GPIO14 (`/dev/ttyAMA0`)| To Blue Pill PA10 (RX)           |

---

## Mechanical Parameters

| Parameter              | Value      | Notes                                        |
|------------------------|:----------:|----------------------------------------------|
| Motor steps/rev        | 200        | 1.8° standard hybrid stepper                 |
| Lead screw pitch       | 500 µm/rev | M3×0.5 lead screw (adjust for yours)        |
| Default microstepping  | 16         | Set via DM542 DIP switches, matched in code  |
| µm per microstep       | 0.15625    | 500 / (200 × 16)                             |
| Max pulse frequency    | 200 kHz    | DM542 rated (vs ~20 kHz for A4988)           |
