# Probe Fabrication System — Electrochemical Etching

Control software and firmware for an automated Z-axis linear motion controller used in **tungsten tip electrochemical etching**. Creates ultra-sharp tungsten probes (STM, AFM, etc.) by precisely controlling wire extraction from an etchant solution while monitoring etching current in real-time.

## System Architecture

A **Raspberry Pi** handles all sensing, decision-making, and logging. A dedicated **microcontroller** receives motion commands over serial and generates step/direction pulses for the stepper driver. The serial command protocol is identical across both hardware targets.

```
┌─────────────────────────────────────────────────────────────────┐
│  Raspberry Pi                                                   │
│  ┌──────────────┐  ┌───────────┐  ┌───────┐  ┌──────────────┐  │
│  │ INA219 (I2C) │  │ Relay GPIO│  │ DHT22 │  │  CSV Logger  │  │
│  │ Current Sense│  │ Power Cut │  │ Temp/H│  │  ~/LogFiles/ │  │
│  └──────────────┘  └───────────┘  └───────┘  └──────────────┘  │
│                         Serial (V/U/D/S/T/P/H/X/R)             │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
     ┌────────▼────────┐          ┌─────────▼────────┐
     │  UnoCode/        │          │  STM32Code/       │
     │  Arduino Uno     │          │  Blue Pill         │
     │  + A4988 driver  │          │  + DM542 driver    │
     │  USB Serial      │          │  UART Serial       │
     └─────────────────┘          └──────────────────┘
```

## Directory Structure

```
MotorController/
├── STM32Code/                   ← Active: Blue Pill (STM32F103C8) + DM542
│   ├── src/main.cpp             Firmware (PlatformIO / STM32duino)
│   ├── platformio.ini           PlatformIO build & upload config
│   ├── advanced_dynamic_etch.py Pi-side etch controller (UART serial)
│   └── PIN_SETUP.md             Complete wiring & DIP switch reference
│
├── UnoCode/                     ← Legacy: Arduino Uno + A4988
│   ├── Advanced_Dynamic/        Advanced continuous-pull etch profile
│   ├── Basic_Dynamic/           Basic dynamic pull profile
│   ├── MultiPhase_Static/       Step-by-step static etch profile
│   ├── Motor_Test/              Stepper calibration & test utilities
│   └── PIN_SETUP.md             Complete wiring reference
│
├── Ideas/                       Design notes & reference papers
│   ├── newideas.md              Blue Pill + DM542 migration notes
│   └── scholarworks_uark_etching_paper.md
│
├── Existing Code/               Early development scripts & logs
├── oldcodes/                    Deprecated code versions
└── README.md                    ← You are here
```

## Hardware Targets

| | **STM32Code** (Current) | **UnoCode** (Legacy) |
|---|---|---|
| **MCU** | Blue Pill (STM32F103C8) | Arduino Uno/Nano (ATmega328P) |
| **Driver** | DM542 (industrial, opto-isolated) | A4988 (breakout board) |
| **Microstepping** | DM542 DIP switches (hardware) | MS1/2/3 pins (software) |
| **Serial link** | UART — `/dev/ttyAMA0` | USB — `/dev/ttyACM0` |
| **Step pins** | PA0 / PA1 / PA2 | D2 / D3 / D4 |
| **Max pulse rate** | 200 kHz | ~20 kHz |
| **Dev environment** | PlatformIO + ST-Link | Arduino IDE |

> See `PIN_SETUP.md` inside each folder for full wiring tables and DIP switch settings.

## Etching Profiles

| Profile | Description |
|---------|-------------|
| **Advanced Dynamic** | Static neck-formation phase → constant-speed dynamic pull → auto drop-off detection with dI/dt smoothing and inrush stabilization |
| **Basic Dynamic** | Simpler continuous pull at fixed speed |
| **MultiPhase Static** | Wire stays stationary; step-wise etching phases |
| **Motor Test** | Standalone stepper calibration and speed testing |

## Serial Command Protocol

Both firmware targets accept the same ASCII commands over serial (115200 baud, newline-terminated):

| Command | Action |
|---------|--------|
| `V <um/s>` | Continuous velocity mode (primary etch command) |
| `U <um> <um/s>` | Move up by distance at speed |
| `D <um> <um/s>` | Move down by distance at speed |
| `S <steps> <um/s>` | Move raw microsteps (+/−) at speed |
| `T <um/s> <sec>` | Move at speed for duration |
| `P` | Report current position |
| `H` | Set current position as home (zero) |
| `X` | Disable driver (free-spin) |
| `R` | Re-enable driver |
| `M <div>` | Set microstepping (Uno only; ignored on STM32) |

## Quick Start — STM32 Setup

### 1. Flash the Blue Pill

Install [PlatformIO](https://platformio.org/) and connect an ST-Link V2:

```bash
cd STM32Code
pio run --target upload
```

### 2. Wire the DM542

Connect PUL+/DIR+/ENA+ to a **5V rail**, and PUL−/DIR−/ENA− to PA0/PA1/PA2 (sinking mode). See [STM32Code/PIN_SETUP.md](STM32Code/PIN_SETUP.md) for the full diagram.

### 3. Connect Blue Pill to Pi

Direct 3.3V UART — no level shifter needed:

```
Blue Pill PA9  (TX) ──► Pi GPIO15 (RXD)
Blue Pill PA10 (RX) ◄── Pi GPIO14 (TXD)
GND ──────────────────── GND
```

Disable the Pi serial console: `sudo raspi-config` → Interface Options → Serial → No login shell, Yes hardware.

### 4. Pi Dependencies

```bash
pip install pyserial smbus2 lgpio adafruit-circuitpython-dht
```

### 5. Run an Etch

```bash
cd STM32Code
python advanced_dynamic_etch.py
```

Follow the prompts to enter metadata. The script auto-detects power supply stabilization, runs the etch profile, and cuts power instantly on drop-off.

## Logs & Data

All runs are logged as timestamped CSV files in `~/LogFiles/` on the Pi, containing current readings, state transitions, motor speed, and experiment metadata (temperature, humidity, dipped length, etchant concentration).