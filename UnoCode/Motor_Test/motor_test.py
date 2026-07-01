#!/usr/bin/env python3
"""
Motor Test & Diagnostics — Standalone
======================================
Spins the motor through various test patterns WITHOUT any electrochemical
etching connection. No relay, no current sensor — just the Arduino motor
controller over serial.

Use this to:
  - Verify the motor is responding to commands
  - Check speed accuracy at different velocities
  - Test direction changes and microstepping settings
  - Run preset patterns (ramp, oscillation, step-change) and log results

All Arduino feedback is logged to a CSV in ~/LogFiles/ for later analysis.
"""

import serial
import time
import threading
import csv
import os
from datetime import datetime

# ---------------- CONFIG ----------------
SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200

# --- AUTO FILE NAME ---
LOG_DIR = os.path.expanduser("~/LogFiles")
os.makedirs(LOG_DIR, exist_ok=True)
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_FILE = os.path.join(LOG_DIR, f"motor_test_{timestamp_str}.csv")

# ---------------- SERIAL LISTENER (background) ----------------
serial_log = []  # (timestamp, message)
log_lock = threading.Lock()

def serial_listener(ser):
    """Background thread: reads Arduino serial output and stores it."""
    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if line:
                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    with log_lock:
                        serial_log.append((ts, line))
                    print(f"  ← [{ts}] {line}")
            else:
                time.sleep(0.05)
        except Exception:
            break

