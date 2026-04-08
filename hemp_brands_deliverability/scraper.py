#!/usr/bin/env python3
"""
THCA Deliverability Scraper
Checks whether top hemp DTC brands ship THCA products to Ohio and Texas.
"""

import asyncio
import csv
import os
import sys
from datetime import datetime

from config import BRANDS, TEST_LOCATIONS
from scrapers.shipping_policy import ShippingPolicyScraper
from scrapers.cart_checkout import CartCheckoutScraper


RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


async def scrape_brand(brand: dict, policy_scraper, cart_scraper) -> list[dict]:
    """Run both scraping methods for a single brand."""
    print(f"\n{'='*60}")
    print(f"Scraping: {brand['name']} ({brand['base_url']})")
    print(f"{'='*60}")

    all_results = []

    # Method 1: Shipping policy
    print(f"\n--- Method 1: Shipping Policy ---")
    try:
        policy_results = await policy_scraper.check_brand(brand, TEST_LOCATIONS)
        all_results.extend(policy_results)
        for r in policy_results:
            print(f"  {r['state']}: {r['result']} - {r['details'][:80]}")
    except Exception as e:
        print(f"  [!] Policy scraper error: {e}")
        for loc in TEST_LOCATIONS:
            all_results.append({
                "brand": brand["name"],
                "website": brand["base_url"],
                "state": loc["state"],
                "abbreviation": loc["abbreviation"],
                "method": "shipping_policy",
                "result": "error",
                "details": str(e)[:200],
            })

    # Method 2: Cart checkout
    print(f"\n--- Method 2: Cart + Checkout ---")
    try:
        cart_results = await cart_scraper.check_brand(brand, TEST_LOCATIONS)
        all_results.extend(cart_results)
        for r in cart_results:
            print(f"  {r['state']}: {r['result']} - {r['details'][:80]}")
    except Exception as e:
        print(f"  [!] Cart scraper error: {e}")
        for loc in TEST_LOCATIONS:
            all_results.append({
                "brand": brand["name"],
                "website": brand["base_url"],
                "state": loc["state"],
                "abbreviation": loc["abbreviation"],
                "method": "cart_checkout",
                "result": "error",
                "details": str(e)[:200],
            })

    # Enrich all results with Brightfield data
    for r in all_results:
        r["brightfield_rank"] = brand.get("brightfield_rank", "")
        r["brightfield_funnel_pct"] = brand.get("brightfield_funnel_pct", "")

    return all_results


def determine_deliverability(brand_results: list[dict]) -> str:
    """Combine results from both methods into a final verdict."""
    results_set = {r["result"] for r in brand_results}

    # Check if brand has no THCA products on their DTC site
    cart_results = [r for r in brand_results if r["method"] == "cart_checkout"]
    if cart_results and all(r["result"] == "no_thca_product_found" for r in cart_results):
        # Also check policy — if policy found no restrictions, still N/A since no THCA to buy
        policy_results = [r for r in brand_results if r["method"] == "shipping_policy"]
        has_policy_restriction = any(
            r["result"] in ("restricted", "possibly_restricted")
            for r in policy_results
        )
        if not has_policy_restriction:
            return "n/a"

    if "restricted" in results_set or "restricted_on_page" in results_set:
        return "no"
    elif "deliverable" in results_set:
        return "yes"
    elif "possibly_restricted" in results_set:
        return "likely_no"
    elif "no_restriction_found" in results_set or "has_restrictions_other_states" in results_set:
        return "likely_yes"
    else:
        return "unclear"


def write_results(all_results: list[dict]):
    """Write results to CSV."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(RESULTS_DIR, f"deliverability_{ts}.csv")

    fieldnames = [
        "brand", "website", "brightfield_rank", "brightfield_funnel_pct",
        "state", "abbreviation",
        "method", "result", "details", "policy_url", "deliverable", "scraped_at",
    ]

    # Group results by brand+state to determine deliverability
    from collections import defaultdict
    grouped = defaultdict(list)
    for r in all_results:
        key = (r["brand"], r["state"])
        grouped[key].append(r)

    rows = []
    for r in all_results:
        key = (r["brand"], r["state"])
        r["deliverable"] = determine_deliverability(grouped[key])
        r["scraped_at"] = datetime.now().isoformat()
        rows.append(r)

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'='*60}")
    print(f"Results written to: {filepath}")
    print(f"Total rows: {len(rows)}")

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for key, group in grouped.items():
        brand, state = key
        verdict = determine_deliverability(group)
        print(f"  {brand} -> {state}: {verdict}")

    return filepath


async def main():
    # Parse CLI args for brand filtering
    brand_filter = None
    if len(sys.argv) > 1:
        brand_filter = [b.strip().lower() for b in sys.argv[1].split(",")]
        print(f"Filtering to brands: {brand_filter}")

    brands = BRANDS
    if brand_filter:
        brands = [b for b in BRANDS if b["name"].lower() in brand_filter]
        if not brands:
            print(f"No matching brands found. Available: {[b['name'] for b in BRANDS]}")
            return

    policy_scraper = ShippingPolicyScraper(headless=True)
    cart_scraper = CartCheckoutScraper(headless=True)

    await policy_scraper.start()
    await cart_scraper.start()

    all_results = []
    try:
        for brand in brands:
            results = await scrape_brand(brand, policy_scraper, cart_scraper)
            all_results.extend(results)
    finally:
        await policy_scraper.stop()
        await cart_scraper.stop()

    if all_results:
        write_results(all_results)


if __name__ == "__main__":
    asyncio.run(main())
