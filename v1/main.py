import csv
import subprocess
import time
import requests
import re
import random
import datetime
import calendar

from typing import Tuple
from pathlib import Path
from playwright.sync_api import sync_playwright

# ----------------------------
# CONFIGURATION CONSTANTS
# ----------------------------
CDP_URL = "http://127.0.0.1:9222"
PROMISE_URL = "https://promise.dhs.pa.gov/portal/provider/Home/tabid/135/Default.aspx"

REQUIRED_COLUMNS = [
    "Contract Name",
    "Medicaid Number",
    "Date of Birth",
    "Last Name",
    "First Name",
]

PAYER_MAPPING = {
    "UPMC": ["UPMC LTSS (CKH)", "CH2F-UPMC COMMUNITY HEALTHCHOICES"],
    "KEYSTONE FIRST": [
        "KEYSTONE FIRST CHC (CKH)",
        "CH2D-KEYSTONE FIRST COMMUNITY HEALTHCHOICES",
    ],
    "PA HEALTH AND WELLNESS": [
        "Centene PA Health Wellness (CKH)",
        "CH2E-PA HEALTH AND WELLNESS COMMUNITY HEALTHCHOICES",
    ],
    "AMERIHEALTH": [
        "AmeriHealth Caritas of PA (CKH)",
        "AMERIHEALTH CARITAS PA COMMUNITY HEALTHCHOICES",
    ],
}

# ----------------------------
# BROWSER CDP MANIPULATION
# ----------------------------
def is_cdp_running():
    try:
        response = requests.get(f"{CDP_URL}/json/version", timeout=2)
        return response.status_code == 200
    except Exception:
        return False

def launch_edge_with_cdp():
    print("🚀 Launching Edge with CDP...")
    edge_cmd = [
        "cmd",
        "/c",
        "start",
        "msedge",
        "--remote-debugging-port=9222",
        "--ignore-certificate-errors",
        "--allow-running-insecure-content",
        "--start-maximized",
        "--user-data-dir=C:\\edge-playwright-profile",
    ]
    subprocess.Popen(edge_cmd)
    for _ in range(20):
        if is_cdp_running():
            print("✅ Edge launched and CDP is running")
            return True
        time.sleep(1)
    return False

def get_or_create_promise_page(context):
    for page in context.pages:
        try:
            current_url = page.url.lower()
            if "promise.dhs.pa.gov" in current_url:
                print(f"🌐 Reusing existing Promise tab: {page.url}")
                page.bring_to_front()
                return page
        except Exception:
            continue

    page = context.new_page()
    print("🆕 Opening Promise portal...")
    page.goto(PROMISE_URL, wait_until="domcontentloaded", timeout=60000)
    return page

def ensure_promise_page():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        get_or_create_promise_page(context)
        return True

# ----------------------------
# FILE HANDLING & IO
# ----------------------------
def validate_csv_columns(input_path):
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return REQUIRED_COLUMNS
        headers = [h.strip() for h in reader.fieldnames]

    return [col for col in REQUIRED_COLUMNS if col not in headers]

def sanitize_filename(value: str) -> str:
    return re.sub(r"[^\w\-_. ]", "_", value)

def prepare_output_folder(input_csv_path: str, timestamp: str, output_base_folder: str) -> Tuple[Path, Path]:
    input_path = Path(input_csv_path)
    output_folder = Path(output_base_folder) / f"{input_path.stem}_{timestamp}"
    output_folder.mkdir(parents=True, exist_ok=True)
    output_file = output_folder / f"{input_path.stem}-{timestamp}.csv"
    return output_folder, output_file

def normalize_payer(contract: str) -> str:
    upper_name = contract.upper().strip()
    for standard_name, variants in PAYER_MAPPING.items():
        for variant in variants:
            if variant.upper().strip() in upper_name:
                return standard_name
    return contract

