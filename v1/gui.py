import threading
import queue
import sys
import os
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

# ----------------------------
# CORE AUTOMATION LINKAGES
# ----------------------------
try:
    from main import is_cdp_running, launch_edge_with_cdp, ensure_promise_page
except ImportError:
    def is_cdp_running(): return False
    def launch_edge_with_cdp(): return False
    def ensure_promise_page(): pass

try:
    from main import run_automation
except Exception:
    run_automation = None

# ----------------------------
# APP SETTINGS & BRAND COLORS
# ----------------------------
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

PRIMARY_COLOR = "#4c1d95"
HOVER_COLOR = "#1F1481"
BG_COLOR = "#f5f7fb"
CARD_COLOR = "#ffffff"
TEXT_COLOR = "#111827"
BORDER_COLOR = "#d4d4d8"
GREEN_COLOR = "#16a34a"
GREEN_HOVER = "#15803d"
RED_COLOR = "#dc2626"
RED_HOVER = "#b91c1c"

# ----------------------------
# WINDOW FRAME INITIALIZATION
# ----------------------------
app = ctk.CTk()
app.title("AZ Billing Automation")
app.geometry("1200x760")
app.minsize(1000, 650)
app.configure(fg_color=BG_COLOR)

if getattr(sys, "frozen", False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

icon_path = os.path.join(base_path, "azbilling-new-logo.ico")
logo_png_path = os.path.join(base_path, "azbilling-new-logo.png")

if os.path.exists(icon_path):
    app.iconbitmap(icon_path)

# ----------------------------
# STATE SYSTEM DATA STORAGE
# ----------------------------
csv_path = ctk.StringVar()
output_folder = ctk.StringVar()
cdp_connected = False
stop_requested = False
log_queue = queue.Queue()

app.grid_columnconfigure(0, weight=1)
app.grid_rowconfigure(0, weight=1)

# ----------------------------
# LAYOUT STRUCTURE ENGINE
# ----------------------------
main_frame = ctk.CTkFrame(app, fg_color=BG_COLOR)
main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
main_frame.grid_columnconfigure(0, weight=1)
main_frame.grid_rowconfigure(3, weight=1)

# ----------------------------
# SECTION 1: TOP NAVIGATION TOOLBAR
# ----------------------------
toolbar = ctk.CTkFrame(main_frame, fg_color=CARD_COLOR, corner_radius=18, border_width=1, border_color=BORDER_COLOR)
toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 20))
toolbar.grid_columnconfigure(1, weight=1)

img_resource = logo_png_path if os.path.exists(logo_png_path) else icon_path
if os.path.exists(img_resource):
    try:
        logo_image = ctk.CTkImage(light_image=Image.open(img_resource), size=(85, 85))
        logo_label = ctk.CTkLabel(toolbar, image=logo_image, text="")
        logo_label.grid(row=0, column=0, padx=(20, 10), pady=20, sticky="w")
    except Exception:
        pass

title_label = ctk.CTkLabel(toolbar, text="Promise Eligibility Checker", text_color=TEXT_COLOR, font=ctk.CTkFont(family="Segoe UI", size=30, weight="bold"))
title_label.grid(row=0, column=1, columnspan=2, sticky="w")

