"""Deeper inspection of Weedmaps product card DOM."""
import asyncio
from playwright.async_api import async_playwright

INSPECT_JS = """
() => {
    // Find all links that go to products
    const productLinks = [...document.querySelectorAll('a')].filter(a => {
        const href = a.href || '';
        return href.includes('/products/') || href.includes('/product/');
    });

    const results = [];
    for (const link of productLinks.slice(0, 5)) {
        // Walk up to find the card container
        let card = link;
        for (let i = 0; i < 8; i++) {
            if (card.parentElement) card = card.parentElement;
        }

        results.push({
            linkHref: link.href,
            linkText: link.innerText.substring(0, 100),
            // Card info
            cardTag: card.tagName,
            cardClass: (card.className || '').toString().substring(0, 200),
            cardHTML: card.outerHTML.substring(0, 1500),
        });
    }

    // Also check __NEXT_DATA__ more thoroughly
    const nd = document.getElementById('__NEXT_DATA__');
    let nextDataInfo = null;
    if (nd) {
        try {
            const data = JSON.parse(nd.textContent);
            // Recursively find arrays with product-like objects
            function findProducts(obj, path) {
                if (!obj || typeof obj !== 'object') return [];
                let found = [];
                if (Array.isArray(obj)) {
                    if (obj.length > 0 && obj[0] && (obj[0].name || obj[0].title || obj[0].productName)) {
                        found.push({path, count: obj.length, sample: JSON.stringify(obj[0]).substring(0, 500)});
                    }
                } else {
                    for (const [k, v] of Object.entries(obj)) {
                        if (path.split('.').length < 6) {
                            found = found.concat(findProducts(v, path + '.' + k));
                        }
                    }
                }
                return found;
            }
            nextDataInfo = findProducts(data, 'root');
        } catch(e) {
            nextDataInfo = {error: e.message};
        }
    }

    // Check for any API-like script tags or data attributes
    const dataAttrs = [...document.querySelectorAll('[data-listing], [data-product], [data-item]')].map(el => ({
        tag: el.tagName,
        attrs: [...el.attributes].map(a => a.name + '=' + a.value.substring(0, 50)).join(', '),
    }));

    return {products: results, nextDataProducts: nextDataInfo, dataAttrElements: dataAttrs.slice(0, 5)};
}
"""

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()

        url = "https://weedmaps.com/search?q=THC+gummies&lat=34.0522&lng=-118.2437&type=product"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        info = await page.evaluate(INSPECT_JS)

        import json
        print("=== Product link cards (first 3) ===")
        for p in info["products"][:3]:
            print(f"\nLink: {p['linkHref'][:80]}")
            print(f"Card HTML:\n{p['cardHTML'][:800]}\n---")

        print("\n=== __NEXT_DATA__ product arrays ===")
        for item in (info["nextDataProducts"] or []):
            print(f"  Path: {item['path']}, Count: {item['count']}")
            print(f"  Sample: {item['sample'][:300]}\n")

        print(f"\n=== Data attribute elements: {info['dataAttrElements']}")

        await browser.close()

asyncio.run(main())
