from smbus2 import SMBus
import lgpio
import time
import csv
from datetime import datetime

# ---------------- CONFIG ----------------
BUS_NUM = 1

POSSIBLE_ADDR = [0x40, 0x41, 0x44, 0x45]

RELAY_PIN = 17

REG_CALIBRATION = 0x05
REG_CURRENT = 0x04

CALIBRATION_VALUE = 4096
CURRENT_LSB = 0.1   # mA

VOLTAGE = 5.0

CC = 2.5
DEL_R_THRESHOLD = 1.5

ZERO_CURRENT_THRESHOLD = 0.3

CSV_FILE = "log_1channel.csv"

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

# ---------------- AUTO DETECT SENSOR ----------------
def detect_sensor(bus):
    for addr in POSSIBLE_ADDR:
        try:
            bus.read_byte(addr)
            print(f"Sensor found at address {hex(addr)}")
            return addr
        except:
            pass
    raise Exception("No INA219 sensor found!")

# ---------------- INIT ----------------
bus = SMBus(BUS_NUM)

DEVICE_ADDR = detect_sensor(bus)

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(h, RELAY_PIN)
lgpio.gpio_write(h, RELAY_PIN, 0)

# Calibrate sensor
write_calibration(bus, DEVICE_ADDR)

# ---------------- CSV SETUP ----------------
try:
    with open(CSV_FILE, 'x', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Current(mA)", "Resistance(kohm)", "dR", "Relay", "Error"])
except FileExistsError:
    pass

print("System Initialized...")

# ---------------- VARIABLES ----------------
flag = 0
prev_res = None

# ---------------- MAIN LOOP ----------------
try:
    while True:

        error = "OK"

        # ---- READ CURRENT ----
        try:
            c = read_current(bus, DEVICE_ADDR)

            if c < ZERO_CURRENT_THRESHOLD:
                error = "NO_CURRENT"

        except Exception:
            c = 0
            error = "READ_FAIL"

        # ---- RESISTANCE ----
        if c > 0:
            r = VOLTAGE / c
        else:
            r = None

        # ---- DELTA R ----
        if r is not None and prev_res is not None:
            dR = abs(r - prev_res)
        else:
            dR = 0

        prev_res = r

        # ---- RELAY CONTROL (LATCH LOGIC) ----
        if c < CC:
            if dR > DEL_R_THRESHOLD or flag == 1:
                lgpio.gpio_write(h, RELAY_PIN, 1)
                relay_state = 1
                flag = 1   # 🔥 stays ON forever
            else:
                lgpio.gpio_write(h, RELAY_PIN, 0)
                relay_state = 0
        else:
            lgpio.gpio_write(h, RELAY_PIN, 0)
            relay_state = 0

        # ---- PRINT ----
        r_str = f"{r:.2f}" if r is not None else "∞"
        print(f"I={c:.2f} mA | R={r_str} | dR={dR:.2f} | Relay={relay_state} | Err={error}")

        # ---- CSV LOGGING ----
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with open(CSV_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp,
                    round(c, 3),
                    round(r, 3) if r is not None else "",
                    round(dR, 3),
                    relay_state,
                    error
                ])
        except Exception as e:
            print("CSV WRITE ERROR:", e)

        time.sleep(1)

# ---------------- CLEANUP ----------------
except KeyboardInterrupt:
    print("Stopped by user")

finally:
    print("Cleaning up...")

    lgpio.gpio_write(h, RELAY_PIN, 0)
    lgpio.gpiochip_close(h)
    bus.close()

    print("System safely stopped.")