What the Current System Does
Two separate brains talking to each other:
The Raspberry Pi is the intelligent controller — it runs the Python script (Dynamic_Etch_Auto_8Channel.py), which:

Reads 8 INA219 current sensors across two I2C buses (bus 1 and bus 3, four sensors each)
Controls 8 individual relay GPIOs — one relay per wire, cuts power the instant that wire drops off
Detects drop-off per channel using a ΔR threshold — computes R = V/I each loop, triggers relay when ΔR spikes above DEL_R_THRESHOLD while current is below 2.5mA
Maps total current across all active channels linearly to a lift speed between MIN_LIFT_SPEED and MAX_LIFT_SPEED
Sends V <speed> over serial to the Arduino every loop cycle
Logs everything to CSV

The Arduino is a dumb motion executor — it just:

Receives ASCII commands over serial (V, U, D, S, T, M, P, H, X, R)
Uses AccelStepper in DRIVER mode to generate STEP/DIR pulses to the A4988
In continuous mode (V <speed>), calls stepper.runSpeed() every loop

The split is clean: Pi decides what speed to run, Arduino executes it. That architecture stays the same.

What Changes With Blue Pill + DM542
The DM542 — bigger deal than it sounds
The DM542 is a serious industrial driver, not a hobbyist IC like the A4988. Key differences that directly affect your code and wiring:
Microstepping is set by DIP switches, not pins. The A4988 had MS1/2/3 pins your Arduino controlled programmatically with the M <div> command. The DM542 has SW5–SW8 physical switches on the body. This means:

Remove the MS1/2/3 pin definitions and applyMicrostepping() function entirely from the firmware
Remove the M <div> serial command (or keep it as a no-op with a warning)
Set your microstep resolution once physically before a run — it doesn't change during etching

Signal inputs are optically isolated. The DM542 has PUL+/PUL−, DIR+/DIR−, ENA+/ENA− differential inputs with opto-isolators inside. This is good for noise immunity but creates a voltage problem explained below.
It's rated for much higher pulse frequencies — up to 200kHz step pulses. The A4988 starts struggling above ~20kHz. This matters if you ever want very fine microstep resolution at high speeds.

The Blue Pill — the voltage problem you must solve
The Blue Pill (STM32F103C8) outputs 3.3V logic. The DM542 opto-isolators are designed assuming ~5V signals. The way the DM542 inputs work:
PUL+ ──── [resistor] ──── opto LED ──── PUL−
The opto LED needs ~7–20mA to trigger reliably. With a 5V signal and a ~150Ω resistor, that's fine. With 3.3V, it can fail to trigger or trigger intermittently.
The fix — two options:
Option A (simplest): Connect PUL+, DIR+, ENA+ to your 5V rail (not 3.3V, not STM32 — a separate 5V supply or Pi 5V pin). Connect PUL−, DIR−, ENA− to the Blue Pill GPIO pins. When the GPIO goes LOW, current flows from 5V through the opto LED to GPIO (sinking mode). With 5V supply and ~1.2V LED drop, ~3.8V across your series resistor — 200Ω gives ~19mA. Works perfectly, and the Blue Pill GPIO can safely sink this.
Option B: Use a 3.3V to 5V level shifter IC (like a 74AHCT125) between Blue Pill GPIOs and DM542 signal inputs. More components but cleaner.
Go with Option A. It's what most people do with differential-input industrial drivers and 3.3V microcontrollers.

Serial Communication — the Blue Pill USB Problem
This is the most practically painful change. The Arduino communicates with the Pi via USB serial (/dev/ttyACM0). The Blue Pill has a USB port but STM32F103 clone USB is notoriously unreliable — it often doesn't enumerate correctly, especially with cheap Chinese Blue Pills that have imprecise oscillator crystals.
Don't use the Blue Pill USB for serial. Use UART instead.
Blue Pill USART1 is on PA9 (TX) and PA10 (RX). The Raspberry Pi UART is 3.3V logic (GPIO14/GPIO15 on the Pi header). Both are 3.3V — connect directly, no level shifter needed. Just cross TX to RX.
On the Pi side, change /dev/ttyACM0 in the Python script to /dev/ttyAMA0 (or /dev/serial0 depending on Pi model). You'll also need to disable the Pi's serial console if it's enabled (raspi-config → Interface Options → Serial).

What Stays Exactly the Same

The entire Python script logic — drop-off detection, relay control, speed mapping, CSV logging, INA219 I2C reading — does not change at all. That's all on the Pi side.
The serial command protocol (V <speed>, P, H, etc.) — same ASCII commands, same baud rate
AccelStepper library works on STM32duino, so the motion logic ports cleanly


Pin Remapping for Blue Pill
The Arduino used pins 2/3/4/5/6/7. Blue Pill convention uses PA/PB/PC naming. A clean mapping:
FunctionArduino PinBlue Pill PinSTEP2PA0DIR3PA1ENABLE4PA2MS15RemoveMS26RemoveMS37RemoveTX (to Pi)USBPA9RX (from Pi)USBPA10

Development Environment for Blue Pill
Use PlatformIO in VS Code with the STM32duino framework — it handles the Blue Pill board definition cleanly. For uploading, use an ST-Link V2 (cheap clones work fine). In platformio.ini:
ini[env:bluepill_f103c8]
platform = ststm32
board = bluepill_f103c8
framework = arduino
upload_protocol = stlink
monitor_speed = 115200
Your existing .ino code will port with minimal changes — mainly removing the MS pin stuff and updating pin numbers.

Summary of What You Actually Need to Change
WhatChange neededMS1/2/3 pin controlRemove entirely — DM542 uses DIP switchesM <div> commandRemove or stub out with a noteSTEP/DIR/ENABLE pinsRemap to PA0/PA1/PA2Serial portSwitch from USB to USART1 (PA9/PA10)Python /dev/ttyACM0Change to /dev/ttyAMA0 or /dev/serial0DM542 wiringPUL+/DIR+/ENA+ to 5V rail, PUL−/DIR−/ENA− to GPIO (sinking)Microstep configSet DM542 DIP switches physically before running
