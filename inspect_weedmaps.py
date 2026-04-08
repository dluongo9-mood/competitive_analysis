"""Quick script to inspect Weedmaps search page DOM structure."""
import asyncio
from playwright.async_api import async_playwright

INSPECT_JS = """
() => {
    const info = {
        title: document.title,
        url: window.location.href,
        bodyText: document.body.innerText.substring(0, 3000),
        productCards: document.querySelectorAll('[data-testid="product-card"]').length,
        anyCards: document.querySelectorAll('[class*="ProductCard"], [class*="product-card"]').length,
        allProductLinks: [...document.querySelectorAll('a')].filter(a => a.href.includes('/product')).length,
        nextData: !!document.getElementById('__NEXT_DATA__'),
    };
    // Find product-like elements by class
    const allEls = document.querySelectorAll('*');
    const productEls = [...allEls].filter(el => {
        const cl = (el.className || '').toString().toLowerCase();
        return cl.includes('product') || cl.includes('listing') || cl.includes('menu-item');
    });
    info.productElSamples = productEls.slice(0, 15).map(el => ({
        tag: el.tagName,
        class: el.className.toString().substring(0, 100),
        text: el.innerText.substring(0, 80),
    }));

    // Check for __NEXT_DATA__
    const nd = document.getElementById('__NEXT_DATA__');
    if (nd) {
        try {
            const data = JSON.parse(nd.textContent);
            info.nextDataKeys = Object.keys(data.props?.pageProps || {});
            const pp = data.props?.pageProps;
            // Look for product arrays
            for (const [k, v] of Object.entries(pp || {})) {
                if (Array.isArray(v) && v.length > 0) {
                    info['array_' + k] = v.length + ' items, first keys: ' + Object.keys(v[0]).join(', ');
                }
            }
        } catch(e) {
            info.nextDataError = e.message;
        }
    }

    // Check for any JSON script tags
    const scripts = document.querySelectorAll('script[type="application/json"]');
    info.jsonScripts = scripts.length;

    return info;
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
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        info = await page.evaluate(INSPECT_JS)

        import json
        for k, v in info.items():
            if k == "bodyText":
                print(f"\n--- Body text (first 2000) ---\n{v[:2000]}")
            elif k == "productElSamples":
                print(f"\n--- Product-like elements ---")
                for el in v:
                    print(f"  <{el['tag']} class='{el['class']}'> {el['text'][:60]}")
            else:
                print(f"{k}: {v}")

        await browser.close()

asyncio.run(main())
