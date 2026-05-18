import csv
from multiprocessing import context
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

CDP_URL = "http://127.0.0.1:9222"

PROMISE_URL = (
    "https://promise.dhs.pa.gov/" "portal/provider/Home/tabid/135/Default.aspx"
)

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


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^\w\-_. ]", "_", value)


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

    # ----------------------------------------
    # CHECK EXISTING TABS
    # ----------------------------------------

    for page in context.pages:

        try:

            current_url = page.url.lower()

            if "promise.dhs.pa.gov" in current_url:

                print(f"🌐 Reusing existing Promise tab: " f"{page.url}")

                page.bring_to_front()

                return page

        except Exception:
            continue

    # ----------------------------------------
    # CREATE NEW TAB
    # ----------------------------------------

    page = context.new_page()

    print("🆕 Opening Promise portal...")

    page.goto(PROMISE_URL, wait_until="domcontentloaded", timeout=60000)

    return page


def prepare_output_folder(
    input_csv_path: str, timestamp: str, output_base_folder: str
) -> Tuple[Path, Path]:
    """
    Create an output folder based on the input CSV filename plus current timestamp.

    Returns:
        output_folder (Path): The path to the created output folder.
        output_file (Path): The path to the output CSV file inside the folder.
    """
    input_path = Path(input_csv_path)
    input_stem = input_path.stem
    output_folder_name = f"{input_stem}_{timestamp}"
    output_folder = Path(output_base_folder) / output_folder_name
    output_folder.mkdir(parents=True, exist_ok=True)
    output_file = output_folder / f"{input_stem}-{timestamp}.csv"
    return output_folder, output_file


def ensure_promise_page():

    with sync_playwright() as p:

        browser = p.chromium.connect_over_cdp(CDP_URL)

        context = browser.contexts[0] if browser.contexts else browser.new_context()

        page = get_or_create_promise_page(context)

        page.bring_to_front()

        return True


def prepare_csv_reader_writer(
    input_path: Path, output_file: Path, progress_file: Path = None
):

    # ----------------------------------------
    # READ INPUT CSV
    # ----------------------------------------

    with open(input_path, newline="", encoding="utf-8") as f:

        input_rows = list(csv.DictReader(f))

        input_headers = list(input_rows[0].keys()) if input_rows else []

    # ----------------------------------------
    # OUTPUT HEADERS
    # ----------------------------------------

    output_headers = input_headers + [
        "Insurance Name",
        "Begin Date",
        "End Date",
        "Discrepancy",
        "Penalty",
    ]

    # ----------------------------------------
    # CREATE OUTPUT FILE
    # ----------------------------------------

    f_out = open(output_file, mode="w", newline="", encoding="utf-8")

    writer = csv.DictWriter(f_out, fieldnames=output_headers)

    writer.writeheader()

    # ----------------------------------------
    # COPY EXISTING PROGRESS
    # ----------------------------------------

    if progress_file and progress_file.exists():

        with open(progress_file, newline="", encoding="utf-8") as pf:

            progress_reader = csv.DictReader(pf)

            for row in progress_reader:

                writer.writerow(row)

        f_out.flush()

    return input_rows, writer, f_out


def normalize_payer(contract: str) -> str:

    upper_name = contract.upper()

    for standard_name, variants in PAYER_MAPPING.items():

        for variant in variants:

            if variant.upper() in upper_name:
                return standard_name

    return contract


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

    delay = random.uniform(1, 5)  # random delay between 1 and 5 seconds
    time.sleep(delay)
    page.wait_for_selector(
        "#dnn_ctr1732_Eligibility_btnSearch", state="visible", timeout=60000
    )  # wait up to 60s
    page.click("#dnn_ctr1732_Eligibility_btnSearch", no_wait_after=True)

    return start_date_str, end_date_str


