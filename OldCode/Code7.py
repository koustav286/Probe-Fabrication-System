import threading
import queue
import time
import csv
import traceback
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, messagebox

try:
    import lgpio
except Exception as e:
    lgpio = None
    LGPIO_IMPORT_ERROR = str(e)

try:
    from ina219 import INA219
except Exception as e:
    INA219 = None
    INA219_IMPORT_ERROR = str(e)


CSV_FILE = "log_data_6.csv"
VOLTAGE = 5.0  # Applied Voltage (V)

RELAY_PIN_1 = 17  # BCM GPIO17
RELAY_PIN_2 = 27  # BCM GPIO27
RELAY_PIN_3 = 22  # BCM GPIO22
RELAY_PIN_4 = 23  # BCM GPIO23

CURRENT_THRESHOLD = 0.5  # mA
CC = 2.5  # Critical Current
DEL_R_THRESHOLD = 1.5
SHUNT_OHMS = 0.1

# Create the CSV file with headers if it doesn't exist
try:
    with open(CSV_FILE, 'x', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp",
            "Current1 (mA)", "Current2 (mA)", "Current3 (mA)", "Current4 (mA)",
            "Resistance1 (kohm)", "Resistance2 (kohm)", "Resistance3 (kohm)", "Resistance4 (kohm)",
            "del_R1 (kohm)", "del_R2 (kohm)", "del_R3 (kohm)", "del_R4 (kohm)"
        ])
except FileExistsError:
    pass

# Thread communication
log_queue = queue.Queue()
update_queue = queue.Queue()
stop_event = threading.Event()
worker_thread = None

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_queue.put(f"[{ts}] {msg}")

def safe_format_kohm(val):
    if val is None:
        return "∞"
    try:
        return f"{val:.2f}"
    except Exception:
        return "--"

