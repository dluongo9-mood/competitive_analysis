"""
Weedmaps Dispensary Product Scraper — THC/CBD Gummies

Scrapes Weedmaps product search results across major US markets
using Playwright to extract product listings.

Outputs: weedmaps_gummies.csv

Run:
    python3 scrape_weedmaps.py
"""

import asyncio
import csv
import json
import re
import time

from playwright.async_api import async_playwright

OUTPUT_CSV = "weedmaps_gummies.csv"

# Major cannabis markets to search
MARKETS = [
    ("Los Angeles", 34.0522, -118.2437),
    ("New York", 40.7128, -74.0060),
    ("Denver", 39.7392, -104.9903),
    ("Portland", 45.5155, -122.6789),
    ("Seattle", 47.6062, -122.3321),
    ("Chicago", 41.8781, -87.6298),
    ("San Francisco", 37.7749, -122.4194),
    ("Detroit", 42.3314, -83.0458),
    ("Phoenix", 33.4484, -112.0740),
    ("Las Vegas", 36.1699, -115.1398),
]

SEARCH_QUERIES = [
    "THC gummies",
    "delta 9 gummies",
    "CBD gummies",
    "edible gummies",
]

MAX_PAGES_PER_SEARCH = 10  # Cap at 10 pages (300 products) per search
PAGE_DELAY = 2  # seconds between pages

FIELDS = [
    "productName", "brand", "price", "thcContent", "cbdContent",
    "category", "rating", "reviewCount", "dispensaryCount",
    "market", "searchQuery", "url", "image",
]

EXTRACT_JS = """
() => {
    const products = [];
    const seen = new Set();

    // Weedmaps uses styled-components; find product cards via product links
    // Cards are inside a grid with data-testid="serp-grid"
    const grid = document.querySelector('[data-testid="serp-grid"]');
    const linkEls = grid
        ? grid.querySelectorAll('a[href*="/products/"]')
        : document.querySelectorAll('a[href*="/products/"]');

    for (const link of linkEls) {
        const url = link.href;
        if (!url || seen.has(url)) continue;
        seen.add(url);

        // Walk up to find the individual card wrapper
        // Stop when the parent contains MORE than one product link
        let card = link;
        for (let i = 0; i < 10; i++) {
            const parent = card.parentElement;
            if (!parent) break;
            const linksInParent = parent.querySelectorAll('a[href*="/products/"]');
            if (linksInParent.length > 1) break;  // parent has multiple products = grid
            card = parent;
        }

        const fullText = card.innerText || '';
        const rawLines = fullText.split('\\n');
        const lines = [];
        for (const l of rawLines) { const t = l.trim(); if (t) lines.push(t); }

        // Parse card text — typical structure:
        // "-30%", "GUMMIES", "1 mi", "Product Name Here",
        // "100mg THC", "BRAND", "4.9 star average rating from X reviews",
        // "4.9", "(1,029)", "$21.00", "$30.00"
        let name = null, brand = null, price = null;
        let thcContent = null, cbdContent = null;
        let rating = null, reviewCount = null, category = null;

        // Extract name from URL slug as most reliable source
        const slugMatch = url.match(/\\/products\\/(.+?)(?:\\?|$)/);
        if (slugMatch) {
            const words = slugMatch[1].replace(/-/g, ' ').split(' ');
            const caps = [];
            for (const w of words) { caps.push(w.charAt(0).toUpperCase() + w.slice(1)); }
            name = caps.join(' ');
        }

        // Also try to find name in card text — look for the longest line
        // that isn't a category, price, distance, rating, or THC content
        let candidateName = null;
        for (const line of lines) {
            // Product name: longest meaningful line
            if (line.length > 15 && line.length < 120 && !line.startsWith('$') &&
                !line.includes('star average') && !/^\\d+(\\.\\d)?\\s*mi$/.test(line) &&
                !/^\\d+(\\.\\d)?$/.test(line) && !/^\\(/.test(line) &&
                !/^-?\\d+%$/.test(line) && !/mg\\s*(THC|CBD)/i.test(line) &&
                !['GUMMIES','PODS','FLOWER','VAPES','EDIBLES','CONCENTRATES','PREROLLS'].includes(line)) {
                if (!candidateName || line.length > candidateName.length) {
                    candidateName = line;
                }
            }

            // Category
            if (['GUMMIES','PODS','FLOWER','VAPES','EDIBLES','CONCENTRATES','PREROLLS'].includes(line)) {
                category = line;
            }

            // THC content
            const thcMatch = line.match(/(\\d+(?:\\.\\d+)?\\s*mg)\\s*THC/i);
            if (thcMatch) thcContent = thcMatch[1];

            // CBD content
            const cbdMatch = line.match(/(\\d+(?:\\.\\d+)?\\s*mg)\\s*CBD/i);
            if (cbdMatch) cbdContent = cbdMatch[1];

            // Price
            const priceMatch = line.match(/^\\$(\\d+(?:\\.\\d+)?)$/);
            if (priceMatch && !price) price = priceMatch[1];

            // Rating from "X.X star average" text
            const ratingMatch = line.match(/(\\d\\.\\d)\\s*star\\s*average/i);
            if (ratingMatch) rating = ratingMatch[1];

            // Review count from "(1,234)" format
            const reviewMatch = line.match(/^\\(([\\d,]+)\\)$/);
            if (reviewMatch) reviewCount = reviewMatch[1].replace(/,/g, '');
        }
        if (candidateName) name = candidateName;

        // Brand: look for all-caps short text or text after THC content line
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            // Brand is often a short all-caps or title-case word after THC line
            if (line.length >= 2 && line.length <= 30 &&
                !line.startsWith('$') && !line.startsWith('(') &&
                !line.includes('star') && !line.includes('mi') &&
                !/^\\d/.test(line) &&
                !['GUMMIES','PODS','FLOWER','VAPES','EDIBLES','CONCENTRATES','PREROLLS'].includes(line)) {
                // Check if previous line was THC/CBD content
                if (i > 0 && /mg/i.test(lines[i-1])) {
                    brand = line;
                    break;
                }
            }
        }

        if (name) {
            products.push({
                productName: name,
                brand: brand,
                price: price,
                thcContent: thcContent,
                cbdContent: cbdContent,
                category: category,
                rating: rating,
                reviewCount: reviewCount,
                url: url,
                image: null,
            });
        }
    }

    return products;
}
"""


