import tkinter as tk
from tkinter import scrolledtext
import queue

# Queues (connect these to your backend)
log_queue = queue.Queue()
update_queue = queue.Queue()

# ---------------- ROOT ----------------
root = tk.Tk()
root.title("8-Channel Sensor System")
root.geometry("1200x650")

# ---------------- CONTROL PANEL ----------------
control_frame = tk.Frame(root)
control_frame.pack(fill='x', padx=8, pady=6)

start_btn = tk.Button(control_frame, text="Start", width=12)
stop_btn = tk.Button(control_frame, text="Stop", width=12)
exit_btn = tk.Button(control_frame, text="Exit", width=12)

status_label = tk.Label(control_frame, text="Status: Idle")

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
    
    # 2 rows layout (4 + 4)
    row = i // 4
    col = i % 4
    pf.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

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

# Make grid expand properly
for i in range(4):
    panel_frame.columnconfigure(i, weight=1)
for i in range(2):
    panel_frame.rowconfigure(i, weight=1)

# ---------------- LOG BOX ----------------
log_box = scrolledtext.ScrolledText(root, height=10, state='disabled')
log_box.pack(fill='both', expand=True, padx=8, pady=6)

# ---------------- FUNCTIONS ----------------

def safe_format(val):
    return "--" if val is None else f"{val:.2f}"

def flush_logs():
    try:
        while True:
            msg = log_queue.get_nowait()
            log_box.configure(state='normal')
            log_box.insert('end', msg + '\n')
            log_box.see('end')
            log_box.configure(state='disabled')
    except queue.Empty:
        pass
    root.after(200, flush_logs)

def flush_updates():
    try:
        while True:
            upd = update_queue.get_nowait()

            currents = upd.get('currents', [0]*8)
            resistances = upd.get('resistances', [None]*8)
            delrs = upd.get('del_R', [0]*8)
            relays = upd.get('relays', [0]*8)

            for i in range(8):
                value_labels[i]['current'].config(
                    text=f"Current (mA): {safe_format(currents[i])}"
                )
                value_labels[i]['res'].config(
                    text=f"Resistance (kohm): {safe_format(resistances[i])}"
                )
                value_labels[i]['del'].config(
                    text=f"ΔR (kohm): {safe_format(delrs[i])}"
                )

                if relays[i]:
                    value_labels[i]['relay'].config(
                        text="Relay: ON", bg='lightgreen'
                    )
                else:
                    value_labels[i]['relay'].config(
                        text="Relay: OFF", bg='lightgray'
                    )

    except queue.Empty:
        pass

    root.after(200, flush_updates)

# ---------------- START LOOP ----------------
root.after(200, flush_logs)
root.after(200, flush_updates)

root.mainloop()