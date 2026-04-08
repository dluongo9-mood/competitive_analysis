"""
State Cannabis Sales Data Downloader

Downloads public cannabis sales data from state regulatory agencies:
  - Colorado: CDOR monthly sales Excel files
  - Washington: LCB Socrata API (product-level where available)
  - Oregon: OLCC data (if downloadable)

Outputs: state_cannabis_sales.csv

Run:
    python3 scrape_state_cannabis.py
"""

import csv
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

OUTPUT_CSV = "state_cannabis_sales.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

FIELDS = [
    "state", "year", "month", "total_sales", "edible_sales",
    "edible_pct", "source", "notes",
]


def download_json(url, timeout=30):
    """Download JSON from a URL."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_file(url, dest, timeout=60):
    """Download a file to disk."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(dest, "wb") as f:
            f.write(resp.read())
    return dest


# ── Colorado ─────────────────────────────────────────────────────────────────
def fetch_colorado():
    """
    Colorado CDOR publishes monthly sales totals as Excel.
    The MED Tableau dashboard has edibles breakdowns (~12-15% of total).

    CDOR downloads:
      - https://cdor.colorado.gov/data-and-reports/marijuana-data/marijuana-sales-reports
      - Direct xlsx links change; try known patterns.
    """
    results = []

    # Try to download the CDOR sales report Excel
    xlsx_urls = [
        "https://cdor.colorado.gov/sites/cdor/files/documents/Marijuana_Sales_2014_To_Date_Report.xlsx",
        "https://revenue.colorado.gov/sites/revenue/files/documents/Marijuana_Sales_2014_To_Date_Report.xlsx",
    ]

    xlsx_path = "colorado_sales.xlsx"
    downloaded = False
    for url in xlsx_urls:
        try:
            download_file(url, xlsx_path)
            downloaded = True
            print(f"  Downloaded Colorado sales data: {xlsx_path}")
            break
        except Exception as e:
            print(f"  CO download failed ({url}): {e}")

    if downloaded:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx_path, data_only=True)
            ws = wb.active

            # Parse the Excel structure (varies by year)
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                # Expected: Month, Year, Medical Sales, Retail Sales, Total
                # Exact columns may vary
                month_val = row[0]
                year_val = row[1] if len(row) > 1 else None
                total = row[-1] if len(row) > 2 else None

                if isinstance(total, (int, float)) and total > 0:
                    results.append({
                        "state": "CO",
                        "year": int(year_val) if year_val else None,
                        "month": month_val,
                        "total_sales": total,
                        "edible_sales": None,  # CDOR doesn't break out edibles
                        "edible_pct": None,
                        "source": "CDOR",
                        "notes": "Medical + Retail combined",
                    })
            print(f"  Colorado: {len(results)} monthly records")
        except ImportError:
            print("  openpyxl not installed — can't parse Colorado Excel")
        except Exception as e:
            print(f"  Error parsing Colorado data: {e}")

    return results


# ── Washington ───────────────────────────────────────────────────────────────
def fetch_washington():
    """
    Washington LCB publishes data on Socrata (data.lcb.wa.gov).

    Product-level datasets (may be stale after ~2017):
      - Solid Edibles: https://data.lcb.wa.gov/resource/479x-ivk9.json
      - Usable (flower): https://data.lcb.wa.gov/resource/9wz2-qma2.json
      - Monthly sales: https://data.lcb.wa.gov/resource/v4wy-crji.json

    Socrata API supports $limit, $offset, $order, $where for filtering.
    """
    results = []

    # Try monthly sales summary first
    base = "https://data.lcb.wa.gov/resource"
    endpoints = {
        "monthly_usable": f"{base}/v4wy-crji.json",
        "other_products": f"{base}/479x-ivk9.json",
    }

    for name, url in endpoints.items():
        try:
            # Get most recent data, paginated
            offset = 0
            limit = 1000
            all_records = []

            while True:
                page_url = f"{url}?$limit={limit}&$offset={offset}&$order=date_trunc_ymd%20DESC"
                data = download_json(page_url)
                if not data:
                    break
                all_records.extend(data)
                offset += limit
                if len(data) < limit:
                    break
                time.sleep(1)  # rate limit

            print(f"  WA {name}: {len(all_records)} records")

            for r in all_records:
                date_str = r.get("date_trunc_ymd", "")
                try:
                    dt = datetime.fromisoformat(date_str.replace("T00:00:00.000", ""))
                    year = dt.year
                    month = dt.month
                except:
                    year = month = None

                total = float(r.get("total_sales", 0) or 0)

                results.append({
                    "state": "WA",
                    "year": year,
                    "month": month,
                    "total_sales": total,
                    "edible_sales": total if "other" in name else None,
                    "edible_pct": None,
                    "source": f"LCB Socrata ({name})",
                    "notes": r.get("productname", ""),
                })

        except Exception as e:
            print(f"  WA {name}: {e}")

    return results


# ── Save ─────────────────────────────────────────────────────────────────────
def save_results(results):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def main():
    all_results = []

    print("Fetching Colorado data...")
    all_results.extend(fetch_colorado())

    print("Fetching Washington data...")
    all_results.extend(fetch_washington())

    if all_results:
        save_results(all_results)
        print(f"\nDone! {len(all_results)} records → {OUTPUT_CSV}")
    else:
        print("\nNo data fetched. Check network connectivity.")


if __name__ == "__main__":
    main()
