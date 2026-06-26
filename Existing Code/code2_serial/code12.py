# pyrefly: ignore [missing-import]
from smbus2 import SMBus
import lgpio
import time
import csv
import serial
import sys
import select
from datetime import datetime

# -------- AUTO FILE NAME --------
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_FILE = f"log_{timestamp}.csv"

# -------- SERIAL --------
arduino = serial.Serial('/dev/ttyACM0', 9600)
time.sleep(2)

# -------- CONFIG --------
BUS_NUM = 1
ADDR = 0x40
RELAY_PIN = 17

REG_CALIBRATION = 0x05
REG_CURRENT = 0x04

CALIBRATION_VALUE = 4096
CURRENT_LSB = 0.1

VOLTAGE = 5.0
CC = 2.5
DEL_R_THRESHOLD = 1.5
ZERO_CURRENT_THRESHOLD = 0.05

# -------- FUNCTIONS --------
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

# -------- INIT --------
bus = SMBus(BUS_NUM)

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(h, RELAY_PIN)
lgpio.gpio_write(h, RELAY_PIN, 0)

write_calibration(bus, ADDR)

# -------- CSV INIT --------
with open(CSV_FILE, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Time","Current","Resistance","dR","Relay","Error"])

print(f"Logging to: {CSV_FILE}")
print("System Started...")
print("-> Press 'y' + Enter for HARD STOP")

flag = 0
prev_res = None
relay_prev = 0
stop_sent = False   # track manual stop

# -------- MAIN LOOP --------
try:
    while True:

        # -- MANUAL HARD STOP --
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            user_input = sys.stdin.readline().strip()
            if user_input.lower() == 'y':
                print("[!] HARD STOP (User)")
                arduino.write(b'X')
                stop_sent = True
                break

        # ---- READ CURRENT ----
        try:
            c = read_current(bus, ADDR)
            error = "OK"
            if c < ZERO_CURRENT_THRESHOLD:
                error = "NO_CURRENT"
        except:
            c = 0
            error = "READ_FAIL"

        # ---- RESISTANCE ----
        if c > ZERO_CURRENT_THRESHOLD:
            r = VOLTAGE / c
        else:
            r = None

        # ---- DELTA R ----
        if r is not None and prev_res is not None:
            d = abs(r - prev_res)
        else:
            d = 0

        prev_res = r

        # ---- RELAY LOGIC ----
        if c < CC:
            # Trigger if Delta R spikes OR if current drops to zero (wire breaks completely)
            if (d > DEL_R_THRESHOLD or c < ZERO_CURRENT_THRESHOLD) and flag == 0:
                lgpio.gpio_write(h, RELAY_PIN, 1)
                relay_state = 1
                flag = 1

                print("[*] Trigger -> Motor START")
                try:
                    arduino.write(b'START\n')
                except:
                    print("Serial error")

            elif flag == 1:
                lgpio.gpio_write(h, RELAY_PIN, 1)
                relay_state = 1
            else:
                lgpio.gpio_write(h, RELAY_PIN, 0)
                relay_state = 0
        else:
            lgpio.gpio_write(h, RELAY_PIN, 0)
            relay_state = 0

        # ---- LOG WHEN RELAY TURNS ON ----
        if relay_prev == 0 and relay_state == 1:
            print("[*] Trigger detected -> Idling so Arduino doesn't reset. Press 'y' + Enter to stop.")

        relay_prev = relay_state

        # ---- PRINT ----
        r_str = f"{r:.2f}" if r else "inf"
        print(f"I={c:.2f} | R={r_str} | dR={d:.2f} | Relay={relay_state} | {error}")

        # ---- CSV LOG ----
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now(),
                round(c,3),
                (round(r,3) if r else ""),
                round(d,3),
                relay_state,
                error
            ])

        time.sleep(1)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    print("Cleaning up...")

    if stop_sent:
        print("[-] Ensuring motor stop")
        try:
            arduino.write(b'X')
        except:
            pass
    else:
        print("[!] Arduino continues running (no stop sent)")

    lgpio.gpio_write(h, RELAY_PIN, 0)
    lgpio.gpiochip_close(h)
    bus.close()

    print("[+] Clean Exit")