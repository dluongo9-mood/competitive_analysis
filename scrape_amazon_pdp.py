"""
Amazon PDP Scraper — Brand extraction for THC/CBD gummies

Fetches /dp/{ASIN} via same-origin fetch() inside a Playwright browser
and extracts brand name from #bylineInfo.

Outputs: amazon_brands.csv (asin, brand)
Supports resume — skips ASINs already scraped.

Run:
    python3 scrape_amazon_pdp.py
"""

import asyncio
import csv
import time

from playwright.async_api import async_playwright

AMAZON_CSV = "amazon_gummies_plp.csv"
OUTPUT_CSV = "amazon_brands.csv"
BATCH_SIZE = 10
TIMEOUT_MS = 15000

EXTRACT_JS = """
(asins) => {
    const concurrency = 2;
    const results = [];
    let idx = 0, finished = 0;

    return new Promise(resolve => {
        function next() {
            while (idx < asins.length && (idx - finished) < concurrency) {
                const asin = asins[idx++];
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 15000);

                fetch('/dp/' + asin, {
                    headers: { 'Accept': 'text/html' },
                    signal: controller.signal,
                })
                .then(r => { clearTimeout(timer); return r.text(); })
                .then(html => {
                    if (html.length < 5000) {
                        results.push({ asin, brand: null });
                        return;
                    }
                    const doc = new DOMParser().parseFromString(html, 'text/html');

                    // Brand from bylineInfo
                    const byline = doc.querySelector('#bylineInfo, a#bylineInfo');
                    let brand = null;
                    if (byline) {
                        brand = byline.textContent
                            .replace(/Visit the|Store|Brand:|by/gi, '')
                            .replace(/\\s+/g, ' ')
                            .trim() || null;
                    }

                    doc.documentElement.remove();
                    results.push({ asin, brand });
                })
                .catch(() => {
                    clearTimeout(timer);
                    results.push({ asin, brand: null });
                })
                .finally(() => {
                    finished++;
                    if (finished === asins.length) resolve(results);
                    else next();
                });
            }
        }
        next();
    });
}
"""


def load_asins():
    with open(AMAZON_CSV, newline="", encoding="utf-8") as f:
        return [r["asin"] for r in csv.DictReader(f) if r.get("asin")]


def load_existing():
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            return {r["asin"]: r for r in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


def save_results(results):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["asin", "brand"])
        writer.writeheader()
        for asin in sorted(results.keys()):
            writer.writerow({
                "asin": asin,
                "brand": results[asin].get("brand") or "",
            })


async def main():
    all_asins = load_asins()
    existing = load_existing()
    remaining = [a for a in all_asins if a not in existing or not existing[a].get("brand")]

    print(f"Total ASINs: {len(all_asins):,}")
    print(f"Already scraped: {len(existing):,}")
    print(f"Remaining: {len(remaining):,}")

    if not remaining:
        print("All done!")
        return

    results = {}
    for asin, row in existing.items():
        results[asin] = {"brand": row.get("brand") or None}

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

        print("Establishing session…")
        await page.goto("https://www.amazon.com/s?k=hemp+gummies",
                        wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2000)
        print("Session ready.\n")

        total_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE
        start_time = time.time()
        brands_found = 0

        for batch_num in range(total_batches):
            batch_start = batch_num * BATCH_SIZE
            batch_asins = remaining[batch_start:batch_start + BATCH_SIZE]

            try:
                batch_results = await page.evaluate(EXTRACT_JS, batch_asins)
            except Exception as e:
                print(f"  Batch {batch_num+1} error: {e}")
                save_results(results)
                continue

            bf = 0
            for r in batch_results:
                asin = r["asin"]
                brand = r.get("brand")
                results[asin] = {"brand": brand}
                if brand:
                    brands_found += 1
                    bf += 1

            done = batch_start + len(batch_asins)
            elapsed = time.time() - start_time
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(remaining) - done) / rate if rate > 0 else 0

            print(f"  Batch {batch_num+1}/{total_batches}  |  "
                  f"+{bf} brands  |  "
                  f"{done:,}/{len(remaining):,}  |  "
                  f"total: {brands_found} brands  |  "
                  f"ETA {eta:.0f}s")

            if batch_num % 5 == 0:
                save_results(results)

            await asyncio.sleep(2)

        await browser.close()

    save_results(results)
    total_brands = sum(1 for r in results.values() if r.get("brand"))
    print(f"\nDone! {total_brands:,} brands out of {len(results):,} ASINs")


if __name__ == "__main__":
    asyncio.run(main())
