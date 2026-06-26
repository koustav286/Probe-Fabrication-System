# Probe Fabrication System (Electrochemical Etching)

This repository contains the control software and firmware for an automated Z-Axis Linear Motion Controller used in **Tungsten Tip Electrochemical Etching**. The system creates ultra-sharp tungsten probes (used in STM, AFM, etc.) by precisely controlling the extraction of a tungsten wire from an etchant solution while monitoring the etching current.

## Features

- **Automated Z-Axis Motion:** Controls a hybrid stepper motor (via A4988 driver) to smoothly extract the probe from the etchant.
- **Current Monitoring:** Real-time current sensing (via INA219 via I2C) to detect the exact moment the probe "drops off" and finishes etching.
- **Auto-Cutoff Relay:** Instantly cuts the etching voltage using a GPIO relay when the drop-off is detected to prevent blunting the tip.
- **Multi-Phase Etching Profiles:** 
  - *Static Etching:* Wire remains stationary.
  - *Dynamic Etching:* Wire is gradually pulled out at a constant/variable speed to control the probe taper/apex radius.
- **Environment Logging:** Automatically reads a DHT22 sensor (Temperature & Humidity) to log environmental conditions during fabrication for reproducibility.

## Hardware Architecture

1. **Microcontroller (Arduino Uno/Nano):** 
   - Runs `MotorController.ino`.
   - Directly interfaces with the A4988 stepper motor driver.
   - Listens to serial commands (`U`, `D`, `S`, `T`, `V`) to move the Z-axis stage.
2. **Controller (Raspberry Pi):** 
   - Runs the Python etch scripts (e.g., `advanced_dynamic_etch.py`).
   - Monitors the INA219 current sensor via I2C (`0x40`).
   - Controls the power relay on GPIO 17.
   - Reads the DHT22 on GPIO 27.
   - Communicates with the Arduino over USB/Serial (`/dev/ttyACM0`).

## Directory Structure

- `/Dynamic_Etch_Release/` - Contains the production-ready etching scripts and firmware.
  - `Advanced_Dynamic/` - Advanced continuous pull etching profile.
  - `Basic_Dynamic/` - Basic dynamic pull profile.
  - `MultiPhase_Static/` - Step-by-step static etching profile.
  - `Motor_Test/` - Utilities for calibrating and testing the stepper motor stage.
- `/Existing Code/` - Legacy and reference scripts.
- `/oldcodes/` - Deprecated code versions.

## Setup & Usage

### 1. Arduino Firmware
- Open `Dynamic_Etch_Release/Advanced_Dynamic/MotorController.ino` in the Arduino IDE.
- Adjust `PITCH_UM` and `microstepping` to match your specific lead screw and driver configuration.
- Flash to your Arduino Uno/Nano.

### 2. Python Environment (Raspberry Pi)
Ensure you have the required dependencies installed:
```bash
pip install pyserial smbus2 lgpio adafruit-circuitpython-dht
```

### 3. Running an Etch
1. Mount the tungsten wire to the Z-axis stage and submerge the tip into the etchant (e.g., KOH).
2. Connect the etching circuit (power supply through the INA219 and Relay to the etching cell).
3. Run the desired profile:
```bash
python Dynamic_Etch_Release/Advanced_Dynamic/advanced_dynamic_etch.py
```
4. Follow the on-screen prompts to enter metadata (dipped length, concentration). The script will automatically wait for the power supply to stabilize, begin the etching profile, and cut power instantly when the tip drops off.

## Logs & Data
All etching runs are logged automatically as CSV files in `~/LogFiles/` on the Raspberry Pi, containing timestamps, real-time current (mA), motor speed, and environmental metadata.