def monitor_loop():
    if lgpio is None:
        log(f"ERROR: lgpio import failed: {LGPIO_IMPORT_ERROR}")
        return
    if INA219 is None:
        log(f"ERROR: ina219 import failed: {INA219_IMPORT_ERROR}")
        return

    h = None
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, RELAY_PIN_1)
        lgpio.gpio_claim_output(h, RELAY_PIN_2)
        lgpio.gpio_claim_output(h, RELAY_PIN_3)
        lgpio.gpio_claim_output(h, RELAY_PIN_4)

        ina1 = INA219(SHUNT_OHMS, address=0x40, busnum=1)
        ina2 = INA219(SHUNT_OHMS, address=0x41, busnum=1)
        ina3 = INA219(SHUNT_OHMS, address=0x44, busnum=1)
        ina4 = INA219(SHUNT_OHMS, address=0x45, busnum=1)

        ina1.configure()
        ina2.configure()
        ina3.configure()
        ina4.configure()

        flag1 = flag2 = flag3 = flag4 = 0

        log("Monitoring started.")
        while not stop_event.is_set():

            try:
                c1_before = ina1.current()
                c2_before = ina2.current()
                c3_before = ina3.current()
                c4_before = ina4.current()
            except Exception as e:
                log(f"Read error (before): {e}")
                log(traceback.format_exc())

                for _ in range(5):
                    if stop_event.is_set(): break
                    time.sleep(0.1)
                continue

            if all(c <= 0.4 for c in (c1_before, c2_before, c3_before, c4_before)):
                log("Current not flowing on all channels.")
                update_queue.put({
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'currents': (c1_before, c2_before, c3_before, c4_before),
                    'resistances': (None, None, None, None),
                    'del_R': (0,0,0,0),
                    'relays': (0,0,0,0),
                    'flags': (flag1, flag2, flag3, flag4),
                })
                for _ in range(5):
                    if stop_event.is_set(): break
                    time.sleep(0.1)
                continue


            Rp1_k = VOLTAGE / c1_before if c1_before > 0.0 else None
            Rp2_k = VOLTAGE / c2_before if c2_before > 0.0 else None
            Rp3_k = VOLTAGE / c3_before if c3_before > 0.0 else None
            Rp4_k = VOLTAGE / c4_before if c4_before > 0.0 else None

            for _ in range(5):
                if stop_event.is_set(): break
                time.sleep(0.1)
            if stop_event.is_set():
                break

            try:
                c1_after = ina1.current()
                c2_after = ina2.current()
                c3_after = ina3.current()
                c4_after = ina4.current()
            except Exception as e:
                log(f"Read error (after): {e}")
                log(traceback.format_exc())
                for _ in range(5):
                    if stop_event.is_set(): break
                    time.sleep(0.1)
                continue


            Rn1_k = VOLTAGE / c1_after if c1_after > 0.0 else None
            Rn2_k = VOLTAGE / c2_after if c2_after > 0.0 else None
            Rn3_k = VOLTAGE / c3_after if c3_after > 0.0 else None
            Rn4_k = VOLTAGE / c4_after if c4_after > 0.0 else None


            delR1 = abs((Rn1_k or 0) - (Rp1_k or 0))
            delR2 = abs((Rn2_k or 0) - (Rp2_k or 0))
            delR3 = abs((Rn3_k or 0) - (Rp3_k or 0))
            delR4 = abs((Rn4_k or 0) - (Rp4_k or 0))

            log(f"Currents (mA): 1={c1_after:.2f}, 2={c2_after:.2f}, 3={c3_after:.2f}, 4={c4_after:.2f}")
            log(f"Resistances (kohm): R1={safe_format_kohm(Rn1_k)}, R2={safe_format_kohm(Rn2_k)}, R3={safe_format_kohm(Rn3_k)}, R4={safe_format_kohm(Rn4_k)}")
            log(f"ΔR (kohm): {delR1:.2f}, {delR2:.2f}, {delR3:.2f}, {delR4:.2f}")


            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(CSV_FILE, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        timestamp,
                        round(c1_after, 4), round(c2_after, 4), round(c3_after, 4), round(c4_after, 4),
                        (round(Rn1_k, 6) if Rn1_k is not None else ""),
                        (round(Rn2_k, 6) if Rn2_k is not None else ""),
                        (round(Rn3_k, 6) if Rn3_k is not None else ""),
                        (round(Rn4_k, 6) if Rn4_k is not None else ""),
                        round(delR1, 6), round(delR2, 6), round(delR3, 6), round(delR4, 6)
                    ])
            except Exception as e:
                log(f"CSV write error: {e}")
                log(traceback.format_exc())

            relays_state = [0,0,0,0]

            # Channel 1
            if c1_after < CC:
                if delR1 > DEL_R_THRESHOLD or flag1 == 1:
                    lgpio.gpio_write(h, RELAY_PIN_1, 1)
                    relays_state[0] = 1
                    flag1 = 1
                    log("Relay 1: ON (Probe 1 fabrication complete)")
                else:
                    lgpio.gpio_write(h, RELAY_PIN_1, 0)
            else:
                lgpio.gpio_write(h, RELAY_PIN_1, 0)

            # Channel 2
            if c2_after < CC:
                if delR2 > DEL_R_THRESHOLD or flag2 == 1:
                    lgpio.gpio_write(h, RELAY_PIN_2, 1)
                    relays_state[1] = 1
                    flag2 = 1
                    log("Relay 2: ON (Probe 2 fabrication complete)")
                else:
                    lgpio.gpio_write(h, RELAY_PIN_2, 0)
            else:
                lgpio.gpio_write(h, RELAY_PIN_2, 0)

            # Channel 3
            if c3_after < CC:
                if delR3 > DEL_R_THRESHOLD or flag3 == 1:
                    lgpio.gpio_write(h, RELAY_PIN_3, 1)
                    relays_state[2] = 1
                    flag3 = 1
                    log("Relay 3: ON (Probe 3 fabrication complete)")
                else:
                    lgpio.gpio_write(h, RELAY_PIN_3, 0)
            else:
                lgpio.gpio_write(h, RELAY_PIN_3, 0)

            # Channel 4
            if c4_after < CC:
                if delR4 > DEL_R_THRESHOLD or flag4 == 1:
                    lgpio.gpio_write(h, RELAY_PIN_4, 1)
                    relays_state[3] = 1
                    flag4 = 1
                    log("Relay 4: ON (Probe 4 fabrication complete)")
                else:
                    lgpio.gpio_write(h, RELAY_PIN_4, 0)
            else:
                lgpio.gpio_write(h, RELAY_PIN_4, 0)

            update_queue.put({
                'timestamp': timestamp,
                'currents': (c1_after, c2_after, c3_after, c4_after),
                'resistances': (Rn1_k, Rn2_k, Rn3_k, Rn4_k),
                'del_R': (delR1, delR2, delR3, delR4),
                'relays': tuple(relays_state),
                'flags': (flag1, flag2, flag3, flag4),
            })

            if flag1 and flag2 and flag3 and flag4:
                log("All probes fabricated. Ending program.")
                break

            for _ in range(5):
                if stop_event.is_set():
                    break
                time.sleep(0.1)

    except Exception as e:
        log(f"Exception in monitor loop: {e}")
        log(traceback.format_exc())
    finally:
        
        try:
            if h is not None:
                lgpio.gpio_write(h, RELAY_PIN_1, 0)
                lgpio.gpio_write(h, RELAY_PIN_2, 0)
                lgpio.gpio_write(h, RELAY_PIN_3, 0)
                lgpio.gpio_write(h, RELAY_PIN_4, 0)
                lgpio.gpiochip_close(h)
                log("GPIO handle closed and relays set OFF.")
        except Exception as e:
            log(f"Error during cleanup: {e}")
            log(traceback.format_exc())
        log("Monitor thread exiting.")