def extract_results(page, row_contract: str, start_date_str: str, end_date_str: str):
    result_rows = []
    insurance_names = []
    begin_dates = []
    end_dates = []
    discrepancy = None
    penalty = None
    try:
        page.wait_for_selector(
            "#dnn_ctr1732_Eligibility_gvSummary tbody tr:not(:first-child)",
            state="visible",
            timeout=60000,
        )
        rows = page.query_selector_all(
            "#dnn_ctr1732_Eligibility_gvSummary tbody tr:not(:first-child)"
        )
        for row in rows:
            type_cell = row.query_selector("td:nth-child(1)")
            type_text = type_cell.inner_text().strip() if type_cell else ""

            if "Managed Care" in type_text:
                name_cell = row.query_selector("td:nth-child(2)")
                name = name_cell.inner_text().strip() if name_cell else ""

                if "COMMUNITY HEALTHCHOICES" in name_cell.inner_text().strip().upper():
                    begin_cell = row.query_selector("td:nth-child(3)")
                    end_cell = row.query_selector("td:nth-child(4)")
                    name = name_cell.inner_text().strip() if name_cell else ""
                    begin = begin_cell.inner_text().strip() if begin_cell else ""
                    end = end_cell.inner_text().strip() if end_cell else ""

                    insurance_names.append(name)
                    begin_dates.append(begin)
                    end_dates.append(end)
                    result_rows.append(
                        {"Insurance Name": name, "Begin Date": begin, "End Date": end}
                    )

        # Determine discrepancy by comparing (MCO) normalized contract name with insurance names, and also checking date ranges
        discrepancy = "No"
        contract = row_contract

        normalized_contract = normalize_payer(contract)
        match_found = False

        for insurance_name in insurance_names:
            normalized_insurance = normalize_payer(insurance_name)
            print(
                f"Comparing normalized contract '{normalized_contract}' with insurance '{normalized_insurance}'"
            )
            if normalized_contract == normalized_insurance:
                match_found = True
                break

        if match_found == False:
            discrepancy = "Yes"

        for date in begin_dates:
            if date != start_date_str:
                discrepancy = "Yes"

        for date in end_dates:
            if date != end_date_str:
                discrepancy = "Yes"

        # Determine penalty
        penalty = "No"
        penalty_count = page.get_by_text("Penalty", exact=True).count()
        if penalty_count > 0:
            penalty = "Yes"
    except Exception as e:
        print(f"⚠️ No Results Found: {e}")
    return result_rows, discrepancy, penalty


def take_screenshot(page, output_folder, filename_prefix):

    page.wait_for_selector("#dnn_ctr1732_Eligibility_Table6")

    page.evaluate("""
                () => {
                    document.body.style.zoom = "90%"
                }
            """)
    try:
        table = page.locator("#dnn_ctr1732_Eligibility_Table6")

        # Scroll element into view
        table.scroll_into_view_if_needed()

        # Wait for portal layout to settle
        page.wait_for_timeout(1000)

        # Get element position and size
        box = table.bounding_box()

        if not box:
            print("⚠️ Could not get bounding box.")
            return

        # Extra surrounding space
        padding_left = 200
        padding_right = 200

        padding_top = 500
        padding_bottom = 500

        screenshot_path = output_folder / f"{filename_prefix}.png"

        page.screenshot(
            path=str(screenshot_path),
            clip={
                "x": max(0, box["x"] - padding_left),
                "y": max(0, box["y"] - padding_top),
                "width": (box["width"] + padding_left + padding_right),
                "height": (box["height"] + padding_top + padding_bottom),
            },
        )

        print(f"🖼️ Screenshot saved: {screenshot_path}")

    except Exception as e:
        print(f"⚠️ Error taking screenshot: {e}")


def setup_progress_tracking(input_path, output_headers):

    # ----------------------------------------
    # PROGRESS FILE PATH
    # ----------------------------------------

    progress_file = input_path.parent / f"{input_path.stem}_progress.csv"

    # ----------------------------------------
    # TRACK COMPLETED MEMBERS
    # ----------------------------------------

    processed_ids = set()

    # ----------------------------------------
    # CHECK IF FILE EXISTS
    # ----------------------------------------

    file_exists = progress_file.exists()

    # ----------------------------------------
    # OPEN PROGRESS FILE
    # ----------------------------------------

    progress_f = open(progress_file, mode="a", newline="", encoding="utf-8")

    progress_writer = csv.DictWriter(progress_f, fieldnames=output_headers)

    # ----------------------------------------
    # WRITE HEADER IF NEW FILE
    # ----------------------------------------

    if not file_exists:

        progress_writer.writeheader()

    # ----------------------------------------
    # LOAD EXISTING PROCESSED IDS
    # ----------------------------------------

    else:

        with open(progress_file, newline="", encoding="utf-8") as f:

            reader = csv.DictReader(f)

            for row in reader:

                member_id = row.get("Medicaid Number", "").strip()

                if member_id:

                    processed_ids.add(member_id)

    # ----------------------------------------
    # RETURN EVERYTHING
    # ----------------------------------------

    return (
        progress_file,
        processed_ids,
        progress_writer,
        progress_f,
    )