def load_existing():
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def save_results(products):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)


async def scrape_search(page, query, market_name, lat, lng):
    """Scrape product search results for a query in a market."""
    products = []
    base_url = f"https://weedmaps.com/search?q={query.replace(' ', '+')}&lat={lat}&lng={lng}&type=product"

    for page_num in range(1, MAX_PAGES_PER_SEARCH + 1):
        url = f"{base_url}&page={page_num}" if page_num > 1 else base_url
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3000)

            items = await page.evaluate(EXTRACT_JS)
            if not items:
                print(f"      Page {page_num}: no results, stopping")
                break

            for item in items:
                item["market"] = market_name
                item["searchQuery"] = query
                products.append(item)

            print(f"      Page {page_num}: {len(items)} products")

            if len(items) < 20:  # Partial page = last page
                break

        except Exception as e:
            print(f"      Page {page_num} error: {e}")
            break

        await asyncio.sleep(PAGE_DELAY)

    return products


async def main():
    seen = set()
    all_products = []

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
        await page.goto("https://weedmaps.com", wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3000)
        print("Session ready.\n")

        for market_name, lat, lng in MARKETS:
            print(f"  Market: {market_name}")
            for query in SEARCH_QUERIES:
                print(f"    Query: {query}")
                products = await scrape_search(page, query, market_name, lat, lng)

                new = 0
                for p in products:
                    # Dedup by product name + brand
                    key = (p.get("productName", ""), p.get("brand", ""))
                    if key not in seen and key[0]:
                        seen.add(key)
                        all_products.append(p)
                        new += 1
                print(f"    → {new} new products\n")

            # Save after each market
            save_results(all_products)

        await browser.close()

    save_results(all_products)
    print(f"\nDone! {len(all_products):,} products → {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
