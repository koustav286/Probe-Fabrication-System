from smbus2 import SMBus
import lgpio
import time
import serial
from datetime import datetime
import csv
import collections
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
HISTORY_LEN = 3

CC = 2.5 # Cutoff Current (mA) indicating tip drop-off
OVERCURRENT_MAX = 250.0 # mA threshold for a short circuit
ZERO_CURRENT_THRESHOLD = 0.05

# --- Inrush Stabilization (dI/dt based) ---
INRUSH_STABLE_DI_DT = 10.0   # |dI/dt| (mA/s) threshold to consider supply stable
INRUSH_STABLE_COUNT = 3       # Consecutive stable readings required
INRUSH_MIN_WAIT = 1.0         # Minimum seconds to wait before checking stability
INRUSH_MAX_WAIT = 30.0        # Maximum seconds to wait (safety fallback)

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200

# --- AUTO FILE NAME ---
LOG_DIR = os.path.expanduser("~/LogFiles")
os.makedirs(LOG_DIR, exist_ok=True)
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_FILE = os.path.join(LOG_DIR, f"log_multiphase_{timestamp_str}.csv")

# =========================================================================
#   MULTI-PHASE ETCHING PROFILE
# =========================================================================
# The motor will execute each phase sequentially.
# It will lift the specified distance (um) at the specified speed (um/s).
# If the tip drops off (current < 2.5mA) at ANY point during ANY phase,
# the script will instantly stop the motor and cut the power.
# If it completes the entire array and hasn't dropped, it stops safely.
#
# The liftoff speed is computed dynamically from the wire dip length in mm.
# =========================================================================
BASE_PHASES = [
    {"dist_um": 2000.0, "base_speed_um_s": 3.0},  # Phase 1
    {"dist_um": 2000.0, "base_speed_um_s": 2.5},  # Phase 2
    {"dist_um": 1000.0, "base_speed_um_s": 2.0},  # Phase 3
    {"dist_um": 1000.0, "base_speed_um_s": 1.5},  # Phase 4
    {"dist_um": 1000.0, "base_speed_um_s": 1.0},  # Phase 5
    {"dist_um":  500.0, "base_speed_um_s": 0.5}   # Phase 6
]


def compute_phase_profile(length_mm):
    length_mm = max(0.5, float(length_mm))
    # Longer dipped lengths should lift more slowly; shorter lengths can proceed a bit faster.
    length_factor = 5.0 / length_mm
    length_factor = max(0.4, min(1.2, length_factor))

    phases = []
    for phase in BASE_PHASES:
        phases.append({
            "dist_um": phase["dist_um"],
            "speed_um_s": round(phase["base_speed_um_s"] * length_factor, 2)
        })
    return phases

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

# Create the dynamic phase profile based on dipped length
try:
    meta_len_float = float(meta_len)
except ValueError:
    meta_len_float = 5.0
    print(f"Invalid dipped length '{meta_len}', defaulting to {meta_len_float} mm")

PHASES = compute_phase_profile(meta_len_float)

print(f"Using dynamic liftoff profile for {meta_len_float:.2f} mm dipped length:")
for idx, phase in enumerate(PHASES, start=1):
    print(f"  Phase {idx}: {phase['dist_um']} um @ {phase['speed_um_s']} um/s")

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
        writer.writerow(["Timestamp", "Current(mA)", "Resistance(kOhm)", "dI_dt(mA/s)", "RelayState", "Phase", "PhaseDist(um)", "TotalDist(um)", "MotorSpeed(um/s)", "Error"])
except FileExistsError:
    pass

print("\n--- MULTI-PHASE ETCHING STARTED ---")
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
# Wait for |dI/dt| to drop below threshold for N consecutive readings
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
            sc = prev_stab_current  # Hold last value on read failure

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

running = True
current_phase_index = 0
phase_distance_travelled = 0.0
total_distance_travelled = 0.0
history = collections.deque(maxlen=HISTORY_LEN)

if arduino:
    initial_speed = PHASES[0]["speed_um_s"]
    arduino.write(f"V {initial_speed:.2f}\n".encode('utf-8'))

print(f"\n[*] Entering Phase 1 -> Distance: {PHASES[0]['dist_um']} um @ Speed: {PHASES[0]['speed_um_s']} um/s")
last_time = time.time()

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

        history.append(c)

        if c > ZERO_CURRENT_THRESHOLD:
            r = VOLTAGE / c
        else:
            r = None

        if len(history) >= 2:
            di_dt = (history[-1] - history[0]) / max(1, len(history) - 1)
        else:
            di_dt = 0.0

        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time

        current_speed = PHASES[current_phase_index]["speed_um_s"]

        # ---- LOGIC ----
        if c > OVERCURRENT_MAX:
            print(f"\n[!!!] SHORT CIRCUIT DETECTED! Current spiked to {c:.2f} mA!")
            print("The wire likely touched the counter-electrode ring. Stopping immediately.")
            error = "SHORT_CIRCUIT"
            lgpio.gpio_write(h, RELAY_PIN, 1) # Cut power
            relay_state = 1
            if arduino:
                arduino.write(b"V 0\n")
            running = False

        elif c < CC or error == "NO_CURRENT":
            print(f"\n[*] DROP-OFF DETECTED! Current: {c:.2f} mA")
            
            # Emergency Stop
            lgpio.gpio_write(h, RELAY_PIN, 1) # Cut power
            relay_state = 1
            if arduino:
                arduino.write(b"V 0\n")
            
            print("Process finished safely.")
            running = False
        else:
            # We are actively etching. Update distance tracker.
            dist_step = current_speed * dt
            phase_distance_travelled += dist_step
            total_distance_travelled += dist_step

            # Check if we've completed the current phase
            if phase_distance_travelled >= PHASES[current_phase_index]["dist_um"]:
                current_phase_index += 1
                
                # Did we finish all phases?
                if current_phase_index >= len(PHASES):
                    print(f"\n[!] MAX TRAVEL DISTANCE REACHED. Motor stopped, but keeping current ON until drop-off!")
                    if arduino:
                        arduino.write(b"V 0\n")
                    current_speed = 0.0
                    
                    # We DO NOT set running = False here! 
                    # We just let the loop continue reading current with speed=0.0
                    # so that it will trigger the drop-off block above when it finally breaks!
                else:
                    # Start the next phase!
                    phase_distance_travelled = 0.0
                    current_speed = PHASES[current_phase_index]["speed_um_s"]
                    target_dist = PHASES[current_phase_index]["dist_um"]
                    
                    print(f"\n[*] Entering Phase {current_phase_index + 1} -> Distance: {target_dist} um @ Speed: {current_speed} um/s")
                    if arduino:
                        arduino.write(f"V {current_speed:.2f}\n".encode('utf-8'))

        # ---- LOGGING ----
        timestamp = datetime.now().strftime("%H:%M:%S")
        phase_num = current_phase_index + 1 if running else current_phase_index
        
        r_str = f"{r:5.2f}" if r else "  inf"
        print(f"[{timestamp}] Ph{phase_num} | TotDist: {total_distance_travelled:6.1f}um | I={c:5.2f}mA | R={r_str}kOhm | dI/dt={di_dt:5.2f} | V={current_speed:4.1f} | Err={error}")
        
        try:
            with open(CSV_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                    round(c, 3), 
                    round(r, 3) if r else "",
                    round(di_dt, 3),
                    relay_state, 
                    phase_num, 
                    round(phase_distance_travelled, 2), 
                    round(total_distance_travelled, 2),
                    round(current_speed, 2), 
                    error
                ])
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
