from smbus2 import SMBus
import lgpio
import time
import csv
from datetime import datetime
import serial

# ---------------- CONFIG ----------------
BUS1_NUM = 1
BUS3_NUM = 3
BUS1_ADDR = [0x40, 0x41, 0x44, 0x45]
BUS3_ADDR = [0x40, 0x41, 0x44, 0x45]
RELAY_PINS = [26, 24, 16, 25, 17, 27, 22, 23]
REG_CALIBRATION = 0x05
REG_CURRENT = 0x04
CALIBRATION_VALUE = 4096
CURRENT_LSB = 0.1   # mA
VOLTAGE = 5.0
CC = 2.5
DEL_R_THRESHOLD = 1.5
ZERO_CURRENT_THRESHOLD = 0.3
# --- AUTO FILE NAME ---
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_FILE = f"log_8channel_dynamic_{timestamp_str}.csv"

# ---------------- MOTOR CONFIG ----------------
ARDUINO_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200
MAX_LIFT_SPEED = 100.0 # um/s (fastest speed when current is high)
MIN_LIFT_SPEED = 10.0  # um/s (slowest speed when current is low)

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
bus1 = SMBus(BUS1_NUM)
bus3 = SMBus(BUS3_NUM)
BUSES = [bus1]*4 + [bus3]*4
ADDRESSES = BUS1_ADDR + BUS3_ADDR

h = lgpio.gpiochip_open(0)
for pin in RELAY_PINS:
    lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_write(h, pin, 1) # Start with all relays CUTTING power (OFF)

for i in range(8):
    write_calibration(BUSES[i], ADDRESSES[i])

try:
    with open(CSV_FILE, 'x', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp",
            *[f"I{i+1}(mA)" for i in range(8)],
            *[f"R{i+1}(kohm)" for i in range(8)],
            *[f"dR{i+1}" for i in range(8)],
            *[f"Relay{i+1}" for i in range(8)],
            *[f"Error{i+1}" for i in range(8)]
        ])
except FileExistsError:
    pass

print("System Initialized...")

try:
    print(f"Connecting to Arduino on {ARDUINO_PORT}...")
    arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    print("Connected to Arduino!")
except Exception as e:
    print("Failed to connect to Arduino. Continuing without motor control:", e)
    arduino = None

# ---------------- VARIABLES ----------------
flags = [0]*8
prev_res = [None]*8
starting_total_current = None

print("\n--- 8-CHANNEL DYNAMIC ETCHING STARTED ---")
for pin in RELAY_PINS:
    lgpio.gpio_write(h, pin, 0) # Turn all relays ON (Etching ON)

print("\nWaiting for power supply to be turned on (Any Current > 2.5mA)...")
while True:
    any_power = False
    for i in range(8):
        try:
            if read_current(BUSES[i], ADDRESSES[i]) > CC:
                any_power = True
                break
        except:
            pass
    if any_power:
        print("\nPower detected! Starting etch process.")
        break
    time.sleep(0.5)

# ---------------- MAIN LOOP ----------------
try:
    while True:
        currents = []
        resistances = []
        delRs = []
        relay_states = [0]*8
        errors = ["OK"]*8

        # ---- READ CURRENT ----
        for i in range(8):
            try:
                c = read_current(BUSES[i], ADDRESSES[i])
                if c < ZERO_CURRENT_THRESHOLD:
                    errors[i] = "NO_CURRENT"
            except Exception:
                c = 0
                errors[i] = "READ_FAIL"
            currents.append(c)

        # ---- RESISTANCE ----
        for i in range(8):
            c = currents[i]
            if c > 0:
                resistances.append(VOLTAGE / c)
            else:
                resistances.append(None)

        # ---- DELTA R ----
        for i in range(8):
            if resistances[i] is not None and prev_res[i] is not None:
                d = abs(resistances[i] - prev_res[i])
            else:
                d = 0
            delRs.append(d)

        prev_res = resistances.copy()

        # ---- RELAY CONTROL (LATCH LOGIC) ----
        for i in range(8):
            if currents[i] < CC:
                # Trigger if it dropped off, OR if it's completely empty/disconnected (< 0.3mA)
                if delRs[i] > DEL_R_THRESHOLD or flags[i] == 1 or currents[i] < ZERO_CURRENT_THRESHOLD:
                    lgpio.gpio_write(h, RELAY_PINS[i], 1)
                    relay_states[i] = 1
                    flags[i] = 1   # latch ON forever
                else:
                    lgpio.gpio_write(h, RELAY_PINS[i], 0)
                    relay_states[i] = 0
            else:
                lgpio.gpio_write(h, RELAY_PINS[i], 0)
                relay_states[i] = 0

        # ---- MOTOR CONTROL (DYNAMIC SPEED) ----
        total_current = sum([c for c in currents if c > 0])
        
        # Auto-detect the starting current based on how many probes are plugged in!
        if starting_total_current is None and total_current > 0.5:
            starting_total_current = total_current
            
        # Map current to speed. Higher current = faster lift.
        dynamic_speed = MIN_LIFT_SPEED
        if starting_total_current:
            speed_ratio = min(total_current / starting_total_current, 1.0)
            dynamic_speed = MIN_LIFT_SPEED + (speed_ratio * (MAX_LIFT_SPEED - MIN_LIFT_SPEED))
            
        if arduino:
            cmd = f"V {dynamic_speed:.2f}\n"
            arduino.write(cmd.encode('utf-8'))

        # ---- PRINT ----
        print("\n========== STATUS ==========")
        print(f"Total Current: {total_current:.2f} mA -> Motor Speed: {dynamic_speed:.2f} um/s")
        for i in range(8):
            r = resistances[i]
            r_str = f"{r:.2f}" if r is not None else "∞"
            print(f"Ch{i+1} | I={currents[i]:.2f} | R={r_str} | dR={delRs[i]:.2f} | Relay={relay_states[i]} | Err={errors[i]}")

        # ---- CSV LOGGING ----
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(CSV_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp,
                    *[round(c, 3) for c in currents],
                    *[(round(r, 3) if r is not None else "") for r in resistances],
                    *[round(d, 3) for d in delRs],
                    *relay_states,
                    *errors
                ])
        except Exception as e:
            print("CSV WRITE ERROR:", e)

        # ---- STOP CONDITION ----
        if all(flags):
            print("All active probes completed. Stopping.")
            if arduino:
                arduino.write(b"V 0\n") # stop motor
            break

        time.sleep(1)

# ---------------- CLEANUP ----------------
except KeyboardInterrupt:
    print("Stopped by user")

finally:
    print("Cleaning up...")
    for pin in RELAY_PINS:
        lgpio.gpio_write(h, pin, 0)
    lgpio.gpiochip_close(h)
    bus1.close()
    bus3.close()
    if arduino:
        arduino.write(b"V 0\n")
        arduino.close()
    print("System safely stopped.")