# ----------------------------
# PORTAL SEARCH AUTOMATION
# ----------------------------
def search(page, member_id_raw: str, dob: str):
    member_id = member_id_raw.strip().zfill(10)
    today = datetime.date.today()
    first_of_month = today.replace(day=1)
    _, last_day = calendar.monthrange(today.year, today.month)
    last_of_month = today.replace(day=last_day)
    
    start_date_str = first_of_month.strftime("%m/%d/%Y")
    end_date_str = last_of_month.strftime("%m/%d/%Y")

    page.fill("#dnn_ctr1732_Eligibility_txtRecipientID2", member_id)
    page.fill("#dnn_ctr1732_Eligibility_txtDob3", dob)
    page.fill("#dnn_ctr1732_Eligibility_txtDosFrom", start_date_str)
    page.fill("#dnn_ctr1732_Eligibility_txtDosTo", end_date_str)

    time.sleep(random.uniform(1, 3))
    page.wait_for_selector("#dnn_ctr1732_Eligibility_btnSearch", state="visible", timeout=60000)
    page.click("#dnn_ctr1732_Eligibility_btnSearch", no_wait_after=True)

    return start_date_str, end_date_str

# ----------------------------
# WEB SCRAPING & RESULTS EXTRACTION
# ----------------------------
def extract_results(page, log_callback=None):
    result_rows = []
    insurance_names = []
    begin_dates = []
    end_dates = []

    try:
        page.wait_for_selector("#dnn_ctr1732_Eligibility_gvSummary tbody tr:not(:first-child)", state="visible", timeout=15000)
        rows = page.query_selector_all("#dnn_ctr1732_Eligibility_gvSummary tbody tr:not(:first-child)")

        for row in rows:
            type_cell = row.query_selector("td:nth-child(1)")
            type_text = type_cell.inner_text().strip() if type_cell else ""

            if "Managed Care" in type_text:
                name_cell = row.query_selector("td:nth-child(2)")
                name = name_cell.inner_text().strip() if name_cell else ""

                if "COMMUNITY HEALTHCHOICES" in name.upper():
                    begin = row.query_selector("td:nth-child(3)").inner_text().strip()
                    end = row.query_selector("td:nth-child(4)").inner_text().strip()

                    insurance_names.append(name)
                    begin_dates.append(begin)
                    end_dates.append(end)
                    result_rows.append({"Insurance Name": name, "Begin Date": begin, "End Date": end})

        return {"result_rows": result_rows, "insurance_names": insurance_names, "begin_dates": begin_dates, "end_dates": end_dates}

    except Exception:
        if log_callback:
            log_callback("ℹ No active Managed Care results found for this member lookup.")
        return {"result_rows": [], "insurance_names": [], "begin_dates": [], "end_dates": [],}

# ----------------------------
# LOGICAL VALIDATION & DISCREPANCIES
# ----------------------------
def check_results(extracted_data, row_contract, start_date_str, end_date_str, page, log_callback=None):
    discrepancy = "No"
    penalty = "No"
    insurance_names = extracted_data["insurance_names"]
    begin_dates = extracted_data["begin_dates"]
    end_dates = extracted_data["end_dates"]
    
    normalized_contract = normalize_payer(row_contract).strip().lower()

    match_found = False
    last_checked_insurance = "No insurance found"

    for insurance_name in insurance_names:
        normalized_insurance = normalize_payer(insurance_name).strip().lower()
        last_checked_insurance = insurance_name
        if normalized_contract == normalized_insurance:
            match_found = True
            break

    # 1. Evaluate Payer Alignments
    if not match_found:
        discrepancy = "Yes"
        if log_callback:
            log_callback(f"⚠️ Payer Mismatch Discrepancy: Contract '{row_contract.strip()}' does not match portal entry '{last_checked_insurance}'")

    # 2. Evaluate Running Window Criteria Ranges
    date_discrepancy = False
    for date in begin_dates:
        if date != start_date_str:
            discrepancy = "Yes"
            date_discrepancy = True

    for date in end_dates:
        if date != end_date_str:
            discrepancy = "Yes"
            date_discrepancy = True

    if date_discrepancy and log_callback:
        log_callback(f"⚠️ Date Range Discrepancy: Portal metrics do not match runtime requirements ({start_date_str} - {end_date_str})")

    # 3. Evaluate Running Exception Penalty Rules
    try:
        if page.get_by_text("Penalty", exact=True).count() > 0:
            penalty = "Yes"
    except Exception:
        pass

    # 4. Process Diagnostic Pipeline
    if discrepancy == "Yes" or penalty == "Yes":
        if log_callback:
            log_callback(f"❌ Row Summary Flagged: Record saved with an explicit Discrepancy or Penalty notice.")
    else:
        if log_callback:
            log_callback(f"🟢 Perfect Match: No discrepancies or penalties found for this member.")

    return discrepancy, penalty

