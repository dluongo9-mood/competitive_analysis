"""
Amazon PLP Scraper — Hemp-derived THC & CBD Gummies

Scrapes Amazon search results pages using Playwright to extract product
listings. Supports multiple search queries and pagination.

Outputs: amazon_gummies_plp.csv

Run:
    python3 scrape_amazon_plp.py
"""

import asyncio
import csv
import json
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright

OUTPUT_CSV = "amazon_gummies_plp.csv"

SEARCH_QUERIES = [
    "THC gummies",
    "delta 9 gummies",
    "delta 8 gummies",
    "hemp gummies THC",
    "CBD THC gummies",
    "hemp derived THC edibles",
    "delta 9 THC edibles",
    "full spectrum hemp gummies",
    "microdose THC gummies",
    "THC sleep gummies",
    "THC relaxation gummies",
]

EXTRACT_JS = """
() => {
    const items = [];
    const cards = document.querySelectorAll('[data-asin]');

    for (const card of cards) {
        const asin = card.getAttribute('data-asin');
        if (!asin || asin.length < 5) continue;

        // Skip ads/widgets without product info
        const titleEl = card.querySelector('h2 a span, h2 span');
        if (!titleEl) continue;

        const title = titleEl.textContent.trim();
        if (!title) continue;

        // Price
        const priceWhole = card.querySelector('.a-price .a-price-whole');
        const priceFraction = card.querySelector('.a-price .a-price-fraction');
        let price = null;
        if (priceWhole) {
            price = priceWhole.textContent.replace(/[^0-9]/g, '');
            if (priceFraction) price += '.' + priceFraction.textContent.replace(/[^0-9]/g, '');
            else price += '.00';
        }

        // List price (was price)
        const listPriceEl = card.querySelector('.a-price.a-text-price .a-offscreen');
        const listPrice = listPriceEl ? listPriceEl.textContent.trim() : '';

        // Unit price
        const unitEl = card.querySelector('[data-a-color="secondary"] .a-size-base.a-color-secondary, .a-price + .a-size-base');
        const unitPrice = unitEl ? unitEl.textContent.trim() : '';

        // Rating
        const ratingEl = card.querySelector('.a-icon-star-small .a-icon-alt, .a-icon-star-mini .a-icon-alt');
        let rating = null;
        if (ratingEl) {
            const m = ratingEl.textContent.match(/([\d.]+)/);
            if (m) rating = m[1];
        }

        // Review count — from aria-label on review link, with fallbacks
        let reviewCount = null;
        const revLink = card.querySelector('a[href*="#customerReviews"]');
        if (revLink) {
            const aria = revLink.getAttribute('aria-label') || '';
            const m = aria.match(/([\d,]+)/);
            if (m) reviewCount = m[1].replace(/,/g, '');
            else {
                const txt = revLink.textContent.replace(/[^0-9]/g, '');
                if (txt) reviewCount = txt;
            }
        }
        if (!reviewCount) {
            const csaContainer = card.querySelector('[data-csa-c-content-id*="customer-ratings-count"] a');
            if (csaContainer) {
                const aria = csaContainer.getAttribute('aria-label') || '';
                const m = aria.match(/([\d,]+)/);
                if (m) reviewCount = m[1].replace(/,/g, '');
            }
        }

        // Bought past month
        const boughtEl = card.querySelector('.a-row.a-size-base .a-size-base.a-color-secondary');
        let boughtPastMonth = '';
        if (boughtEl && /bought/i.test(boughtEl.textContent)) {
            boughtPastMonth = boughtEl.textContent.trim();
        }

        // Badges
        const isBestSeller = !!card.querySelector('[data-component-type="s-status-badge-component"]');
        const isAmazonChoice = !!card.querySelector('.a-badge-text');
        const isSponsored = !!card.querySelector('.a-color-secondary:has(> .a-text-bold)') ||
                           !!card.querySelector('[data-component-type="sp-sponsored-result"]');
        const isPrime = !!card.querySelector('.a-icon-prime');

        // Coupon
        const couponEl = card.querySelector('.s-coupon-unclipped .a-color-base, [data-component-type="s-coupon-component"]');
        const coupon = couponEl ? couponEl.textContent.trim() : '';

        // Form factor / count from title
        let formFactor = '';
        const titleLower = title.toLowerCase();
        if (/gummies|gummy/i.test(titleLower)) formFactor = 'Gummy';
        else if (/capsule/i.test(titleLower)) formFactor = 'Capsule';
        else if (/tincture|drops?|oil/i.test(titleLower)) formFactor = 'Tincture';
        else if (/chocolate|bar/i.test(titleLower)) formFactor = 'Edible';

        // Count
        const countMatch = title.match(/(\d+)\s*(?:count|ct|pack|gummies|pcs|pieces)/i);
        const count = countMatch ? countMatch[0] : '';

        // Image
        const imgEl = card.querySelector('img.s-image');
        const image = imgEl ? imgEl.src : '';

        // URL
        const linkEl = card.querySelector('h2 a');
        const url = linkEl ? 'https://www.amazon.com' + linkEl.getAttribute('href').split('?')[0] : '';

        items.push({
            asin, title, formFactor, count, price, listPrice, unitPrice,
            rating, reviewCount: reviewCount || '',
            isBestSeller: String(isBestSeller),
            isAmazonChoice: String(isAmazonChoice),
            isSponsored: String(isSponsored),
            isPrime: String(isPrime),
            coupon, boughtPastMonth,
            image, url
        });
    }
    return items;
}
"""


def load_existing():
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            return {r["asin"]: r for r in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


def save_results(all_products):
    fields = [
        "asin", "title", "formFactor", "count", "price", "listPrice",
        "unitPrice", "rating", "reviewCount", "isBestSeller", "isAmazonChoice",
        "isSponsored", "isPrime", "coupon", "boughtPastMonth", "searchQuery",
        "image", "url",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for p in all_products:
            writer.writerow({k: p.get(k, "") for k in fields})


async def scrape_query(page, query, existing_asins):
    """Scrape all pages for a given search query."""
    products = []
    base_url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}"

    for page_num in range(1, 20):  # Up to 20 pages
        url = f"{base_url}&page={page_num}" if page_num > 1 else base_url
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2000)

            items = await page.evaluate(EXTRACT_JS)
            if not items:
                print(f"    Page {page_num}: no results, stopping")
                break

            new = 0
            for item in items:
                if item["asin"] not in existing_asins:
                    item["searchQuery"] = query
                    products.append(item)
                    existing_asins.add(item["asin"])
                    new += 1

            print(f"    Page {page_num}: {len(items)} items, {new} new")

            # Check for "next" button
            has_next = await page.evaluate("""
                () => !!document.querySelector('.s-pagination-next:not(.s-pagination-disabled)')
            """)
            if not has_next:
                print(f"    No more pages")
                break

            await page.wait_for_timeout(1500)

        except Exception as e:
            print(f"    Page {page_num} error: {e}")
            break

    return products


async def main():
    existing = load_existing()
    existing_asins = set(existing.keys())
    all_products = list(existing.values())
    print(f"Existing products: {len(all_products)}")

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

        # Warm up session
        print("Establishing session...")
        await page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2000)
        print("Session ready.\n")

        for query in SEARCH_QUERIES:
            print(f"  Searching: {query}")
            products = await scrape_query(page, query, existing_asins)
            all_products.extend(products)
            print(f"  → {len(products)} new products\n")
            save_results(all_products)

        await browser.close()

    # Final save
    save_results(all_products)
    print(f"\nDone! {len(all_products):,} total products → {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
