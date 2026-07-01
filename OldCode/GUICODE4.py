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
root.geometry("1200x700")

running = False
flags = [0]*8
prev_res = [None]*8

# ---------------- CONTROL PANEL ----------------
control_frame = tk.Frame(root)
control_frame.pack(fill='x', padx=8, pady=6)

status_label = tk.Label(control_frame, text="Status: Idle")

def start():
    global running, flags, prev_res

    running = True
    flags = [0]*8
    prev_res = [None]*8

    status_label.config(text="Status: Started (Reset)")
    update_system()

def play():
    global running
    if running:
        return

    running = True
    status_label.config(text="Status: Running (Resume)")
    update_system()

def stop():
    global running
    running = False
    status_label.config(text="Status: Paused")

def exit_app():
    global running
    running = False

    for pin in RELAY_PINS:
        lgpio.gpio_write(h, pin, 0)

    lgpio.gpiochip_close(h)
    bus1.close()
    bus3.close()

    root.destroy()

start_btn = tk.Button(control_frame, text="Start", width=12, command=start)
play_btn = tk.Button(control_frame, text="Play", width=12, command=play)
stop_btn = tk.Button(control_frame, text="Stop", width=12, command=stop)
exit_btn = tk.Button(control_frame, text="Exit", width=12, command=exit_app)

start_btn.pack(side='left', padx=4)
play_btn.pack(side='left', padx=4)
stop_btn.pack(side='left', padx=4)
exit_btn.pack(side='left', padx=4)
status_label.pack(side='left', padx=12)

# ---------------- CHANNEL PANELS ----------------
panel_frame = tk.Frame(root)
panel_frame.pack(fill='both', expand=True, padx=8, pady=6)

value_labels = []

for i in range(8):
    pf = tk.LabelFrame(panel_frame, text=f"Channel {i+1}", padx=6, pady=6)
    pf.grid(row=i//4, column=i%4, padx=6, pady=6, sticky="nsew")

    lbl_c = tk.Label(pf, text="Current: --")
    lbl_r = tk.Label(pf, text="Resistance: --")
    lbl_d = tk.Label(pf, text="ΔR: --")
    lbl_relay = tk.Label(pf, text="Relay: OFF", bg='lightgray')
    lbl_err = tk.Label(pf, text="Err: OK")

    lbl_c.pack(anchor='w')
    lbl_r.pack(anchor='w')
    lbl_d.pack(anchor='w')
    lbl_relay.pack(fill='x', pady=3)
    lbl_err.pack(anchor='w')

    value_labels.append({
        'c': lbl_c,
        'r': lbl_r,
        'd': lbl_d,
        'relay': lbl_relay,
        'err': lbl_err
    })

# ---------------- LOG BOX ----------------
log_box = scrolledtext.ScrolledText(root, height=10)
log_box.pack(fill='both', padx=8, pady=6)

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

    # ---- READ CURRENT ----
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
        if resistances[i] is not None and prev_res[i] is not None:
            d = abs(resistances[i] - prev_res[i])
        else:
            d = 0
        delRs.append(d)

    prev_res = resistances.copy()

    # ---- RELAY LOGIC (YOUR ORIGINAL) ----
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

    # ---- UPDATE GUI ----
    for i in range(8):
        r = resistances[i]

        value_labels[i]['c'].config(text=f"Current: {currents[i]:.2f} mA")
        value_labels[i]['r'].config(
            text=f"Resistance: {r:.2f}" if r is not None else "Resistance: ∞"
        )
        value_labels[i]['d'].config(text=f"ΔR: {delRs[i]:.2f}")
        value_labels[i]['err'].config(text=f"Err: {errors[i]}")

        if relay_states[i]:
            value_labels[i]['relay'].config(text="Relay: ON", bg='lightgreen')
        else:
            value_labels[i]['relay'].config(text="Relay: OFF", bg='lightgray')

    log(f"Currents: {[round(c,2) for c in currents]}")

    root.after(1000, update_system)

# ---------------- CLEANUP ----------------
def on_close():
    exit_app()

root.protocol("WM_DELETE_WINDOW", on_close)

# ---------------- START ----------------
root.mainloop()