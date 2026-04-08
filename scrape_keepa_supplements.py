"""
Keepa API Scraper — Historical data for Amazon supplement products.

Fetches review count, rating, sales rank, and price history for ASINs
from amazon_supplements.csv. Prioritizes products with highest sold volume.

Outputs: keepa_supplements.csv (one row per ASIN per date observation)

Usage:
    python3 scrape_keepa_supplements.py YOUR_KEEPA_API_KEY
    # or set KEEPA_API_KEY environment variable
"""

import csv
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

AMAZON_CSV = "amazon_supplements.csv"
OUTPUT_CSV = "keepa_supplements.csv"
KEEPA_BASE = "https://api.keepa.com"
BATCH_SIZE = 10     # 10 ASINs × 2 tokens = 20 tokens per batch (~7 min at 3 tokens/min)
DOMAIN = 1          # 1 = amazon.com (US)

# Keepa epoch: minutes since 2011-01-01
KEEPA_EPOCH = datetime(2011, 1, 1)


def keepa_time_to_date(keepa_minutes):
    return (KEEPA_EPOCH + timedelta(minutes=int(keepa_minutes))).strftime("%Y-%m-%d")


def parse_csv_history(csv_array, value_type="int"):
    """Parse Keepa's [time, value, time, value, ...] array into [(date, value), ...]."""
    if not csv_array:
        return []
    points = []
    for i in range(0, len(csv_array) - 1, 2):
        ts, val = csv_array[i], csv_array[i + 1]
        if ts < 0 or val < 0:
            continue
        date = keepa_time_to_date(ts)
        if value_type == "rating":
            val = val / 10.0
        elif value_type == "price":
            val = val / 100.0
        points.append((date, val))
    return points


def query_keepa(api_key, asins):
    """Query Keepa product API for a batch of ASINs."""
    params = {
        "key": api_key,
        "domain": DOMAIN,
        "asin": ",".join(asins),
        "rating": "1",
    }
    url = f"{KEEPA_BASE}/product?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "User-Agent": "supplement-market-analysis/1.0",
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    })

    import gzip as _gzip
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        try:
            data = json.loads(_gzip.decompress(raw))
        except Exception:
            data = json.loads(raw)

    return (
        data.get("products", []),
        data.get("tokensLeft", 0),
        data.get("refillIn", 0),
        data.get("refillRate", 0),
    )


def extract_history(product):
    """Extract time series from a Keepa product object."""
    asin = product.get("asin", "")
    csv_data = product.get("csv", [])

    if not csv_data or len(csv_data) < 18:
        return []

    reviews = parse_csv_history(csv_data[17] if len(csv_data) > 17 else None, "int")
    ratings = parse_csv_history(csv_data[16] if len(csv_data) > 16 else None, "rating")
    sales = parse_csv_history(csv_data[3] if len(csv_data) > 3 else None, "int")
    prices = parse_csv_history(csv_data[0] if len(csv_data) > 0 else None, "price")

    all_dates = sorted(set(
        [d for d, _ in reviews] + [d for d, _ in ratings] +
        [d for d, _ in sales] + [d for d, _ in prices]
    ))

    review_dict, rating_dict = dict(reviews), dict(ratings)
    sales_dict, price_dict = dict(sales), dict(prices)

    rows = []
    last = {"review": None, "rating": None, "sales": None, "price": None}
    for date in all_dates:
        if date in review_dict: last["review"] = review_dict[date]
        if date in rating_dict: last["rating"] = rating_dict[date]
        if date in sales_dict: last["sales"] = sales_dict[date]
        if date in price_dict: last["price"] = price_dict[date]
        rows.append({
            "asin": asin, "date": date,
            "reviewCount": last["review"], "rating": last["rating"],
            "salesRank": last["sales"], "price": last["price"],
        })
    return rows


def load_asins_by_priority():
    """Load ASINs from supplement CSV, sorted by sold volume."""
    with open(AMAZON_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    def parse_sold(v):
        if not v:
            return 0
        v = v.lower().replace(",", "").replace("+", "")
        m = re.search(r"([\d.]+)\s*k", v)
        if m:
            return int(float(m.group(1)) * 1000)
        m = re.search(r"(\d+)", v)
        return int(m.group(1)) if m else 0

    rows.sort(key=lambda r: -parse_sold(r.get("boughtPastMonth", "")))
    return [r["asin"] for r in rows if r.get("asin")]


def save_history(all_rows):
    fields = ["asin", "date", "reviewCount", "rating", "salesRank", "price"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\n  Checkpoint: {len(all_rows):,} data points → {OUTPUT_CSV}")


def main():
    api_key = os.environ.get("KEEPA_API_KEY") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not api_key:
        print("Usage: python3 scrape_keepa_supplements.py YOUR_KEEPA_API_KEY")
        print("   or: KEEPA_API_KEY=... python3 scrape_keepa_supplements.py")
        sys.exit(1)

    asins = load_asins_by_priority()
    print(f"Total ASINs: {len(asins):,}")

    # Load existing data to skip already-scraped ASINs
    existing_asins = set()
    all_rows = []
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))
            existing_asins = set(r["asin"] for r in existing_rows)
            all_rows = existing_rows
        print(f"Already scraped: {len(existing_asins):,} ASINs ({len(all_rows):,} data points)")
    except FileNotFoundError:
        pass

    remaining = [a for a in asins if a not in existing_asins]
    print(f"Remaining: {len(remaining):,}")

    if not remaining:
        print("All done!")
        return

    batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    print(f"Batches: {len(batches)} ({BATCH_SIZE} ASINs each)\n")

    for batch_num, batch_asins in enumerate(batches):
        print(f"  Batch {batch_num + 1}/{len(batches)} ({len(batch_asins)} ASINs)…", end=" ")

        try:
            products, tokens_left, refill_in, refill_rate = query_keepa(api_key, batch_asins)
        except Exception as e:
            err_str = str(e)
            print(f"ERROR: {err_str}")
            if "429" in err_str:
                tokens_needed = len(batch_asins) * 2
                wait = tokens_needed * 60 + 30
                print(f"  Rate limited. Waiting {wait}s…")
                time.sleep(wait)
                try:
                    products, tokens_left, refill_in, refill_rate = query_keepa(api_key, batch_asins)
                except Exception:
                    time.sleep(120)
                    continue
            else:
                time.sleep(60)
                continue

        for product in products:
            all_rows.extend(extract_history(product))

        with_data = sum(1 for p in products if p.get("csv") and len(p.get("csv", [])) > 17 and p["csv"][17])
        print(f"got {len(products)} ({with_data} with reviews) | tokens: {tokens_left} | rows: {len(all_rows):,}")

        if batch_num % 10 == 0:
            save_history(all_rows)

        # Rate limit management
        tokens_needed = BATCH_SIZE * 2
        if tokens_left < tokens_needed:
            rate = max(refill_rate, 1)
            deficit = tokens_needed - tokens_left
            wait = (deficit / rate) * 60 + 10
            print(f"  Waiting {wait:.0f}s for tokens…")
            time.sleep(wait)
        else:
            time.sleep(2)

    save_history(all_rows)
    print(f"\nDone! {len(all_rows):,} data points for {len(set(r['asin'] for r in all_rows)):,} ASINs")


if __name__ == "__main__":
    main()
