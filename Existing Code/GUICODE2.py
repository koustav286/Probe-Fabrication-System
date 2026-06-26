import tkinter as tk
from tkinter import scrolledtext
import random

# ---------------- ROOT ----------------
root = tk.Tk()
root.title("8-Channel Sensor System")
root.geometry("1200x650")

running = False
prev_res = [None]*8
flags = [0]*8

VOLTAGE = 5.0
DEL_R_THRESHOLD = 1.5
CC = 2.5

# ---------------- CONTROL PANEL ----------------
control_frame = tk.Frame(root)
control_frame.pack(fill='x', padx=8, pady=6)

status_label = tk.Label(control_frame, text="Status: Idle")

def start():
    global running
    if running:
        return   # prevent multiple loops
    running = True
    status_label.config(text="Status: Running")
    start_btn.config(state='disabled')
    stop_btn.config(state='normal')
    update_system()

def stop():
    global running
    running = False
    status_label.config(text="Status: Stopped")
    start_btn.config(state='normal')
    stop_btn.config(state='disabled')

def exit_app():
    root.destroy()

start_btn = tk.Button(control_frame, text="Start", width=12, command=start)
stop_btn = tk.Button(control_frame, text="Stop", width=12, command=stop, state='disabled')
exit_btn = tk.Button(control_frame, text="Exit", width=12, command=exit_app)

start_btn.pack(side='left', padx=4)
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

    lbl_current = tk.Label(pf, text="Current (mA): --")
    lbl_res = tk.Label(pf, text="Resistance (kohm): --")
    lbl_del = tk.Label(pf, text="ΔR (kohm): --")
    lbl_relay = tk.Label(pf, text="Relay: OFF", bg='lightgray')

    lbl_current.pack(anchor='w')
    lbl_res.pack(anchor='w')
    lbl_del.pack(anchor='w')
    lbl_relay.pack(fill='x', pady=4)

    value_labels.append({
        'current': lbl_current,
        'res': lbl_res,
        'del': lbl_del,
        'relay': lbl_relay
    })

for i in range(4):
    panel_frame.columnconfigure(i, weight=1)
for i in range(2):
    panel_frame.rowconfigure(i, weight=1)

# ---------------- LOG BOX ----------------
log_box = scrolledtext.ScrolledText(root, height=10, state='disabled')
log_box.pack(fill='both', expand=True, padx=8, pady=6)

def log(msg):
    log_box.config(state='normal')
    log_box.insert('end', msg + "\n")
    log_box.see('end')
    log_box.config(state='disabled')

# ---------------- MAIN LOOP ----------------
def update_system():
    global prev_res, flags, running

    if not running:
        return

    try:
        currents = []
        resistances = []
        delRs = []
        relays = []

        # ---- GENERATE VALUES (SIMULATION) ----
        for i in range(8):
            c = random.uniform(0.1, 3.0)
            currents.append(c)

            r = VOLTAGE / c
            resistances.append(r)

            if prev_res[i] is not None:
                d = abs(r - prev_res[i])
            else:
                d = 0
            delRs.append(d)

        prev_res = resistances.copy()

        # ---- RELAY LOGIC ----
        for i in range(8):
            if currents[i] < CC:
                if delRs[i] > DEL_R_THRESHOLD or flags[i] == 1:
                    relays.append(1)
                    flags[i] = 1
                else:
                    relays.append(0)
            else:
                relays.append(0)

        # ---- UPDATE GUI ----
        for i in range(8):
            value_labels[i]['current'].config(
                text=f"Current (mA): {currents[i]:.2f}"
            )

            value_labels[i]['res'].config(
                text=f"Resistance (kohm): {resistances[i]:.2f}"
            )

            value_labels[i]['del'].config(
                text=f"ΔR (kohm): {delRs[i]:.2f}"
            )

            if relays[i]:
                value_labels[i]['relay'].config(
                    text="Relay: ON", bg='lightgreen'
                )
            else:
                value_labels[i]['relay'].config(
                    text="Relay: OFF", bg='lightgray'
                )

        log(f"Currents: {[round(c,2) for c in currents]}")

    except Exception as e:
        print("ERROR:", e)

    # 🔥 THIS LINE IS CRITICAL (loop continues)
    root.after(1000, update_system)

# ---------------- START ----------------
root.mainloop()