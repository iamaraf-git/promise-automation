import threading
import queue
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image
from main import is_cdp_running, launch_edge_with_cdp, ensure_promise_page

# ============================================
# OPTIONAL IMPORT FROM main.py
# ============================================

try:
    from main import run_automation
except Exception:
    run_automation = None

# ============================================
# APP SETTINGS
# ============================================

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ============================================
# BRAND COLORS
# ============================================

PRIMARY_PURPLE = "#4c1d95"
HOVER_PURPLE = "#5b21b6"

GOLD = "#c8a96b"

BG_COLOR = "#f5f7fb"

CARD_COLOR = "#ffffff"

TEXT_COLOR = "#111827"

BORDER_COLOR = "#d4d4d8"

# ============================================
# ROOT WINDOW
# ============================================

app = ctk.CTk()

app.title("AZ Billing Automation")

app.geometry("1200x760")

app.minsize(1000, 650)

app.configure(fg_color=BG_COLOR)

# ============================================
# VARIABLES
# ============================================

csv_path = ctk.StringVar()

output_folder = ctk.StringVar()

cdp_connected = False

stop_requested = False

log_queue = queue.Queue()

# ============================================
# GRID
# ============================================

app.grid_columnconfigure(0, weight=1)

app.grid_rowconfigure(0, weight=1)

# ============================================
# MAIN FRAME
# ============================================

main_frame = ctk.CTkFrame(app, fg_color=BG_COLOR)

main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

main_frame.grid_columnconfigure(0, weight=1)

main_frame.grid_rowconfigure(3, weight=1)

# ============================================
# TOOLBAR
# ============================================

toolbar = ctk.CTkFrame(
    main_frame,
    fg_color=CARD_COLOR,
    corner_radius=18,
    border_width=1,
    border_color=BORDER_COLOR,
)

toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 20))

toolbar.grid_columnconfigure(1, weight=1)

# ============================================
# LOGO
# ============================================

logo_image = ctk.CTkImage(
    light_image=Image.open("azbilling-new-logo.png"), size=(85, 85)
)

logo_label = ctk.CTkLabel(toolbar, image=logo_image, text="")

logo_label.grid(row=0, column=0, padx=(20, 10), pady=20, sticky="w")

# ============================================
# TITLE
# ============================================

title_label = ctk.CTkLabel(
    toolbar,
    text="Promise Eligibility Checker",
    text_color=PRIMARY_PURPLE,
    font=ctk.CTkFont(size=30, weight="bold"),
)

title_label.grid(row=0, column=1, columnspan=2, sticky="w")

# ============================================
# CSV SECTION
# ============================================

csv_label = ctk.CTkLabel(
    toolbar,
    text="CSV File",
    text_color=TEXT_COLOR,
    font=ctk.CTkFont(size=15, weight="bold"),
)

csv_label.grid(row=1, column=0, padx=(20, 10), pady=(10, 5), sticky="w")

csv_entry = ctk.CTkEntry(
    toolbar, textvariable=csv_path, height=42, border_color=PRIMARY_PURPLE
)

csv_entry.grid(row=1, column=1, padx=10, pady=(10, 5), sticky="ew")

# ============================================
# OUTPUT SECTION
# ============================================

output_label = ctk.CTkLabel(
    toolbar,
    text="Output Folder",
    text_color=TEXT_COLOR,
    font=ctk.CTkFont(size=15, weight="bold"),
)

output_label.grid(row=2, column=0, padx=(20, 10), pady=(5, 20), sticky="w")

output_entry = ctk.CTkEntry(
    toolbar, textvariable=output_folder, height=42, border_color=PRIMARY_PURPLE
)

output_entry.grid(row=2, column=1, padx=10, pady=(5, 20), sticky="ew")

# ============================================
# FILE FUNCTIONS
# ============================================


def select_csv():

    file_path = filedialog.askopenfilename(
        title="Select CSV File", filetypes=[("CSV Files", "*.csv")]
    )

    if file_path:
        csv_path.set(file_path)
        log(f"CSV selected: {file_path}")


def select_output_folder():

    folder = filedialog.askdirectory(title="Select Output Folder")

    if folder:
        output_folder.set(folder)
        log(f"Output folder selected: {folder}")


# ============================================
# BROWSE BUTTONS
# ============================================