# ----------------------------
# SCREENSHOT UTILITY
# ----------------------------
def take_screenshot(page, output_folder, filename_prefix, log_callback=None):
    try:
        page.wait_for_selector("#dnn_ctr1732_Eligibility_Table6", timeout=5000)
        page.evaluate('() => { document.body.style.zoom = "87%" }')
        table = page.locator("#dnn_ctr1732_Eligibility_Table6")
        table.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        
        box = table.bounding_box()
        if not box:
            if log_callback:
                log_callback("⚠️ Screenshot failed: Unable to compute target table boundary coordinates.")
            return

        filename = f"{filename_prefix}.png"
        screenshot_path = output_folder / filename
        page.screenshot(
            path=str(screenshot_path),
            clip={
                "x": max(0, box["x"] - 50),
                "y": max(0, box["y"] - 100),
                "width": box["width"] + 100,
                "height": box["height"] + 200,
            },
        )
        if log_callback:
            log_callback(f"📸 Screenshot successfully captured and saved: {filename}")
            
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ Screenshot skipped due to exception: {e}")

# ----------------------------
# PROGRESS TRACKING STORAGE
# ----------------------------
def setup_progress_tracking(input_path, output_headers):
    progress_file = input_path.parent / f"{input_path.stem}_progress.csv"
    processed_ids = set()
    file_exists = progress_file.exists()

    if file_exists:
        try:
            with open(progress_file, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    member_id = (row.get("Medicaid Number") or "").strip()
                    if member_id:
                        processed_ids.add(member_id)
            
            with open(progress_file, newline="", encoding="utf-8-sig") as f:
                first_line = f.readline().strip()
                expected_header = ",".join(output_headers)
                if first_line != expected_header and first_line:
                    progress_file.rename(progress_file.with_suffix(".csv.bak"))
                    file_exists = False
                    processed_ids.clear()
        except Exception:
            file_exists = False
            processed_ids.clear()

    mode = "a" if file_exists else "w"
    progress_f = open(progress_file, mode=mode, newline="", encoding="utf-8-sig")
    progress_writer = csv.DictWriter(progress_f, fieldnames=output_headers)
    if not file_exists:
        progress_writer.writeheader()

    return progress_file, processed_ids, progress_writer, progress_f

# ----------------------------
# MAIN ORCHESTRATION ENGINE
# ----------------------------
def run_automation(csv_path, output_base_folder, log_callback=None, progress_callback=None, stop_check=None):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = get_or_create_promise_page(context)
        input_path = Path(csv_path)

        missing_columns = validate_csv_columns(input_path)
        if missing_columns:
            error_message = f"❌ Verification Failure - Missing Required Columns: {', '.join(missing_columns)}"
            if log_callback:
                log_callback(error_message)
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_folder, output_file = prepare_output_folder(input_path, timestamp, output_base_folder)

        with open(input_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            input_headers = reader.fieldnames or []
            input_rows = list(reader)
        
        full_headers = input_headers + ["Insurance Name", "Begin Date", "End Date", "Discrepancy", "Penalty"]
        
        progress_file_raw = input_path.parent / f"{input_path.stem}_progress.csv"
        has_historical_session = progress_file_raw.exists() and progress_file_raw.stat().st_size > 0
        
        progress_file, processed_ids, progress_writer, progress_f = setup_progress_tracking(input_path, full_headers)
        
        f_out = open(output_file, mode="w", newline="", encoding="utf-8-sig")
        writer = csv.DictWriter(f_out, fieldnames=full_headers)
        writer.writeheader()
        
        # ----------------------------
        # HISTORICAL RESUME RESTORE
        # ----------------------------
        if has_historical_session:
            try:
                with open(progress_file_raw, newline="", encoding="utf-8-sig") as pf:
                    progress_reader = csv.DictReader(pf)
                    rows_copied = 0
                    for progress_row in progress_reader:
                        writer.writerow(progress_row)
                        rows_copied += 1
                f_out.flush()
                if log_callback:
                    log_callback(f"📂 Resumed from previous run: {rows_copied} records safely restored.")
            except Exception as e:
                if log_callback:
                    log_callback(f"⚠️ Progress Recovery Warning: Could not backload historical data: {e}")

        try:
            page.wait_for_selector("#dnn_PrimaryMenu_PrimaryMenuRepeater_PrimaryItemHCPHyperlink_2", timeout=30000)
            page.click("#dnn_PrimaryMenu_PrimaryMenuRepeater_PrimaryItemHCPHyperlink_2")
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ Navigation Note: Eligibility Search target skipped or already active: {e}")

        # ----------------------------
        # MAIN RECORD ROW LOOP
        # ----------------------------
        for idx, row in enumerate(input_rows, 1):
            member_id_raw = (row.get("Medicaid Number") or "").strip()
            row_contract = (row.get("Contract Name") or "").strip()
            dob = (row.get("Date of Birth") or "").strip()
            lname = (row.get("Last Name") or "").strip()
            fname = (row.get("First Name") or "").strip()
            fullname = f"{lname}, {fname}".strip(", ")

            if stop_check and stop_check():
                if log_callback:
                    log_callback("🛑 Automation run interrupted by user action request.")
                break

            if member_id_raw in processed_ids:
                if progress_callback:
                    progress_callback(current=idx, total=len(input_rows), member_id=member_id_raw)
                continue

            if log_callback:
                log_callback(f"🔍 Processing row {idx}/{len(input_rows)}: {fullname} ({member_id_raw})")

            try:
                start_date_str, end_date_str = search(page, member_id_raw, dob)
                extracted_data = extract_results(page, log_callback=log_callback)
                result = extracted_data["result_rows"]
                discrepancy, penalty = check_results(extracted_data, row_contract, start_date_str, end_date_str, page, log_callback=log_callback)

                if not result:
                    agg_name, agg_begin, agg_end = "N/A", "N/A", "N/A"
                else:
                    agg_name = "\n".join(f"{i+1}. {d['Insurance Name']}" for i, d in enumerate(result))
                    agg_begin = "\n".join(f"{i+1}. {d['Begin Date']}" for i, d in enumerate(result))
                    agg_end = "\n".join(f"{i+1}. {d['End Date']}" for i, d in enumerate(result))
                    
                    # ----------------------------
                    # SCREENSHOT CAPTURE (EXPLICIT ARGUMENTS)
                    # ----------------------------
                    take_screenshot(
                        page=page, 
                        output_folder=output_folder, 
                        filename_prefix=f"screenshot_{sanitize_filename(fullname)}_{member_id_raw}_{timestamp}", 
                        log_callback=log_callback
                    )

                output_row = dict(row)
                output_row.update({
                    "Insurance Name": agg_name, 
                    "Begin Date": agg_begin, 
                    "End Date": agg_end, 
                    "Discrepancy": discrepancy, 
                    "Penalty": penalty
                })

                writer.writerow(output_row)
                progress_writer.writerow(output_row)
                f_out.flush()
                progress_f.flush()
                
                processed_ids.add(member_id_raw)

                if progress_callback:
                    progress_callback(current=idx, total=len(input_rows), member_id=member_id_raw)

            except Exception as e:
                if log_callback:
                    log_callback(f"❌ Error on row {idx} ({fullname}): {e}")
                continue

        f_out.close()
        progress_f.close()

    if log_callback:
        log_callback(f"✅ Run processing complete. Export located at: {output_file}")
