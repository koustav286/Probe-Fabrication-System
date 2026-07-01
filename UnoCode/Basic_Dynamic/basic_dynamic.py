from smbus2 import SMBus
import lgpio
import time
import serial
from datetime import datetime
import csv
import threading
import os
import board
import adafruit_dht

# ---------------- CONFIG ----------------
BUS_NUM = 1
ADDR = 0x40
RELAY_PIN = 17

REG_CALIBRATION = 0x05
REG_CURRENT = 0x04
CALIBRATION_VALUE = 4096
CURRENT_LSB = 0.1

VOLTAGE = 5.0
CC = 2.5 # Cutoff Current (mA)
ZERO_CURRENT_THRESHOLD = 0.05

# --- Inrush Stabilization (dI/dt based) ---
INRUSH_STABLE_DI_DT = 10.0   # |dI/dt| (mA/s) threshold to consider supply stable
INRUSH_STABLE_COUNT = 3       # Consecutive stable readings required
INRUSH_MIN_WAIT = 1.0         # Minimum seconds to wait before checking stability
INRUSH_MAX_WAIT = 30.0        # Maximum seconds to wait (safety fallback)

MAX_LIFT_SPEED = 100.0 # um/s
MIN_LIFT_SPEED = 10.0  # um/s

SERIAL_PORT = "/dev/ttyACM0" # Fixed to match Arduino
BAUD_RATE = 115200

# --- AUTO FILE NAME ---
LOG_DIR = os.path.expanduser("~/LogFiles")
os.makedirs(LOG_DIR, exist_ok=True)
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_FILE = os.path.join(LOG_DIR, f"log_dynamic_basic_{timestamp_str}.csv")

# ---------------- HELPER ----------------
def swap_bytes(val):
    return ((val & 0xFF) << 8) | (val >> 8)

def write_calibration(bus, addr):
    bus.write_word_data(addr, REG_CALIBRATION, swap_bytes(CALIBRATION_VALUE))

def read_current(bus, addr):
    raw = bus.read_word_data(addr, REG_CURRENT)
    raw = swap_bytes(raw)
    if raw > 32767:
        raw -= 65536
    return raw * CURRENT_LSB

# ---------------- INIT ----------------
try:
    bus = SMBus(BUS_NUM)
    write_calibration(bus, ADDR)
except Exception as e:
    print("I2C Init Error:", e)
    bus = None

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(h, RELAY_PIN)
lgpio.gpio_write(h, RELAY_PIN, 1) # Start with relay cutting power (OFF)

try:
    print(f"Connecting to Arduino on {SERIAL_PORT}...")
    arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2) # Wait for Arduino to reset
    print("Connected to Arduino!")
except Exception as e:
    print(f"Failed to connect to Arduino: {e}")
    arduino = None

print("\n--- EXPERIMENT METADATA ---")
meta_len = input("Enter Length Dipped (mm) [e.g. 5.0]: ")
meta_conc = input("Enter Etchant Concentration (M) [e.g. 2.0]: ")

print("Reading DHT22 sensor on GPIO 27...")
meta_temp, meta_hum = "Unknown", "Unknown"
try:
    dhtDevice = adafruit_dht.DHT22(board.D27, use_pulseio=False)
    for _ in range(5):
        try:
            temp_val = dhtDevice.temperature
            hum_val = dhtDevice.humidity
            if temp_val is not None and hum_val is not None:
                meta_temp, meta_hum = temp_val, hum_val
                break
        except RuntimeError:
            pass
        time.sleep(2.0)
    dhtDevice.exit()
except Exception as e:
    print(f"DHT error: {e}")

if meta_temp == "Unknown":
    print("Failed to auto-read DHT22.")
    meta_temp = input("Enter Temperature (°C) [e.g. 25.50]: ")
    meta_hum = input("Enter Humidity (%) [e.g. 45.00]: ")
else:
    print(f"Auto-Detected Temp: {meta_temp}°C | Humidity: {meta_hum}%")

print("---------------------------\n")

# ---- INIT CSV HEADER ----
try:
    with open(CSV_FILE, 'x', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["# Metadata", "Value"])
        writer.writerow(["# Temperature (C)", meta_temp])
        writer.writerow(["# Humidity (%)", meta_hum])
        writer.writerow(["# Length Dipped (mm)", meta_len])
        writer.writerow(["# Etchant Conc (M)", meta_conc])
        writer.writerow([])
        writer.writerow(["Timestamp", "Current(mA)", "RelayState", "MotorSpeed(um/s)", "Error"])
except FileExistsError:
    pass