csv_browse_btn = ctk.CTkButton(
    toolbar,
    text="Browse",
    width=130,
    height=42,
    fg_color=PRIMARY_PURPLE,
    hover_color=HOVER_PURPLE,
    command=select_csv,
)

csv_browse_btn.grid(row=1, column=2, padx=(10, 20), pady=(10, 5))

output_browse_btn = ctk.CTkButton(
    toolbar,
    text="Browse",
    width=130,
    height=42,
    fg_color=PRIMARY_PURPLE,
    hover_color=HOVER_PURPLE,
    command=select_output_folder,
)

output_browse_btn.grid(row=2, column=2, padx=(10, 20), pady=(5, 20))

# ============================================
# CONNECTION FRAME
# ============================================

connection_frame = ctk.CTkFrame(
    main_frame,
    fg_color=CARD_COLOR,
    corner_radius=18,
    border_width=1,
    border_color=BORDER_COLOR,
)

connection_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))

connection_frame.grid_columnconfigure(4, weight=1)

connection_title = ctk.CTkLabel(
    connection_frame,
    text="Browser Connection",
    text_color=PRIMARY_PURPLE,
    font=ctk.CTkFont(size=22, weight="bold"),
)

connection_title.grid(row=0, column=0, padx=20, pady=(20, 15), sticky="w")

connection_indicator = ctk.CTkLabel(
    connection_frame,
    text="🔴 Not Connected",
    text_color="#dc2626",
    font=ctk.CTkFont(size=15, weight="bold"),
)

connection_indicator.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

# ============================================
# LOGGING
# ============================================


def log(message):

    timestamp = datetime.now().strftime("%H:%M:%S")

    formatted = f"[{timestamp}] {message}"

    log_queue.put(formatted)


# ============================================
# CDP CONNECTION
# ============================================


def handle_cdp_connection():

    global cdp_connected

    log("Checking CDP browser status...")

    cdp_connected = is_cdp_running()

    # ----------------------------------------
    # IF ALREADY CONNECTED
    # ----------------------------------------

    if cdp_connected:

        start_button.configure(state="normal")
        connection_indicator.configure(text="🟢 Browser Ready", text_color="#16a34a")

        log("✅ Existing CDP browser detected")

        ensure_promise_page()

        log("✅ Promise portal ready")

        log("Please log in if needed, then press Start")

        return

    # ----------------------------------------
    # IF NOT CONNECTED
    # ----------------------------------------

    connection_indicator.configure(text="🟡 Launching Browser...", text_color="#ca8a04")

    log("⚠ No CDP browser detected")

    success = launch_edge_with_cdp()

    # ----------------------------------------
    # SUCCESS
    # ----------------------------------------

    if success:

        cdp_connected = True
        start_button.configure(state="normal")
        connection_indicator.configure(
            text="🟢 CDP Browser Ready", text_color="#16a34a"
        )

        log("✅ Edge launched with CDP")

        ensure_promise_page()

        log("✅ Promise portal ready")

        log("Please log in if needed, then press Start")

    # ----------------------------------------
    # FAILED
    # ----------------------------------------

    else:

        start_button.configure(state="disabled")
        connection_indicator.configure(
            text="🔴 CDP Launch Failed", text_color="#dc2626"
        )

        log("❌ Failed to launch CDP browser")


def start_automation():

    progress_bar.set(0)

    progress_label.configure(text="0 / 0 Rows Processed")
    global stop_requested

    if not csv_path.get():

        messagebox.showwarning("Missing CSV", "Please select CSV file")

        return

    if not output_folder.get():

        messagebox.showwarning("Missing Output Folder", "Please select output folder")

        return

    if not cdp_connected:

        messagebox.showwarning("CDP Not Ready", "Please establish CDP connection first")

        return

    stop_requested = False

    start_button.configure(state="disabled")

    csv_browse_btn.configure(state="disabled")

    output_browse_btn.configure(state="disabled")

    cdp_button.configure(state="disabled")

    stop_button.configure(state="normal")

    log("Starting automation...")

    automation_thread = threading.Thread(target=run_backend_automation, daemon=True)

    automation_thread.start()


