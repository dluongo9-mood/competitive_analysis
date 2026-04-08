"""
Faire.com THC/CBD Gummy Scraper — API-based via Playwright fetch()

Outputs: faire_gummies.csv

Run:
    python3 scrape_faire.py
"""

import asyncio
import csv
import json

from playwright.async_api import async_playwright

QUERIES = [
    "THC gummies",
    "delta 9 gummies",
    "delta 8 gummies",
    "CBD gummies",
    "hemp gummies",
    "hemp edibles",
]

PAGE_SIZE  = 60
PAGE_DELAY = 0.5
OUTPUT_CSV = "faire_gummies.csv"

FIELDS = [
    "productToken", "name", "brand", "brandToken", "retailPrice", "currency",
    "rating", "reviewCount", "badge", "isNew", "isBestseller", "isPromoted",
    "caseSize", "minOrderQty", "availableUnits", "brandCode", "basedIn",
    "hasActivePromo", "image", "url", "searchQuery",
]

FETCH_PAGE_JS = """
(args) => {
    const { query, pageNumber, pageSize } = args;
    return fetch('/api/v3/layout/search-product-tiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filter_keys: [],
            query: query,
            pagination_data: { page_number: pageNumber, page_size: pageSize },
            container_name: 'search_results_grid',
            referrer_type: 'NONE',
        })
    })
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => ({
        pagination: data.pagination_data || {},
        tiles: data.product_tiles || [],
        brands: data.brands_by_token || {},
    }));
}
"""


def parse_tile(tile, brands, query):
    p = tile.get("product", {})
    brand_token = p.get("brand_token", "")
    brand = brands.get(brand_token, {})

    retail = tile.get("min_option_retail_price", {})
    price_cents = retail.get("amount_cents")
    price = price_cents / 100.0 if price_cents else None

    badge_list = tile.get("badge_list", {}).get("badges", [])
    badges = [b["style"]["badge_message"] for b in badge_list
              if b.get("display_to_user") and b.get("style", {}).get("badge_message")]

    qa = tile.get("quick_add", {})
    qa_opt = qa.get("quick_add_option", {})

    best_img = tile.get("best_image", {})
    image_url = best_img.get("optimized_url") or best_img.get("url")

    product_url = "https://www.faire.com/product/" + p["token"] if p.get("token") else None

    return {
        "productToken":   p.get("token"),
        "name":           p.get("name"),
        "brand":          brand.get("name"),
        "brandToken":     brand_token,
        "retailPrice":    price,
        "currency":       retail.get("currency", "USD"),
        "rating":         p.get("avg_brand_review_rating"),
        "reviewCount":    p.get("brand_review_count"),
        "badge":          ", ".join(badges) if badges else None,
        "isNew":          1 if p.get("is_new") else 0,
        "isBestseller":   1 if p.get("maker_best_seller") else 0,
        "isPromoted":     1 if p.get("is_promoted") else 0,
        "caseSize":       qa_opt.get("option_unit_multiplier"),
        "minOrderQty":    qa_opt.get("option_min_order_quantity"),
        "availableUnits": qa_opt.get("option_available_units"),
        "brandCode":      tile.get("min_option_brand_code"),
        "basedIn":        tile.get("based_in_country"),
        "hasActivePromo": 1 if tile.get("has_active_brand_promo") else 0,
        "image":          image_url,
        "url":            product_url,
        "searchQuery":    query,
    }


async def scrape_query(page, query):
    products = []
    print(f"  [{query}] page 1 …", end=" ", flush=True)
    data = await page.evaluate(FETCH_PAGE_JS, {
        "query": query, "pageNumber": 1, "pageSize": PAGE_SIZE
    })
    pag = data["pagination"]
    page_count = pag.get("page_count", 1)
    total = pag.get("total_results", 0)
    print(f"{len(data['tiles'])} products  (total: {total}, pages: {page_count})")

    for tile in data["tiles"]:
        products.append(parse_tile(tile, data["brands"], query))

    for pg in range(2, page_count + 1):
        await asyncio.sleep(PAGE_DELAY)
        print(f"  [{query}] page {pg}/{page_count} …", end=" ", flush=True)
        try:
            data = await page.evaluate(FETCH_PAGE_JS, {
                "query": query, "pageNumber": pg, "pageSize": PAGE_SIZE
            })
            count = len(data["tiles"])
            print(f"{count} products")
            for tile in data["tiles"]:
                products.append(parse_tile(tile, data["brands"], query))
            if count == 0:
                break
        except Exception as e:
            print(f"error: {e}")
            break

    return products


async def main():
    seen = set()
    all_products = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()

        print("Establishing session…")
        await page.goto(
            "https://www.faire.com/search?q=THC+gummies",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_timeout(3000)
        print("Session ready.\n")

        for query in QUERIES:
            print(f"  Query: {query}")
            products = await scrape_query(page, query)

            new = 0
            for p in products:
                token = p["productToken"]
                if token and token not in seen:
                    seen.add(token)
                    all_products.append(p)
                    new += 1
            print(f"  → {new} new products\n")

        await browser.close()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_products)

    print(f"\nDone! {len(all_products):,} products → {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
