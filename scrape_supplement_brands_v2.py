"""
Amazon PDP Brand Scraper v2 — More robust extraction with retries.

Visits product pages for ASINs still missing brands in amazon_supplements.csv.
Uses multiple extraction methods and longer waits.

Run:
    python3 scrape_supplement_brands_v2.py
"""

import asyncio
import csv
import re
from pathlib import Path

from playwright.async_api import async_playwright

INPUT_CSV = "amazon_supplements.csv"

EXTRACT_BRAND_JS = """
() => {
    // Method 1: bylineInfo link (most reliable)
    const byline = document.querySelector('#bylineInfo');
    if (byline) {
        let text = byline.textContent.trim();
        text = text.replace(/^Visit the\\s+/i, '').replace(/\\s+Store$/i, '');
        text = text.replace(/^Brand:\\s*/i, '');
        if (text && text.length > 1 && text.length < 60) return {brand: text, method: 'byline'};
    }

    // Method 2: Brand row in product details table
    const detailRows = document.querySelectorAll('#productDetails_detailBullets_sections1 tr');
    for (const row of detailRows) {
        const th = row.querySelector('th');
        const td = row.querySelector('td');
        if (th && td && /brand/i.test(th.textContent)) {
            const brand = td.textContent.trim();
            if (brand && brand.length < 60) return {brand, method: 'detail_table'};
        }
    }

    // Method 3: Detail bullets (li format)
    const bullets = document.querySelectorAll('#detailBullets_feature_div li, #detailBulletsWrapper_feature_div li');
    for (const li of bullets) {
        const text = li.textContent || '';
        const m = text.match(/Brand\\s*[:\\u200F\\u200E]+\\s*(.+)/i);
        if (m) {
            const brand = m[1].trim();
            if (brand && brand.length < 60) return {brand, method: 'bullets'};
        }
    }

    // Method 4: Tech specs table
    const techRows = document.querySelectorAll('#productDetails_techSpec_section_1 tr');
    for (const row of techRows) {
        const th = row.querySelector('th');
        const td = row.querySelector('td');
        if (th && td && /brand/i.test(th.textContent)) {
            const brand = td.textContent.trim();
            if (brand && brand.length < 60) return {brand, method: 'tech_spec'};
        }
    }

    // Method 5: JSON-LD schema
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const s of scripts) {
        try {
            const data = JSON.parse(s.textContent);
            if (data.brand && data.brand.name) return {brand: data.brand.name, method: 'json_ld'};
            if (Array.isArray(data)) {
                for (const item of data) {
                    if (item.brand && item.brand.name) return {brand: item.brand.name, method: 'json_ld'};
                }
            }
        } catch(e) {}
    }

    // Method 6: a-brand or brand link
    const brandLink = document.querySelector('#brand, .po-brand .a-span9 .a-size-base');
    if (brandLink) {
        const brand = brandLink.textContent.trim();
        if (brand && brand.length < 60) return {brand, method: 'brand_element'};
    }

    // Check if page loaded (CAPTCHA detection)
    const captcha = document.querySelector('#captchacharacters, .a-last');
    if (captcha) return {brand: '', method: 'CAPTCHA'};

    const title = document.querySelector('#productTitle');
    if (!title) return {brand: '', method: 'PAGE_NOT_LOADED'};

    return {brand: '', method: 'NOT_FOUND'};
}
"""


async def main():
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

        print("Establishing session...")
        await page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3000)
        print("Session ready.\n")

        found = 0
        not_found = 0
        captcha = 0
        methods = {}

        for idx, row_idx in enumerate(missing_indices):
            asin = rows[row_idx]["asin"]
            url = f"https://www.amazon.com/dp/{asin}"

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                # Wait longer for page elements to render
                await page.wait_for_timeout(2500)

                # Try to wait for bylineInfo specifically
                try:
                    await page.wait_for_selector("#bylineInfo, #brand, #detailBullets_feature_div", timeout=3000)
                except Exception:
                    pass

                result = await page.evaluate(EXTRACT_BRAND_JS)
                brand = result.get("brand", "").strip() if result else ""
                method = result.get("method", "unknown") if result else "error"

                if brand:
                    rows[row_idx]["brand"] = brand
                    found += 1
                    methods[method] = methods.get(method, 0) + 1
                elif method == "CAPTCHA":
                    captcha += 1
                    # Wait longer on CAPTCHA
                    await page.wait_for_timeout(5000)
                else:
                    not_found += 1
                    methods[method] = methods.get(method, 0) + 1

            except Exception as e:
                methods["error"] = methods.get("error", 0) + 1

            if (idx + 1) % 50 == 0:
                print(f"  [{idx+1}/{len(missing_indices)}] Found: {found}, Not found: {not_found}, CAPTCHA: {captcha}")

            if (idx + 1) % 100 == 0:
                with open(INPUT_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"  → Checkpoint saved")

            await page.wait_for_timeout(1200)

        await browser.close()

    with open(INPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone! Found: {found}, Not found: {not_found}, CAPTCHA: {captcha}")
    print(f"Methods: {methods}")
    print(f"Updated → {INPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
