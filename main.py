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

CDP_URL = "http://127.0.0.1:9222"

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
    print("🚀 Launching new Edge browser with CDP...")
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
            print("✅ CDP browser is ready")
            return True
        time.sleep(1)
    return False


def ensure_edge_cdp():
    if is_cdp_running():
        print("✅ Existing CDP browser detected")
        return
    print("⚠ No CDP browser detected")
    success = launch_edge_with_cdp()
    if not success:
        raise Exception("❌ Failed to launch Edge with CDP")


def get_or_create_page(context):
    if context.pages:
        page = context.pages[0]
        print(f"🌐 Attached to existing tab: {page.url}")
        return page
    page = context.new_page()
    print("🆕 Created new tab")
    return page


def get_valid_csv_path() -> Path:
    """
    Prompts the user to enter the input CSV file path.
    Verifies the file exists. Returns Path object if valid, else None.
    Retries until a valid path is provided or user cancels with empty input.
    """
    while True:
        try:
            csv_input_path = (
                input(
                    "Please enter the path to the input CSV file (or press Enter to cancel): "
                )
                .strip('"')
                .strip()
            )
            if csv_input_path == "":
                print("Input cancelled by user.")
                return None

            input_path = Path(csv_input_path)
            if not input_path.is_file():
                print(
                    f"❌ Input CSV file not found: {csv_input_path}. Please try again."
                )
                continue

            return input_path
        except Exception as e:
            print(f"❌ Error processing input: {e}. Please try again.")


def prepare_output_folder(input_csv_path: str, timestamp: str) -> Tuple[Path, Path]:
    """
    Create an output folder based on the input CSV filename plus current timestamp.

    Returns:
        output_folder (Path): The path to the created output folder.
        output_file (Path): The path to the output CSV file inside the folder.
    """
    input_path = Path(input_csv_path)
    input_stem = input_path.stem
    output_folder_name = f"{input_stem}_{timestamp}"
    output_folder = Path.cwd() / output_folder_name
    output_folder.mkdir(parents=True, exist_ok=True)
    output_file = output_folder / f"{input_stem}-{timestamp}.csv"
    return output_folder, output_file


def prepare_csv_reader_writer(input_path: Path, output_file: Path):
    """
    Reads the entire input CSV file, prepares the output CSV file with additional headers,
    and returns the list of input rows and the CSV writer object.
    """
    # Read all input data
    with open(input_path, newline="", encoding="utf-8") as f:
        input_rows = list(csv.DictReader(f))
        input_headers = list(input_rows[0].keys()) if input_rows else []

    # Prepare output headers (add columns you need)
    output_headers = input_headers + [
        "Insurance Name",
        "Begin Date",
        "End Date",
        "Discrepancy",
        "Penalty",
    ]
    # Open output CSV and prepare writer
    f_out = open(output_file, mode="w", newline="", encoding="utf-8")
    writer = csv.DictWriter(f_out, fieldnames=output_headers)
    writer.writeheader()

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

    progress_file = input_path.parent / f"{input_path.stem}_progress.csv"

    processed_ids = set()

    file_exists = progress_file.exists()

    progress_f = open(progress_file, mode="a", newline="", encoding="utf-8")

    progress_writer = csv.DictWriter(progress_f, fieldnames=output_headers)

    if not file_exists:
        progress_writer.writeheader()

    else:
        with open(progress_file, newline="", encoding="utf-8") as f:

            reader = csv.DictReader(f)

            for row in reader:

                medicaid = row.get("Medicaid Number", "").strip()

                if medicaid:
                    processed_ids.add(medicaid)

    return (progress_file, processed_ids, progress_writer, progress_f)


def main():
    ensure_edge_cdp()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = get_or_create_page(context)
        input(
            "Please log in to the portal if needed, then press Enter here to continue..."
        )

        input_path = get_valid_csv_path()
        if input_path is None:
            return  # or exit

        # Prepare output folder and unique output file
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_folder, output_file = prepare_output_folder(input_path, timestamp)

        input_rows, writer, f_out = prepare_csv_reader_writer(input_path, output_file)

        progress_file, processed_ids, progress_writer, progress_f = (
            setup_progress_tracking(input_path, writer.fieldnames)
        )

        # remember to close the file object at the end:
        # f_out.close()

        page.wait_for_selector(
            "#dnn_PrimaryMenu_PrimaryMenuRepeater_PrimaryItemHCPHyperlink_2"
        )
        page.click("#dnn_PrimaryMenu_PrimaryMenuRepeater_PrimaryItemHCPHyperlink_2")

        for idx, row in enumerate(input_rows, 1):
            row_contract = row.get("Contract Name", "").strip()
            member_id_raw = row.get("Medicaid Number", "").strip()

            if member_id_raw in processed_ids:

                print(f"⏩ Skipping completed row: {member_id_raw}")

                continue

            dob = row.get("Date of Birth", "").strip()
            lname = row.get("Last Name", "").strip()
            fname = row.get("First Name", "").strip()
            fullname = f"{lname}, {fname}"
            sanitized_name = sanitize_filename(fullname)

            # Calling the search function to perform the search and get the date range used for discrepancy checking
            start_date_str, end_date_str = search(page, member_id_raw, dob)

            # Calling the extract_results function to get the results, discrepancy status, and penalty status
            result, discrepancy, penalty = extract_results(
                page, row_contract, start_date_str, end_date_str
            )

            # After extracting `result`, determining `discrepancy`, `penalty`, and within your CSV writing loop:

            if not result:
                agg_name = "N/A"
                agg_begin = "N/A"
                agg_end = "N/A"
            else:
                agg_name = "\n".join(
                    f"{i+1}. {d['Insurance Name']}" for i, d in enumerate(result)
                )
                agg_begin = "\n".join(
                    f"{i+1}. {d['Begin Date']}" for i, d in enumerate(result)
                )
                agg_end = "\n".join(
                    f"{i+1}. {d['End Date']}" for i, d in enumerate(result)
                )

                screenshot_prefix = (
                    f"screenshot_{sanitized_name}_{member_id_raw}_{timestamp}"
                )
                take_screenshot(page, output_folder, screenshot_prefix)

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
            progress_f.flush()

            screenshot_prefix = (
                f"screenshot_{sanitized_name}_{member_id_raw}_{timestamp}"
            )

            print(f"Processed {idx}/{len(input_rows)}: Medicaid Number={member_id_raw}")
            f_out.flush()  # ensure data is written to disk after each row
        f_out.close()  # close the file after processing all rows
        progress_f.close()

    print(f"✅ Automation complete. Output saved to {output_file}")


if __name__ == "__main__":
    main()
