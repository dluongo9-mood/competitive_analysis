#!/usr/bin/env python3
"""Quick re-test of iDelta and ELYXR with fixed false-positive detection."""

import asyncio
import csv
import os
import sys
from datetime import datetime

# Import the functions from test_targeted
sys.path.insert(0, os.path.dirname(__file__))
from test_targeted import (
    test_idelta, test_elyxr, check_result,
    dismiss_age_gate, screenshot, TEST_ZIPS,
    SCREENSHOTS_DIR, RESULTS_DIR,
)
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        slow_mo=400,
    )

    brands = [
        {"name": "iDelta", "func": test_idelta, "rank": 4, "pct": 25.6,
         "base_url": "https://delta8vapeoil.com"},
        {"name": "ELYXR", "func": test_elyxr, "rank": 23, "pct": 11.0,
         "base_url": "https://www.elyxr.com"},
    ]

    all_results = []
    for brand in brands:
        for loc in TEST_ZIPS:
            print(f"\n{'='*50}")
            print(f"{brand['name']} -> {loc['state']} ({loc['zip']})")
            print(f"{'='*50}")

            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await ctx.new_page()
            try:
                result = await brand["func"](page, loc)
            except Exception as e:
                result = {"result": "error", "details": str(e)[:200]}

            print(f"  => {result['result']}: {result['details'][:80]}")
            all_results.append({
                "brand": brand["name"], "state": loc["state"],
                "abbreviation": loc["abbreviation"],
                **result,
            })
            await ctx.close()

    await browser.close()
    await pw.stop()

    print("\nSUMMARY")
    for r in all_results:
        print(f"  {r['brand']:20} -> {r['state']}: {r['result']}")


if __name__ == "__main__":
    asyncio.run(main())
