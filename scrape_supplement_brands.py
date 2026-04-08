"""
Amazon PDP Brand Scraper — Fills in missing brands from supplement CSV.

Only visits product pages for ASINs where brand is empty in amazon_supplements.csv.
Updates the CSV in-place with scraped brand names.

Run:
    python3 scrape_supplement_brands.py
"""

import asyncio
import csv
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright

INPUT_CSV = "amazon_supplements.csv"

EXTRACT_BRAND_JS = """
() => {
    // Method 1: bylineInfo link (most common)
    const byline = document.querySelector('#bylineInfo');
    if (byline) {
        let text = byline.textContent.trim();
        // "Visit the X Store" or "Brand: X"
        text = text.replace(/^Visit the\s+/i, '').replace(/\s+Store$/i, '');
        text = text.replace(/^Brand:\s*/i, '');
        if (text && text.length > 1 && text.length < 60) return text;
    }
    // Method 2: product detail table
    const rows = document.querySelectorAll('#productDetails_detailBullets_sections1 tr, #detailBullets_feature_div li');
    for (const row of rows) {
        const text = row.textContent || '';
        if (/brand/i.test(text)) {
            const match = text.match(/brand[:\\s]+([^\\n]+)/i);
            if (match) return match[1].trim();
        }
    }
    // Method 3: tech spec table
    const techRows = document.querySelectorAll('#productDetails_techSpec_section_1 tr');
    for (const row of techRows) {
        if (/brand/i.test(row.textContent)) {
            const td = row.querySelector('td');
            if (td) return td.textContent.trim();
        }
    }
    return '';
}
"""


async def main():
    # Load CSV and find missing brands
    rows = []
    missing_indices = []
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for i, row in enumerate(reader):
            rows.append(row)
            if not row.get("brand", "").strip() and row.get("asin", ""):
                missing_indices.append(i)

    print(f"Total products: {len(rows):,}")
    print(f"Missing brands: {len(missing_indices):,}")

    if not missing_indices:
        print("No missing brands!")
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await ctx.new_page()

        # Warm up
        print("Establishing session...")
        await page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3000)
        print("Session ready.\n")

        found = 0
        errors = 0
        for idx, row_idx in enumerate(missing_indices):
            asin = rows[row_idx]["asin"]
            url = f"https://www.amazon.com/dp/{asin}"

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(1500)

                brand = await page.evaluate(EXTRACT_BRAND_JS)
                brand = brand.strip() if brand else ""

                if brand:
                    rows[row_idx]["brand"] = brand
                    found += 1
                    status = f"✓ {brand}"
                else:
                    status = "✗ no brand found"

            except Exception as e:
                status = f"ERROR: {str(e)[:50]}"
                errors += 1

            if (idx + 1) % 25 == 0 or idx == 0:
                print(f"  [{idx+1}/{len(missing_indices)}] {asin}: {status}")

            # Save checkpoint every 100
            if (idx + 1) % 100 == 0:
                with open(INPUT_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"  → Checkpoint saved ({found} brands found so far)")

            # Rate limit
            await page.wait_for_timeout(1000)

        await browser.close()

    # Final save
    with open(INPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone! Found {found}/{len(missing_indices)} brands ({errors} errors)")
    print(f"Updated → {INPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
