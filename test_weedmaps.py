"""Quick test of updated Weedmaps extraction JS."""
import asyncio
import json
from playwright.async_api import async_playwright

# Copy EXTRACT_JS from scrape_weedmaps.py
import importlib.util
spec = importlib.util.spec_from_file_location("wm", "scrape_weedmaps.py")
wm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm)

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

        items = await page.evaluate(wm.EXTRACT_JS)
        print(f"\nExtracted {len(items)} products\n")

        for i, item in enumerate(items[:10]):
            print(f"[{i+1}] {item.get('productName', 'NO NAME')}")
            print(f"    Brand: {item.get('brand')} | Price: ${item.get('price')} | THC: {item.get('thcContent')}")
            print(f"    Rating: {item.get('rating')} | Reviews: {item.get('reviewCount')} | Category: {item.get('category')}")
            print(f"    URL: {item.get('url', '')[:80]}")
            print()

        await browser.close()

asyncio.run(main())