# ---------------- HELPERS ----------------
def send_cmd(ser, cmd, label=""):
    """Send a command to Arduino and log it."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    full_cmd = cmd.strip()
    ser.write(f"{full_cmd}\n".encode('utf-8'))
    tag = f" ({label})" if label else ""
    print(f"  → [{ts}] {full_cmd}{tag}")
    with log_lock:
        serial_log.append((ts, f"TX: {full_cmd}{tag}"))

def wait_and_drain(ser, seconds):
    """Wait for a duration, letting the listener thread collect feedback."""
    time.sleep(seconds)

def save_log():
    """Save the accumulated serial log to CSV."""
    with log_lock:
        entries = list(serial_log)
    try:
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Message"])
            for ts, msg in entries:
                writer.writerow([ts, msg])
        print(f"\n  Log saved to: {CSV_FILE} ({len(entries)} entries)")
    except Exception as e:
        print(f"\n  Failed to save log: {e}")

# ========================================================================
#   TEST PATTERNS
# ========================================================================

def test_constant_speed(ser):
    """Run motor at a constant speed for a set duration."""
    print("\n--- CONSTANT SPEED TEST ---")
    speed = float(input("  Enter speed (um/s) [e.g. 20.0]: ") or "20.0")
    duration = float(input("  Enter duration (seconds) [e.g. 10]: ") or "10")
    
    send_cmd(ser, "P", "position before")
    send_cmd(ser, f"V {speed:.2f}", f"constant {speed} um/s")
    wait_and_drain(ser, duration)
    send_cmd(ser, "V 0", "stop")
    wait_and_drain(ser, 0.5)
    send_cmd(ser, "P", "position after")
    wait_and_drain(ser, 0.5)
    print(f"  Done. Ran at {speed} um/s for {duration}s")

def test_speed_ramp(ser):
    """Ramp speed from min to max in steps, hold each briefly."""
    print("\n--- SPEED RAMP TEST ---")
    min_speed = float(input("  Min speed (um/s) [e.g. 1.0]: ") or "1.0")
    max_speed = float(input("  Max speed (um/s) [e.g. 50.0]: ") or "50.0")
    steps = int(input("  Number of speed steps [e.g. 10]: ") or "10")
    hold_time = float(input("  Hold time per step (s) [e.g. 3]: ") or "3")

    if steps < 2:
        steps = 2
    increment = (max_speed - min_speed) / (steps - 1)

    send_cmd(ser, "P", "position before ramp")
    
    print(f"\n  Ramping from {min_speed} to {max_speed} um/s in {steps} steps ({hold_time}s each)...\n")
    
    for i in range(steps):
        speed = min_speed + (increment * i)
        send_cmd(ser, f"V {speed:.2f}", f"ramp step {i+1}/{steps}")
        wait_and_drain(ser, hold_time)
    
    # Ramp back down
    print("  Ramping back down...\n")
    for i in range(steps - 1, -1, -1):
        speed = min_speed + (increment * i)
        send_cmd(ser, f"V {speed:.2f}", f"ramp-down step {steps-i}/{steps}")
        wait_and_drain(ser, hold_time)
    
    send_cmd(ser, "V 0", "stop")
    wait_and_drain(ser, 0.5)
    send_cmd(ser, "P", "position after ramp")
    wait_and_drain(ser, 0.5)
    print("  Ramp test complete.")

def test_step_changes(ser):
    """Instant speed changes to test motor response."""
    print("\n--- STEP CHANGE TEST ---")
    speeds_str = input("  Enter speeds separated by commas (um/s) [e.g. 5,20,2,40,10]: ") or "5,20,2,40,10"
    hold_time = float(input("  Hold time per speed (s) [e.g. 5]: ") or "5")
    
    speeds = [float(s.strip()) for s in speeds_str.split(",")]
    
    send_cmd(ser, "P", "position before")
    print(f"\n  Running step-change test: {speeds} um/s, {hold_time}s each...\n")
    
    for i, speed in enumerate(speeds):
        send_cmd(ser, f"V {speed:.2f}", f"step {i+1}: {speed} um/s")
        wait_and_drain(ser, hold_time)
    
    send_cmd(ser, "V 0", "stop")
    wait_and_drain(ser, 0.5)
    send_cmd(ser, "P", "position after")
    wait_and_drain(ser, 0.5)
    print("  Step change test complete.")

def test_oscillation(ser):
    """Move motor up and down repeatedly to test direction reversals."""
    print("\n--- OSCILLATION TEST ---")
    distance = float(input("  Distance per leg (um) [e.g. 500]: ") or "500")
    speed = float(input("  Speed (um/s) [e.g. 20]: ") or "20")
    cycles = int(input("  Number of cycles [e.g. 5]: ") or "5")
    
    send_cmd(ser, "H", "set home")
    send_cmd(ser, "P", "position before")
    wait_and_drain(ser, 0.5)
    
    print(f"\n  Oscillating {distance} um at {speed} um/s for {cycles} cycles...\n")
    
    for i in range(cycles):
        send_cmd(ser, f"U {distance:.1f} {speed:.1f}", f"cycle {i+1} UP")
        travel_time = distance / speed
        wait_and_drain(ser, travel_time + 1.0)  # +1s buffer for accel/decel
        send_cmd(ser, "P", f"cycle {i+1} top")
        wait_and_drain(ser, 0.5)
        
        send_cmd(ser, f"D {distance:.1f} {speed:.1f}", f"cycle {i+1} DOWN")
        wait_and_drain(ser, travel_time + 1.0)
        send_cmd(ser, "P", f"cycle {i+1} bottom")
        wait_and_drain(ser, 0.5)
    
    send_cmd(ser, "P", "final position")
    wait_and_drain(ser, 0.5)
    print("  Oscillation test complete.")

def test_distance_move(ser):
    """Move a specific distance and report position."""
    print("\n--- DISTANCE MOVE TEST ---")
    direction = input("  Direction [U/D] (default U): ").strip().upper() or "U"
    distance = float(input("  Distance (um) [e.g. 1000]: ") or "1000")
    speed = float(input("  Speed (um/s) [e.g. 20]: ") or "20")
    
    send_cmd(ser, "P", "position before")
    wait_and_drain(ser, 0.5)
    
    send_cmd(ser, f"{direction} {distance:.1f} {speed:.1f}", f"move {direction} {distance}um")
    
    travel_time = distance / speed
    print(f"  Estimated travel time: {travel_time:.1f}s...")
    wait_and_drain(ser, travel_time + 2.0)
    
    send_cmd(ser, "P", "position after")
    wait_and_drain(ser, 0.5)
    print("  Distance move complete.")

def test_microstepping(ser):
    """Test different microstepping modes."""
    print("\n--- MICROSTEPPING TEST ---")
    speed = float(input("  Speed to test at (um/s) [e.g. 10]: ") or "10")
    hold_time = float(input("  Hold time per mode (s) [e.g. 5]: ") or "5")
    modes = [1, 2, 4, 8, 16]
    
    print(f"\n  Testing microstepping modes: {modes} at {speed} um/s, {hold_time}s each...\n")
    
    for mode in modes:
        send_cmd(ser, f"M {mode}", f"set 1/{mode} microstepping")
        wait_and_drain(ser, 0.5)
        send_cmd(ser, f"V {speed:.2f}", f"run at 1/{mode}")
        wait_and_drain(ser, hold_time)
        send_cmd(ser, "V 0", "stop")
        wait_and_drain(ser, 1.0)
    
    # Restore default
    send_cmd(ser, "M 16", "restore 1/16 microstepping")
    wait_and_drain(ser, 0.5)
    print("  Microstepping test complete.")

def manual_mode(ser):
    """Send raw commands to the Arduino interactively."""
    print("\n--- MANUAL COMMAND MODE ---")
    print("  Type Arduino commands directly (U, D, V, S, T, M, P, H, X, R, ?)")
    print("  Type 'exit' to return to the menu.\n")
    
    while True:
        try:
            cmd = input("  cmd> ").strip()
            if cmd.lower() == 'exit':
                break
            if cmd:
                send_cmd(ser, cmd, "manual")
                wait_and_drain(ser, 0.5)
        except EOFError:
            break

# ========================================================================
#   MAIN
# ========================================================================
def main():
    print("=" * 60)
    print("  MOTOR TEST & DIAGNOSTICS")
    print("  No etching. No current sensor. Just the motor.")
    print("=" * 60)
    
    # Connect to Arduino
    print(f"\n  Connecting to Arduino on {SERIAL_PORT}...")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for Arduino reset
        print("  Connected!\n")
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  Check that the Arduino is plugged in and the port is correct.")
        return
    
    # Start background listener
    listener = threading.Thread(target=serial_listener, args=(ser,), daemon=True)
    listener.start()
    
    # Drain any startup messages from Arduino
    wait_and_drain(ser, 1.0)
    
    try:
        while True:
            print("\n" + "─" * 50)
            print("  MOTOR TEST MENU")
            print("─" * 50)
            print("  1. Constant Speed       - Run at fixed speed for N seconds")
            print("  2. Speed Ramp           - Ramp from min→max→min speed")
            print("  3. Step Changes         - Instant speed jumps")
            print("  4. Oscillation          - Move up/down repeatedly")
            print("  5. Distance Move        - Move exact distance")
            print("  6. Microstepping Test   - Compare 1/1, 1/2, 1/4, 1/8, 1/16")
            print("  7. Manual Commands      - Send raw commands to Arduino")
            print("  8. Report Position      - Get current position")
            print("  9. Set Home (Zero)      - Zero the position counter")
            print("  0. Save Log & Exit")
            print("─" * 50)
            
            choice = input("  Select [0-9]: ").strip()
            
            if choice == '1':
                test_constant_speed(ser)
            elif choice == '2':
                test_speed_ramp(ser)
            elif choice == '3':
                test_step_changes(ser)
            elif choice == '4':
                test_oscillation(ser)
            elif choice == '5':
                test_distance_move(ser)
            elif choice == '6':
                test_microstepping(ser)
            elif choice == '7':
                manual_mode(ser)
            elif choice == '8':
                send_cmd(ser, "P", "report position")
                wait_and_drain(ser, 0.5)
            elif choice == '9':
                send_cmd(ser, "H", "set home")
                wait_and_drain(ser, 0.5)
            elif choice == '0':
                break
            else:
                print("  Invalid option, try again.")
    
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
    
    finally:
        # Stop motor and clean up
        print("\n  Stopping motor...")
        send_cmd(ser, "V 0", "emergency stop")
        time.sleep(0.5)
        
        save_log()
        
        ser.close()
        print("  Serial connection closed. Done.")

if __name__ == "__main__":
    main()
