"""
Amazon PDP Brand Scraper v3 — Fresh session, all unknowns, revenue-prioritized.
"""
import asyncio
import csv
import re

from playwright.async_api import async_playwright

INPUT_CSV = "amazon_supplements.csv"

EXTRACT_BRAND_JS = """
() => {
    const byline = document.querySelector('#bylineInfo');
    if (byline) {
        let t = byline.textContent.trim()
            .replace(/^Visit the\\s+/i, '').replace(/\\s+Store$/i, '')
            .replace(/^Brand:\\s*/i, '');
        if (t.length > 1 && t.length < 60) return t;
    }
    for (const row of document.querySelectorAll('tr')) {
        const th = row.querySelector('th,td');
        if (th && /^\\s*Brand\\s*$/i.test(th.textContent)) {
            const tds = row.querySelectorAll('td');
            if (tds.length > 1) return tds[tds.length-1].textContent.trim();
            if (tds.length === 1 && row.querySelector('th')) return tds[0].textContent.trim();
        }
    }
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
        try {
            const d = JSON.parse(s.textContent);
            if (d.brand && d.brand.name) return d.brand.name;
        } catch(e) {}
    }
    return '';
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
            if not row.get("brand", "").strip():
                sold = row.get("boughtPastMonth", "").lower().replace(",", "").replace("+", "")
                m = re.search(r"([\d.]+)\s*k", sold)
                sold_n = int(float(m.group(1)) * 1000) if m else (int(re.search(r"(\d+)", sold).group(1)) if re.search(r"(\d+)", sold) else 0)
                price = float(row.get("price", 0) or 0)
                missing_indices.append((i, price * sold_n))

    # Sort by revenue descending
    missing_indices.sort(key=lambda x: -x[1])
    print(f"Total: {len(rows):,}, Missing brands: {len(missing_indices):,}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await ctx.new_page()

        await page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        print("Session ready.\n")

        found = 0
        captcha = 0
        for idx, (row_idx, rev) in enumerate(missing_indices):
            asin = rows[row_idx]["asin"]
            try:
                await page.goto(f"https://www.amazon.com/dp/{asin}", wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
                try:
                    await page.wait_for_selector("#bylineInfo, #brand, .po-brand, #captchacharacters", timeout=4000)
                except:
                    pass

                is_captcha = await page.evaluate("!!document.querySelector('#captchacharacters')")
                if is_captcha:
                    captcha += 1
                    if captcha >= 3:
                        print(f"\n  CAPTCHA wall hit at product {idx+1}. Stopping.")
                        break
                    await page.wait_for_timeout(5000)
                    continue

                captcha = 0  # reset on success
                brand = await page.evaluate(EXTRACT_BRAND_JS)
                brand = brand.strip() if brand else ""

                if brand:
                    rows[row_idx]["brand"] = brand
                    found += 1
            except Exception:
                pass

            if (idx + 1) % 50 == 0:
                print(f"  [{idx+1}/{len(missing_indices)}] Found: {found}, Rev coverage: ${sum(missing_indices[j][1] for j in range(idx+1) if rows[missing_indices[j][0]].get('brand','').strip())/1e6:.1f}M")

            if (idx + 1) % 200 == 0:
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

    still_missing = sum(1 for r in rows if not r.get("brand", "").strip())
    print(f"\nDone! Found {found} brands. Still missing: {still_missing}")


if __name__ == "__main__":
    asyncio.run(main())
