from smbus2 import SMBus
import lgpio
import time

# ---------------- CONFIG ----------------
BUS1_NUM = 1
BUS3_NUM = 3

BUS1_ADDR = [0x40, 0x41, 0x44, 0x45]
BUS3_ADDR = [0x40, 0x41, 0x44, 0x45]

RELAY_PINS = [17, 27, 22, 23, 26, 24, 16, 25]

REG_CALIBRATION = 0x05
REG_CURRENT = 0x04

CALIBRATION_VALUE = 4096
CURRENT_LSB = 0.1   # mA

VOLTAGE = 5.0

CC = 2.5
DEL_R_THRESHOLD = 1.5

SHUNT_OHMS = 0.1

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

# Combine buses + addresses
BUSES = [bus1]*4 + [bus3]*4
ADDRESSES = BUS1_ADDR + BUS3_ADDR

# GPIO setup
h = lgpio.gpiochip_open(0)

for pin in RELAY_PINS:
    lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_write(h, pin, 0)  # OFF

# Calibrate sensors
for i in range(8):
    write_calibration(BUSES[i], ADDRESSES[i])

print("System Initialized...")

# ---------------- VARIABLES ----------------
flags = [0]*8
prev_res = [0]*8

# ---------------- MAIN LOOP ----------------
try:
    while True:

        currents = []
        resistances = []
        delRs = []
        relay_states = [0]*8

        # ---- READ ALL CURRENTS ----
        for i in range(8):
            try:
                c = read_current(BUSES[i], ADDRESSES[i])
            except:
                c = 0
            currents.append(c)

        # ---- CALCULATE RESISTANCE ----
        for c in currents:
            if c > 0:
                resistances.append(VOLTAGE / c)
            else:
                resistances.append(None)

        # ---- CALCULATE ?R ----
        for i in range(8):
            if resistances[i] is not None:
                d = abs(resistances[i] - prev_res[i])
            else:
                d = 0
            delRs.append(d)

        prev_res = resistances.copy()

        # ---- RELAY CONTROL ----
        for i in range(8):

            if currents[i] < CC:
                if delRs[i] > DEL_R_THRESHOLD or flags[i] == 1:
                    lgpio.gpio_write(h, RELAY_PINS[i], 1)
                    relay_states[i] = 1
                    flags[i] = 1
                    print(f"Relay {i+1} ON (Probe {i+1} complete)")
                else:
                    lgpio.gpio_write(h, RELAY_PINS[i], 0)
            else:
                lgpio.gpio_write(h, RELAY_PINS[i], 0)

        # ---- PRINT DATA ----
        print("\n========== STATUS ==========")
        for i in range(8):
            r = resistances[i]
            r_str = f"{r:.2f}" if r is not None else "8"

            print(f"Ch{i+1} | I={currents[i]:.2f} mA | R={r_str} kohm | ?R={delRs[i]:.2f} | Relay={relay_states[i]}")

        # ---- STOP CONDITION ----
        if all(flags):
            print("All probes completed. Stopping.")
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

    print("System safely stopped.")
