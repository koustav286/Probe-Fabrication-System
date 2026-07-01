# Arduino Uno + A4988 — Complete Pin Setup

> This document describes the **original** hardware configuration using an
> Arduino Uno (ATmega328P) and a Pololu A4988 stepper motor driver.
> For the newer Blue Pill + DM542 setup, see `../STM32Code/PIN_SETUP.md`.

---

## Arduino Pin Assignments

| Function       | Arduino Pin | Direction | Notes                                      |
|----------------|:-----------:|:---------:|--------------------------------------------|
| STEP           | D2          | OUTPUT    | Step pulse to A4988 STEP input              |
| DIR            | D3          | OUTPUT    | Direction signal to A4988 DIR input         |
| ENABLE         | D4          | OUTPUT    | Active-LOW — LOW = driver ON, HIGH = coast  |
| MS1            | D5          | OUTPUT    | Microstepping select bit 0                  |
| MS2            | D6          | OUTPUT    | Microstepping select bit 1                  |
| MS3            | D7          | OUTPUT    | Microstepping select bit 2                  |
| TX (USB)       | —           | OUTPUT    | USB Serial to Raspberry Pi (`/dev/ttyACM0`) |
| RX (USB)       | —           | INPUT     | USB Serial from Raspberry Pi                |

---

## A4988 Module Wiring

```
  A4988 Pin     │  Connect To
  ──────────────┼──────────────────────────────────────────
  VMOT          │  Motor power supply (+)  8–35 V
  GND (motor)   │  Motor power supply (−)
  1A, 1B        │  Stepper coil 1 (A+, A−)
  2A, 2B        │  Stepper coil 2 (B+, B−)
  VDD           │  Arduino 5 V
  GND (logic)   │  Arduino GND
  STEP          │  Arduino D2
  DIR           │  Arduino D3
  ENABLE        │  Arduino D4   (LOW = enabled)
  SLEEP         │  Tie to RESET (both HIGH → driver active)
  RESET         │  Tie to SLEEP
  MS1           │  Arduino D5
  MS2           │  Arduino D6
  MS3           │  Arduino D7
```

> **IMPORTANT:** Place a **100 µF electrolytic capacitor** across VMOT and GND
> as close to the A4988 module as possible to protect against voltage spikes.

---

## A4988 Microstepping Truth Table

Microstepping is set **in software** via pins MS1/MS2/MS3:

| MS1 | MS2 | MS3 | Step Mode  |
|:---:|:---:|:---:|:----------:|
| LOW | LOW | LOW | Full step  |
| HIGH| LOW | LOW | 1/2 step   |
| LOW | HIGH| LOW | 1/4 step   |
| HIGH| HIGH| LOW | 1/8 step   |
| HIGH| HIGH| HIGH| 1/16 step  |

Default in firmware: **1/16 microstepping**.

---

## A4988 Current Limit

Set via the on-board potentiometer:

```
I_trip = Vref / (8 × Rs)

Rs = sense resistor (typically 0.068 Ω on most boards)
For a 0.5 A motor:  Vref = 0.5 × 8 × 0.068 = 0.272 V
```

Measure between the Vref test pad and GND while adjusting the pot.

---

## Serial Communication (Arduino → Raspberry Pi)

- **Interface:** USB Serial (CDC/ACM)
- **Pi device:** `/dev/ttyACM0`
- **Baud rate:** 115200
- **Protocol:** ASCII commands, newline-terminated

---

## Raspberry Pi Side (Unchanged)

| Function       | Pi Pin / Bus       | Notes                            |
|----------------|:------------------:|----------------------------------|
| INA219 Sensor  | I2C Bus 1 (0x40)   | Current sensing via `smbus2`     |
| Relay          | GPIO 17             | Active-LOW, cuts etch power      |
| DHT22          | GPIO 27             | Temperature & humidity logging   |
| Serial RX      | USB (`/dev/ttyACM0`)| From Arduino TX                  |
| Serial TX      | USB (`/dev/ttyACM0`)| To Arduino RX                    |

---

## Mechanical Parameters

| Parameter              | Value      | Notes                                  |
|------------------------|:----------:|----------------------------------------|
| Motor steps/rev        | 200        | 1.8° standard hybrid stepper           |
| Lead screw pitch       | 500 µm/rev | M3×0.5 lead screw (adjust for yours)  |
| Default microstepping  | 16         | 1/16 step via MS pins                  |
| µm per microstep       | 0.15625    | 500 / (200 × 16)                       |