def run_backend_automation():

    try:

        run_automation(
            csv_path=csv_path.get(),
            output_base_folder=output_folder.get(),
            log_callback=log,
            progress_callback=update_progress,
            stop_check=lambda: stop_requested,
        )

    except Exception as e:

        log(f"ERROR: {e}")

    finally:

        app.after(0, lambda: start_button.configure(state="normal"))

        app.after(0, lambda: csv_browse_btn.configure(state="normal"))

        app.after(0, lambda: output_browse_btn.configure(state="normal"))

        app.after(0, lambda: cdp_button.configure(state="normal"))

        app.after(0, lambda: stop_button.configure(state="disabled"))

        log("Automation finished")


def stop_automation():

    global stop_requested

    stop_requested = True

    stop_button.configure(state="disabled")
    log("Stop requested...")


# ============================================
# BUTTONS
# ============================================

cdp_button = ctk.CTkButton(
    connection_frame,
    text="Browser Connection",
    width=170,
    height=42,
    fg_color=PRIMARY_PURPLE,
    hover_color=HOVER_PURPLE,
    command=handle_cdp_connection,
)

cdp_button.grid(row=1, column=1, padx=10, pady=(0, 20))

# ============================================
# START BUTTON
# ============================================

start_button = ctk.CTkButton(
    connection_frame,
    text="Start",
    width=170,
    height=42,
    fg_color=PRIMARY_PURPLE,
    hover_color=HOVER_PURPLE,
    command=start_automation,
)

start_button.grid(row=1, column=2, padx=10, pady=(0, 20))
start_button.configure(state="disabled")

# ============================================
# STOP BUTTON
# ============================================

stop_button = ctk.CTkButton(
    connection_frame,
    text="Stop",
    width=140,
    height=42,
    fg_color="#dc2626",
    hover_color="#b91c1c",
    command=stop_automation,
)

stop_button.grid(row=1, column=3, padx=10, pady=(0, 20))
stop_button.configure(state="disabled")

# ============================================
# PROGRESS FRAME
# ============================================

progress_frame = ctk.CTkFrame(
    main_frame,
    fg_color=CARD_COLOR,
    corner_radius=18,
    border_width=1,
    border_color=BORDER_COLOR,
)

progress_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))

progress_frame.grid_columnconfigure(0, weight=1)

progress_title = ctk.CTkLabel(
    progress_frame,
    text="Progress",
    text_color=PRIMARY_PURPLE,
    font=ctk.CTkFont(size=22, weight="bold"),
)

progress_title.grid(row=0, column=0, padx=20, pady=(12, 6), sticky="w")

progress_bar = ctk.CTkProgressBar(
    progress_frame, height=16, progress_color=PRIMARY_PURPLE
)

progress_bar.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

progress_bar.set(0)

progress_label = ctk.CTkLabel(
    progress_frame, text="0 / 0 Rows Processed", text_color=TEXT_COLOR
)

progress_label.grid(row=2, column=0, padx=20, pady=(5, 10), sticky="w")

# ============================================
# LOG FRAME
# ============================================

log_frame = ctk.CTkFrame(
    main_frame,
    fg_color=CARD_COLOR,
    corner_radius=18,
    border_width=1,
    border_color=BORDER_COLOR,
)

log_frame.grid(row=3, column=0, sticky="nsew")

log_frame.grid_columnconfigure(0, weight=1)

log_frame.grid_rowconfigure(1, weight=1)

log_title = ctk.CTkLabel(
    log_frame,
    text="Logs",
    text_color=PRIMARY_PURPLE,
    font=ctk.CTkFont(size=22, weight="bold"),
)

log_title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

log_textbox = ctk.CTkTextbox(
    log_frame,
    font=("Consolas", 13),
    fg_color="#ffffff",
    text_color="#111827",
    border_width=1,
    border_color=PRIMARY_PURPLE,
)

log_textbox.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")


def update_progress(current, total, member_id="-"):

    progress = current / total if total else 0

    progress_bar.set(progress)

    progress_label.configure(text=f"{current} / {total} Rows Processed")


# ============================================
# PROCESS LOG QUEUE
# ============================================


def process_log_queue():

    while not log_queue.empty():

        message = log_queue.get()

        log_textbox.insert("end", f"{message}\n")

        log_textbox.see("end")

    app.after(100, process_log_queue)


# ============================================
# MAIN LOOP
# ============================================

process_log_queue()

app.mainloop()