def run_automation(
    csv_path,
    output_base_folder,
    log_callback=None,
    progress_callback=None,
    stop_check=None,
):

    with sync_playwright() as p:

        browser = p.chromium.connect_over_cdp(CDP_URL)

        context = browser.contexts[0] if browser.contexts else browser.new_context()

        page = get_or_create_promise_page(context)

        input_path = Path(csv_path)

        # ----------------------------------------
        # OUTPUT SETUP
        # ----------------------------------------

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        output_folder, output_file = prepare_output_folder(
            input_path, timestamp, output_base_folder
        )

        with open(input_path, newline="", encoding="utf-8") as f:

            input_headers = list(csv.DictReader(f).fieldnames)
        (
            progress_file,
            processed_ids,
            progress_writer,
            progress_f,
        ) = setup_progress_tracking(
            input_path,
            input_headers
            + [
                "Insurance Name",
                "Begin Date",
                "End Date",
                "Discrepancy",
                "Penalty",
            ],
        )

        input_rows, writer, f_out = prepare_csv_reader_writer(
            input_path, output_file, progress_file
        )

        # ----------------------------------------
        # NAVIGATE TO ELIGIBILITY PAGE
        # ----------------------------------------

        try:

            page.wait_for_selector(
                "#dnn_PrimaryMenu_" "PrimaryMenuRepeater_" "PrimaryItemHCPHyperlink_2",
                timeout=60000,
            )

            page.click(
                "#dnn_PrimaryMenu_" "PrimaryMenuRepeater_" "PrimaryItemHCPHyperlink_2"
            )

        except Exception as e:

            if log_callback:

                log_callback("❌ Error navigating to " f"Eligibility Search page: {e}")

        # ----------------------------------------
        # MAIN LOOP
        # ----------------------------------------

        for idx, row in enumerate(input_rows, 1):

            member_id_raw = "UNKNOWN"

            try:

                # --------------------------------
                # STOP CHECK
                # --------------------------------

                if stop_check and stop_check():

                    if log_callback:

                        log_callback("Automation stopped by user")

                    break

                # --------------------------------
                # READ CSV DATA
                # --------------------------------

                row_contract = row.get("Contract Name", "").strip()

                member_id_raw = row.get("Medicaid Number", "").strip()

                # --------------------------------
                # SKIP COMPLETED ROWS
                # --------------------------------

                if member_id_raw in processed_ids:

                    if progress_callback:

                        progress_callback(
                            current=idx, total=len(input_rows), member_id=member_id_raw
                        )

                    if log_callback:

                        log_callback("⏩ Skipping completed row: " f"{fullname} ({member_id_raw})")

                    continue

                dob = row.get("Date of Birth", "").strip()

                lname = row.get("Last Name", "").strip()

                fname = row.get("First Name", "").strip()

                fullname = f"{lname}, {fname}"

                sanitized_name = sanitize_filename(fullname)

                # --------------------------------
                # SEARCH
                # --------------------------------

                start_date_str, end_date_str = search(page, member_id_raw, dob)

                # --------------------------------
                # EXTRACT RESULTS
                # --------------------------------

                (
                    result,
                    discrepancy,
                    penalty,
                ) = extract_results(page, row_contract, start_date_str, end_date_str)

                # --------------------------------
                # FORMAT RESULTS
                # --------------------------------

                if not result:

                    agg_name = "N/A"

                    agg_begin = "N/A"

                    agg_end = "N/A"

                else:

                    agg_name = "\n".join(
                        f"{i+1}. " f"{d['Insurance Name']}"
                        for i, d in enumerate(result)
                    )

                    agg_begin = "\n".join(
                        f"{i+1}. " f"{d['Begin Date']}" for i, d in enumerate(result)
                    )

                    agg_end = "\n".join(
                        f"{i+1}. " f"{d['End Date']}" for i, d in enumerate(result)
                    )

                    # ----------------------------
                    # SCREENSHOT
                    # ----------------------------

                    screenshot_prefix = (
                        f"screenshot_"
                        f"{sanitized_name}_"
                        f"{member_id_raw}_"
                        f"{timestamp}"
                    )

                    take_screenshot(page, output_folder, screenshot_prefix)

                # --------------------------------
                # WRITE OUTPUT
                # --------------------------------

                output_row = dict(row)

                output_row.update(
                    {
                        "Insurance Name": agg_name,
                        "Begin Date": agg_begin,
                        "End Date": agg_end,
                        "Discrepancy": discrepancy,
                        "Penalty": penalty,
                    }
                )

                writer.writerow(output_row)

                progress_writer.writerow(output_row)

                # --------------------------------
                # SAVE IMMEDIATELY
                # --------------------------------

                f_out.flush()

                progress_f.flush()

                # --------------------------------
                # LOGGING
                # --------------------------------

                if log_callback:

                    log_callback(
                        f"Processed "
                        f"{idx}/{len(input_rows)}: "
                        f"{fullname} "
                        f"({member_id_raw})"
                    )

                # --------------------------------
                # PROGRESS UPDATE
                # --------------------------------

                if progress_callback:

                    progress_callback(
                        current=idx, total=len(input_rows), member_id=member_id_raw
                    )

            except Exception as e:

                if log_callback:

                    log_callback(
                        f"❌ Failed row " f"{idx} " f"({fullname} {member_id_raw}): {e}"
                    )

                continue

        # ----------------------------------------
        # CLEANUP
        # ----------------------------------------

        f_out.close()

        progress_f.close()

    # --------------------------------------------
    # FINISHED
    # --------------------------------------------

    if log_callback:

        log_callback("✅ Automation complete. " f"Output saved to {output_file}")