csv_label = ctk.CTkLabel(toolbar, text="CSV File", text_color=TEXT_COLOR, font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"))
csv_label.grid(row=1, column=0, padx=(20, 10), pady=(10, 5), sticky="w")
csv_entry = ctk.CTkEntry(toolbar, textvariable=csv_path, height=42, border_color=PRIMARY_COLOR)
csv_entry.grid(row=1, column=1, padx=10, pady=(10, 5), sticky="ew")

output_label = ctk.CTkLabel(toolbar, text="Output Folder", text_color=TEXT_COLOR, font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"))
output_label.grid(row=2, column=0, padx=(20, 10), pady=(5, 20), sticky="w")
output_entry = ctk.CTkEntry(toolbar, textvariable=output_folder, height=42, border_color=PRIMARY_COLOR)
output_entry.grid(row=2, column=1, padx=10, pady=(5, 20), sticky="ew")

# ----------------------------
# FILE DIALOG PICKERS
# ----------------------------
def select_csv():
    file_path = filedialog.askopenfilename(title="Select CSV File", filetypes=[("CSV Files", "*.csv")])
    if file_path:
        csv_path.set(file_path)
        log(f"CSV selected: {file_path}")
        
        p_check = os.path.join(os.path.dirname(file_path), f"{os.path.splitext(os.path.basename(file_path))[0]}_progress.csv")
        if os.path.exists(p_check):
            log("ℹ Found an existing session progress log file. System will automatically resume from the last saved milestone.")

def select_output_folder():
    folder = filedialog.askdirectory(title="Select Output Folder")
    if folder:
        output_folder.set(folder)
        log(f"Output folder selected: {folder}")

csv_browse_btn = ctk.CTkButton(toolbar, text="Browse", width=130, height=42, fg_color=PRIMARY_COLOR, hover_color=HOVER_COLOR, text_color="white", text_color_disabled="white", command=select_csv, font=ctk.CTkFont(family="Segoe UI"))
csv_browse_btn.grid(row=1, column=2, padx=(10, 20), pady=(10, 5))

output_browse_btn = ctk.CTkButton(toolbar, text="Browse", width=130, height=42, fg_color=PRIMARY_COLOR, hover_color=HOVER_COLOR, text_color="white", text_color_disabled="white", command=select_output_folder, font=ctk.CTkFont(family="Segoe UI"))
output_browse_btn.grid(row=2, column=2, padx=(10, 20), pady=(5, 20))

# ----------------------------
# SECTION 2: BROWSER SERVICE RUNTIME STATUS
# ----------------------------
connection_frame = ctk.CTkFrame(main_frame, fg_color=CARD_COLOR, corner_radius=18, border_width=1, border_color=BORDER_COLOR)
connection_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
connection_frame.grid_columnconfigure(4, weight=1)

connection_title = ctk.CTkLabel(connection_frame, text="Browser Connection", text_color=TEXT_COLOR, font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"))
connection_title.grid(row=0, column=0, padx=20, pady=(20, 15), sticky="w")

connection_indicator = ctk.CTkLabel(connection_frame, text="🔴 Browser Not Connected", text_color="#dc2626", font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"))
connection_indicator.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

# ----------------------------
# SECTION 3: METRIC PROGRESS SLIDER
# ----------------------------
progress_frame = ctk.CTkFrame(main_frame, fg_color=CARD_COLOR, corner_radius=18, border_width=1, border_color=BORDER_COLOR)
progress_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
progress_frame.grid_columnconfigure(0, weight=1)

progress_title = ctk.CTkLabel(progress_frame, text="Progress", text_color=TEXT_COLOR, font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"))
progress_title.grid(row=0, column=0, padx=20, pady=(12, 6), sticky="w")

progress_bar = ctk.CTkProgressBar(progress_frame, height=16, progress_color=PRIMARY_COLOR)
progress_bar.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
progress_bar.set(0)

progress_label = ctk.CTkLabel(progress_frame, text="0 / 0 Rows Processed", text_color=TEXT_COLOR)
progress_label.grid(row=2, column=0, padx=20, pady=(5, 10), sticky="w")

# ----------------------------
# SECTION 4: REAL-TIME TERMINAL LOG WINDOW
# ----------------------------
log_frame = ctk.CTkFrame(main_frame, fg_color=CARD_COLOR, corner_radius=18, border_width=1, border_color=BORDER_COLOR)
log_frame.grid(row=3, column=0, sticky="nsew")
log_frame.grid_columnconfigure(0, weight=1)
log_frame.grid_rowconfigure(1, weight=1)

log_title = ctk.CTkLabel(log_frame, text="Logs", text_color=TEXT_COLOR, font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"))
log_title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

log_textbox = ctk.CTkTextbox(log_frame, font=("Consolas", 14), fg_color="#f8fafc", text_color="#111827", border_width=1, border_color=PRIMARY_COLOR)
log_textbox.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

# ----------------------------
# THREAD-SAFE CALL FORWARDING LOOPS
# ----------------------------
def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    log_queue.put(formatted)

def update_progress(current, total, member_id="-"):
    progress = current / total if total else 0
    app.after(0, lambda: _safe_ui_progress(progress, current, total))

def _safe_ui_progress(progress, current, total):
    progress_bar.set(progress)
    progress_label.configure(text=f"{current} / {total} Rows Processed")

def process_log_queue():
    while not log_queue.empty():
        message = log_queue.get()
        log_textbox.insert("end", f"{message}\n")
        log_textbox.see("end")
    app.after(100, process_log_queue)

# ----------------------------
# SERVICE ACTION HANDLERS
# ----------------------------
def handle_cdp_connection():
    global cdp_connected
    log("Checking browser connection...")
    cdp_connected = is_cdp_running()

    if cdp_connected:
        start_button.configure(state="normal")
        connection_indicator.configure(text="🟢 Browser Connected", text_color="#16a34a")
        log("✅ Connected to existing browser")
        ensure_promise_page()
        log("✅ Promise portal ready\nPlease log in if needed, then press Start")
        return

    connection_indicator.configure(text="🟡 Launching Browser...", text_color="#ca8a04")
    log("⚠ No automation browser detected")
    
    if launch_edge_with_cdp():
        cdp_connected = True
        start_button.configure(state="normal")
        connection_indicator.configure(text="🟢 Browser Connected", text_color="#16a34a")
        log("✅ Automation browser is ready")
        ensure_promise_page()
        log("✅ Promise portal ready\nPlease log in if needed, then press Start")
    else:
        start_button.configure(state="disabled")
        connection_indicator.configure(text="🔴 Browser Launch Failed", text_color="#dc2626")
        log("❌ Failed to launch new browser")

def start_automation():
    global stop_requested
    if not csv_path.get():
        messagebox.showwarning("Missing CSV", "Please select CSV file")
        return
    if not output_folder.get():
        messagebox.showwarning("Missing Output Folder", "Please select output folder")
        return
    if not cdp_connected:
        messagebox.showwarning("Browser Not Connected", "Please establish browser connection first")
        return

    progress_bar.set(0)
    progress_label.configure(text="0 / 0 Rows Processed")
    stop_requested = False

    start_button.configure(state="disabled", text_color="#ffffff")
    csv_browse_btn.configure(state="disabled")
    output_browse_btn.configure(state="disabled")
    cdp_button.configure(state="disabled", text_color="white")
    stop_button.configure(state="normal", text_color="white")

    log("Starting automation...")
    automation_thread = threading.Thread(target=run_backend_automation, daemon=True)
    automation_thread.start()

def run_backend_automation():
    try:
        if run_automation:
            run_automation(
                csv_path=csv_path.get(),
                output_base_folder=output_folder.get(),
                log_callback=log,
                progress_callback=update_progress,
                stop_check=lambda: stop_requested,
            )
        else:
            log("❌ Error: run_automation function is missing from main.py")
    except Exception as e:
        log(f"ERROR: {e}")
    finally:
        app.after(0, reset_ui_post_automation)

def reset_ui_post_automation():
    start_button.configure(state="normal", text_color="#ffffff")
    csv_browse_btn.configure(state="normal")
    output_browse_btn.configure(state="normal")
    cdp_button.configure(state="normal", text_color="#ffffff")
    stop_button.configure(state="disabled", text_color="#ffffff")
    log("Automation finished")

def stop_automation():
    global stop_requested
    stop_requested = True
    stop_button.configure(state="disabled", text_color="white")
    log("Stop requested...")

# ----------------------------
# INTERACTION BUTTON PACKING
# ----------------------------
cdp_button = ctk.CTkButton(connection_frame, text="Connect Browser", width=170, height=42, fg_color=PRIMARY_COLOR, hover_color=HOVER_COLOR, text_color="white", text_color_disabled="white", command=handle_cdp_connection)
cdp_button.grid(row=1, column=1, padx=10, pady=(0, 20))

start_button = ctk.CTkButton(connection_frame, text="Start", width=170, height=42, fg_color=GREEN_COLOR, hover_color=GREEN_HOVER, text_color="white", text_color_disabled="white", command=start_automation)
start_button.grid(row=1, column=2, padx=10, pady=(0, 20))
start_button.configure(state="disabled")

stop_button = ctk.CTkButton(connection_frame, text="Stop", width=140, height=42, fg_color=RED_COLOR, hover_color=RED_HOVER, text_color="white", text_color_disabled="white", command=stop_automation)
stop_button.grid(row=1, column=3, padx=10, pady=(0, 20))
stop_button.configure(state="disabled")

# ----------------------------
# EVENT EVENT RUNTIME KICKSTART
# ----------------------------
process_log_queue()
app.mainloop()
