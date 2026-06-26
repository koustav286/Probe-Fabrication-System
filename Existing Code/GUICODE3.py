import tkinter as tk
from tkinter import scrolledtext
from smbus2 import SMBus
import lgpio
import csv
from datetime import datetime

# ---------------- CONFIG ----------------
BUS1_NUM = 1
BUS3_NUM = 3

BUS1_ADDR = [0x40, 0x41, 0x44, 0x45]
BUS3_ADDR = [0x40, 0x41, 0x44, 0x45]

RELAY_PINS = [17, 27, 22, 23, 26, 24, 16, 25]

REG_CALIBRATION = 0x05
REG_CURRENT = 0x04

CALIBRATION_VALUE = 4096
CURRENT_LSB = 0.1

VOLTAGE = 5.0
CC = 2.5
DEL_R_THRESHOLD = 1.5
ZERO_CURRENT_THRESHOLD = 0.3

CSV_FILE = "log_8channel.csv"

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

# ---------------- INIT HARDWARE ----------------
bus1 = SMBus(BUS1_NUM)
bus3 = SMBus(BUS3_NUM)

BUSES = [bus1]*4 + [bus3]*4
ADDRESSES = BUS1_ADDR + BUS3_ADDR

h = lgpio.gpiochip_open(0)

for pin in RELAY_PINS:
    lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_write(h, pin, 0)

for i in range(8):
    write_calibration(BUSES[i], ADDRESSES[i])

# ---------------- GUI ----------------
root = tk.Tk()
root.title("8-Channel Sensor System (REAL)")
root.geometry("1200x650")

running = False
flags = [0]*8
prev_res = [None]*8

# ---------------- CONTROL ----------------
control_frame = tk.Frame(root)
control_frame.pack(fill='x')

status_label = tk.Label(control_frame, text="Status: Idle")

def start():
    global running
    if running:
        return
    running = True
    status_label.config(text="Running")
    update_system()

def stop():
    global running
    running = False
    status_label.config(text="Stopped")

tk.Button(control_frame, text="Start", command=start).pack(side='left')
tk.Button(control_frame, text="Stop", command=stop).pack(side='left')
status_label.pack(side='left', padx=10)

# ---------------- PANELS ----------------
panel_frame = tk.Frame(root)
panel_frame.pack(fill='both', expand=True)

value_labels = []

for i in range(8):
    pf = tk.LabelFrame(panel_frame, text=f"Channel {i+1}")
    pf.grid(row=i//4, column=i%4, padx=5, pady=5)

    lbl_c = tk.Label(pf, text="I: --")
    lbl_r = tk.Label(pf, text="R: --")
    lbl_d = tk.Label(pf, text="ΔR: --")
    lbl_rel = tk.Label(pf, text="Relay OFF", bg='gray')
    lbl_err = tk.Label(pf, text="Err: OK")

    lbl_c.pack()
    lbl_r.pack()
    lbl_d.pack()
    lbl_rel.pack(fill='x')
    lbl_err.pack()

    value_labels.append({
        'c': lbl_c,
        'r': lbl_r,
        'd': lbl_d,
        'relay': lbl_rel,
        'err': lbl_err
    })

# ---------------- LOG ----------------
log_box = scrolledtext.ScrolledText(root, height=8)
log_box.pack(fill='both')

def log(msg):
    log_box.insert('end', msg + "\n")
    log_box.see('end')

# ---------------- MAIN LOOP ----------------
def update_system():
    global running, flags, prev_res

    if not running:
        return

    currents = []
    resistances = []
    delRs = []
    relay_states = [0]*8
    errors = ["OK"]*8

    # ---- READ ----
    for i in range(8):
        try:
            c = read_current(BUSES[i], ADDRESSES[i])
            if c < ZERO_CURRENT_THRESHOLD:
                errors[i] = "NO_CURRENT"
        except:
            c = 0
            errors[i] = "READ_FAIL"

        currents.append(c)

    # ---- RESISTANCE ----
    for i in range(8):
        if currents[i] > 0:
            resistances.append(VOLTAGE / currents[i])
        else:
            resistances.append(None)

    # ---- DELTA R ----
    for i in range(8):
        if resistances[i] and prev_res[i]:
            d = abs(resistances[i] - prev_res[i])
        else:
            d = 0
        delRs.append(d)

    prev_res = resistances.copy()

    # ---- RELAY LOGIC (SAME AS YOUR FILE) ----
    for i in range(8):

        if currents[i] < CC:
            if delRs[i] > DEL_R_THRESHOLD or flags[i] == 1:
                lgpio.gpio_write(h, RELAY_PINS[i], 1)
                relay_states[i] = 1
                flags[i] = 1
            else:
                lgpio.gpio_write(h, RELAY_PINS[i], 0)
                relay_states[i] = 0
        else:
            lgpio.gpio_write(h, RELAY_PINS[i], 0)
            relay_states[i] = 0

    # ---- GUI UPDATE ----
    for i in range(8):
        r = resistances[i]

        value_labels[i]['c'].config(text=f"I: {currents[i]:.2f} mA")
        value_labels[i]['r'].config(text=f"R: {r:.2f}" if r else "R: ∞")
        value_labels[i]['d'].config(text=f"ΔR: {delRs[i]:.2f}")
        value_labels[i]['err'].config(text=f"Err: {errors[i]}")

        if relay_states[i]:
            value_labels[i]['relay'].config(text="ON", bg='green')
        else:
            value_labels[i]['relay'].config(text="OFF", bg='gray')

    log(f"{[round(c,2) for c in currents]}")

    root.after(1000, update_system)

# ---------------- CLEANUP ----------------
def on_close():
    global running
    running = False

    for pin in RELAY_PINS:
        lgpio.gpio_write(h, pin, 0)

    lgpio.gpiochip_close(h)
    bus1.close()
    bus3.close()

    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

# ---------------- START ----------------
root.mainloop()