#GUI
root = tk.Tk()
root.title("Tungsten Probe Sensor Program")
root.geometry("920x560")

control_frame = tk.Frame(root)
control_frame.pack(fill='x', padx=8, pady=6)

start_btn = tk.Button(control_frame, text="Start", width=12)
stop_btn = tk.Button(control_frame, text="Stop", width=12, state='disabled')
exit_btn = tk.Button(control_frame, text="Exit Program", width=12)
status_label = tk.Label(control_frame, text="Status: Idle", anchor='w')
start_btn.pack(side='left', padx=4)
stop_btn.pack(side='left', padx=4)
exit_btn.pack(side='left', padx=4)
status_label.pack(side='left', padx=12)


panel_frame = tk.Frame(root)
panel_frame.pack(fill='x', padx=8, pady=6)

probe_titles = ["Probe 1", "Probe 2", "Probe 3", "Probe 4"]
value_labels = []

for i in range(4):
    pf = tk.LabelFrame(panel_frame, text=probe_titles[i], padx=6, pady=6)
    pf.pack(side='left', expand=True, fill='both', padx=6)
    lbl_current = tk.Label(pf, text="Current (mA): --", font=("Arial", 10))
    lbl_res = tk.Label(pf, text="Resistance (kohm): --", font=("Helvetica", 10))
    lbl_del = tk.Label(pf, text="del-R (kohm): --", font=("Helvetica", 10))
    lbl_relay = tk.Label(pf, text="Relay: OFF", font=("Helvetica", 11, 'bold'), bg='lightgray')
    lbl_current.pack(anchor='w')
    lbl_res.pack(anchor='w')
    lbl_del.pack(anchor='w')
    lbl_relay.pack(anchor='w', pady=(6,0), fill='x')
    value_labels.append({'current': lbl_current, 'res': lbl_res, 'del': lbl_del, 'relay': lbl_relay})


log_box = scrolledtext.ScrolledText(root, height=12, state='disabled', wrap='word')
log_box.pack(fill='both', expand=True, padx=8, pady=6)

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
            currents = upd.get('currents', (0,0,0,0))
            resistances = upd.get('resistances', (None,None,None,None))
            delrs = upd.get('del_R', (0,0,0,0))
            relays = upd.get('relays', (0,0,0,0))
            for i in range(4):
                cur = currents[i]
                res = resistances[i]
                dr = delrs[i]
                try:
                    value_labels[i]['current'].config(text=f"Current (mA): {cur:.2f}")
                except Exception:
                    value_labels[i]['current'].config(text="Current (mA): --")
                value_labels[i]['res'].config(text=f"Resistance (kohm): {safe_format_kohm(res)}")
                try:
                    value_labels[i]['del'].config(text=f"ΔR (kohm): {dr:.2f}")
                except Exception:
                    value_labels[i]['del'].config(text="ΔR (kohm): --")
                if relays[i]:
                    value_labels[i]['relay'].config(text="Relay: ON", bg='lightgreen')
                else:
                    value_labels[i]['relay'].config(text="Relay: OFF", bg='lightgray')
    except queue.Empty:
        pass
    root.after(200, flush_updates)

def on_start():
    global worker_thread
    if lgpio is None or INA219 is None:
        message = "Missing required modules.\n"
        if lgpio is None:
            message += f"lgpio import error: {LGPIO_IMPORT_ERROR}\n"
        if INA219 is None:
            message += f"ina219 import error: {INA219_IMPORT_ERROR}\n"
        message += "Run on Raspberry Pi with required libraries, and run as root if needed (sudo)."
        messagebox.showerror("Missing modules", message)
        return

    start_btn.config(state='disabled')
    stop_btn.config(state='normal')
    status_label.config(text="Status: Running")
    stop_event.clear()
    worker_thread = threading.Thread(target=monitor_loop, daemon=False)
    worker_thread.start()
    log("Start pressed: worker thread launched.")

def on_stop():
    start_btn.config(state='normal')
    stop_btn.config(state='disabled')
    status_label.config(text="Status: Stopping...")
    stop_event.set()
    log("Stop pressed: stopping worker thread...")

    def finish():
        status_label.config(text="Status: Idle")
    root.after(1000, finish)

start_btn.config(command=on_start)
stop_btn.config(command=on_stop)

root.after(200, flush_logs)
root.after(200, flush_updates)

def on_close():
    global worker_thread
    if worker_thread is not None and worker_thread.is_alive():
        if not messagebox.askyesno("Exit", "Monitoring is running. Stop and exit?"):
            return
        stop_event.set()
        log("Closing: waiting for worker thread to finish...")
        worker_thread.join(timeout=4)
    root.destroy()
exit_btn.config(command=on_close)
root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