print("\n--- BASIC DYNAMIC ETCHING STARTED ---")
lgpio.gpio_write(h, RELAY_PIN, 0) # Turn relay to 0 (Etching ON)
relay_state = 0

print("\nWaiting for power supply to be turned on (Current > 2.5mA)...")
while True:
    c = 0.0
    if bus:
        try:
            c = read_current(bus, ADDR)
        except:
            pass
    print(f"Current: {c:.2f} mA", end='\r')
    if c > CC:
        print(f"\nPower detected at {c:.2f} mA. Waiting for supply to stabilize...")
        break
    time.sleep(0.5)

# --- Inrush Stabilization Loop ---
prev_stab_current = c
prev_stab_time = time.time()
stable_streak = 0
stab_start = time.time()

while True:
    time.sleep(0.5)
    sc = 0.0
    if bus:
        try:
            sc = read_current(bus, ADDR)
        except:
            sc = prev_stab_current

    now = time.time()
    dt = now - prev_stab_time
    elapsed = now - stab_start

    if dt > 0:
        di_dt_stab = abs(sc - prev_stab_current) / dt
    else:
        di_dt_stab = 999.0

    prev_stab_current = sc
    prev_stab_time = now

    print(f"  [Stabilizing] I={sc:.2f} mA | |dI/dt|={di_dt_stab:.1f} mA/s | streak={stable_streak}/{INRUSH_STABLE_COUNT} | elapsed={elapsed:.1f}s")

    if elapsed >= INRUSH_MIN_WAIT and di_dt_stab < INRUSH_STABLE_DI_DT:
        stable_streak += 1
    else:
        stable_streak = 0

    if stable_streak >= INRUSH_STABLE_COUNT:
        print(f"  [Stabilized] Supply stable at {sc:.2f} mA (|dI/dt| < {INRUSH_STABLE_DI_DT} mA/s for {INRUSH_STABLE_COUNT} readings)")
        break

    if elapsed >= INRUSH_MAX_WAIT:
        print(f"  [WARNING] Max stabilization wait ({INRUSH_MAX_WAIT}s) reached. Proceeding at {sc:.2f} mA.")
        break

etch_start_time = time.time()

starting_current = None
running = True

# ---------------- MAIN LOOP ----------------
try:
    while running:
        c = 0.0
        error = "OK"

        if bus:
            try:
                c = read_current(bus, ADDR)
                if c < ZERO_CURRENT_THRESHOLD:
                    error = "NO_CURRENT"
            except Exception:
                error = "READ_FAIL"

        dynamic_speed = 0.0

        # Initialize starting current on first valid reading
        if starting_current is None and c > 5.0:
            starting_current = c
            print(f"Initial Current Detected: {starting_current:.2f} mA")

        # ---- LOGIC ----
        if c < CC or error == "NO_CURRENT":
            # The tip has etched through completely
            print(f"\n[*] DROP-OFF DETECTED! Current: {c:.2f} mA")
            
            # 1. Trigger relay (write 1) immediately to prevent blunting
            lgpio.gpio_write(h, RELAY_PIN, 1)
            relay_state = 1
            
            # 2. Stop motor
            if arduino:
                arduino.write(b"V 0\n")
            
            print("Process finished safely.")
            running = False
        else:
            # We are actively etching. Map current to speed.
            if starting_current:
                # Speed ratio = current / starting_current
                speed_ratio = min(c / starting_current, 1.0)
                dynamic_speed = MIN_LIFT_SPEED + (speed_ratio * (MAX_LIFT_SPEED - MIN_LIFT_SPEED))
            else:
                dynamic_speed = MIN_LIFT_SPEED
                
            if arduino:
                cmd = f"V {dynamic_speed:.2f}\n"
                arduino.write(cmd.encode('utf-8'))

        # ---- LOGGING ----
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] I={c:.2f}mA | Speed={dynamic_speed:.2f}um/s | Err={error}")
        
        try:
            with open(CSV_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), round(c, 3), relay_state, round(dynamic_speed, 2), error])
        except:
            pass

        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    print("Cleaning up...")
    
    if 'etch_start_time' in locals() and etch_start_time is not None:
        etch_end_time = time.time()
        time_taken = etch_end_time - etch_start_time
        try:
            with open(CSV_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([])
                writer.writerow(["# SUMMARY", ""])
                writer.writerow(["# Time Taken (s)", round(time_taken, 2)])
                writer.writerow(["# Time Taken (min)", round(time_taken/60.0, 2)])
        except:
            pass

    lgpio.gpio_write(h, RELAY_PIN, 1) # Ensure power is cut
    lgpio.gpiochip_close(h)
    if bus:
        bus.close()
    if arduino:
        arduino.write(b"V 0\n")
        arduino.close()
