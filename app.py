from flask import Flask, render_template, request
from dotenv import load_dotenv
import os
import json
import requests
import threading
import time
from requests.auth import HTTPBasicAuth
from datetime import datetime

load_dotenv()
app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
COMPANY_ID = os.getenv("COMPANY_ID", "666")
API_URI = os.getenv("API_URI", "https://api.company-information.service.gov.uk")
FUND_AMOUNT = os.getenv("FUND_AMOUNT", "0")
TOTAL_DEBT = float(os.getenv("TOTAL_DEBT", "5000000"))
BASELINE_PATH = os.getenv("BASELINE_PATH", "baseline.json")

# store recent changes in memory
latest_changes = []


def format_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d %b %Y")
    except:
        return date_str


def format_filing_description(item):
    description = item.get("description", "")
    values = item.get("description_values", {})

    if description == "change-registered-office-address-company-with-date-old-address-new-address":
        return f"Registered office address changed from {values.get('old_address')} to {values.get('new_address')} on {format_date(values.get('change_date', ''))}"
    if description == "accounts-with-accounts-type-total-exemption-full":
        return f"Accounts filed for a dormant company made up to {format_date(values.get('made_up_date', ''))}"
    if description == "confirmation-statement-with-no-updates":
        return f"Confirmation statement made on {format_date(values.get('made_up_date', ''))} with no updates"
    if description == "change-person-director-company-with-change-date":
        return f"Director details changed on {format_date(values.get('change_date', ''))}"
    if description == "change-to-a-person-with-significant-control":
        return f"Change to a person with significant control on {format_date(values.get('change_date', ''))}"
    if description == "incorporation-company":
        return "Company incorporated"

    return description.replace("-", " ").capitalize()


def get_company_data(company_number):
    url = f"{API_URI}/company/{company_number}"
    r = requests.get(url, auth=HTTPBasicAuth(API_KEY, ''))
    if r.status_code != 200:
        return None
    data = r.json()
    return {
        "name": data.get("company_name", "Unknown"),
        "status": data.get("company_status", "unknown").capitalize()
    }


def get_filing_history(company_number, count=25):
    url = f"{API_URI}/company/{company_number}/filing-history?items_per_page={count}"
    r = requests.get(url, auth=HTTPBasicAuth(API_KEY, ''))
    if r.status_code != 200:
        return []
    return r.json().get("items", [])


@app.route("/")
def index():
    company_number = request.args.get("company", COMPANY_ID)
    company = get_company_data(company_number)
    if not company:
        return "<h1>Company not found or API error</h1>", 404

    try:
        funds_float = float(FUND_AMOUNT.replace(",", "").replace("£", ""))
    except ValueError:
        funds_float = 0

    percent = round((funds_float / TOTAL_DEBT) * 100) if TOTAL_DEBT else 0
    stroke_offset = 377 - int(377 * percent / 100)

    filings_raw = get_filing_history(company_number)
    filings = [
        {
            "type": item.get("type"),
            "date": format_date(item.get("date", "")),
            "description": format_filing_description(item)
        }
        for item in filings_raw
    ]

    return render_template(
        "dashboard.html",
        name=company["name"],
        status=company["status"],
        percent=percent,
        offset=stroke_offset,
        funds_formatted="{:,.0f}".format(funds_float),
        total_debt_formatted="{:,.0f}".format(TOTAL_DEBT),
        filings=filings,
        changes=latest_changes
    )


# ----------------------
# Tracking functionality
# ----------------------

def load_baseline():
    try:
        with open(BASELINE_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load baseline: {e}")
        return None


def fetch_current_state(company_number):
    auth = HTTPBasicAuth(API_KEY, '')

    status = None
    filings = []

    s_resp = requests.get(f"{API_URI}/company/{company_number}", auth=auth)
    if s_resp.status_code == 200:
        status = s_resp.json().get("company_status")

    f_resp = requests.get(f"{API_URI}/company/{company_number}/filing-history?items_per_page=100", auth=auth)
    if f_resp.status_code == 200:
        filings = f_resp.json().get("items", [])

    return {
        "company_status": status,
        "latest_filings": [f["transaction_id"] for f in filings]
    }


def compare_state(baseline, current):
    changes = []

    base_status = baseline.get("company_status")
    curr_status = current.get("company_status")

    if base_status != curr_status:
        changes.append(f"Company status changed: {base_status} → {curr_status}")

    baseline_ids = set(baseline.get("latest_filings", []))
    current_ids = set(current.get("latest_filings", []))

    print("Baseline filings:", len(baseline_ids))
    print("Current filings:", len(current_ids))

    new_ids = current_ids - baseline_ids
    if new_ids:
        changes.append(f"New filings detected: {len(new_ids)} new filing(s): {sorted(list(new_ids))}")

    return changes


def tracking_loop():
    global latest_changes
    print("Tracking thread started")
    while True:
        print(f"[Tracking] Check at {datetime.now().isoformat()}")
        baseline = load_baseline()
        if not baseline:
            print("No baseline found.")
            time.sleep(30)
            continue

        current = fetch_current_state(COMPANY_ID)
        changes = compare_state(baseline, current)
        if changes:
            latest_changes = [
                {"timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), "messages": changes}
            ]
            print("Changes detected:")
            for msg in changes:
                print(" -", msg)
        else:
            latest_changes = []
            print("No changes.")
        time.sleep(3600)

threading.Thread(target=tracking_loop, daemon=True).start()
if __name__ == "__main__":
    app.run(debug=True)
