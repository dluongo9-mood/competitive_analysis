#!/usr/bin/env python3
"""Scout the 5 stuck brand sites to find valid THCA product URLs and understand their add-to-cart DOM."""

import asyncio
from playwright.async_api import async_playwright


async def dismiss_age_gate(page):
    for text in ["YES", "Yes", "I'm over 21", "ENTER", "Enter", "Yep, let's go"]:
        for tag in ["button", "a", "span", "div"]:
            try:
                loc = page.locator(f"{tag}:has-text('{text}')").first
                if await loc.is_visible(timeout=500):
                    await loc.click(timeout=2000)
                    await page.wait_for_timeout(2000)
                    return
            except Exception:
                continue
    try:
        await page.evaluate("""() => {
            ['age_verified','ageVerified','verified','isAdult','over21']
                .forEach(k => { localStorage.setItem(k, 'true'); });
            document.cookie = 'age_verified=true;path=/;max-age=86400';
        }""")
    except Exception:
        pass


async def scout(browser, name, url, info):
    print(f"\n{'='*60}")
    print(f"Scouting: {name} — {url}")
    print(f"{'='*60}")
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        await dismiss_age_gate(page)
        await page.wait_for_timeout(1000)

        # Find product links on the page
        products = await page.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href*="/product"], a[href*="/products/"]');
                const seen = new Set();
                const results = [];
                for (const a of links) {
                    const href = a.href;
                    const text = (a.innerText || '').trim().substring(0, 80);
                    if (!seen.has(href) && text.length > 2) {
                        seen.add(href);
                        results.push({href, text});
                    }
                }
                return results.slice(0, 10);
            }
        """)
        print(f"  Products found: {len(products)}")
        for p in products:
            thca_flag = " <-- THCA" if "thca" in (p['text'] + p['href']).lower() else ""
            print(f"    {p['text'][:50]:50} {p['href']}{thca_flag}")

        # Get add-to-cart button info
        atc_info = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll(
                    'button.single_add_to_cart_button, button[name="add-to-cart"], ' +
                    'button[name="add"], form.cart button, ' +
                    'button:not([disabled])[type="submit"]'
                );
                return Array.from(btns).slice(0, 5).map(b => ({
                    tag: b.tagName,
                    text: (b.innerText || b.value || '').trim().substring(0, 50),
                    name: b.name,
                    classes: b.className.substring(0, 80),
                    disabled: b.disabled,
                }));
            }
        """)
        if atc_info:
            print(f"\n  Add-to-cart buttons:")
            for b in atc_info:
                print(f"    {b}")

        # Get variant selectors
        variants = await page.evaluate("""
            () => {
                const selects = document.querySelectorAll('select');
                const results = [];
                for (const s of selects) {
                    const opts = Array.from(s.options).map(o => o.text.trim()).filter(t => t);
                    results.push({
                        name: s.name,
                        id: s.id,
                        options: opts.slice(0, 8),
                    });
                }
                return results;
            }
        """)
        if variants:
            print(f"\n  Select dropdowns:")
            for v in variants:
                print(f"    name={v['name']} id={v['id']} options={v['options']}")

        # For BigCommerce/enjoy: check for checkboxes
        checkboxes = await page.evaluate("""
            () => {
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                return Array.from(cbs).map(cb => ({
                    name: cb.name,
                    id: cb.id,
                    required: cb.required,
                    label: cb.parentElement?.innerText?.trim()?.substring(0, 80) || '',
                }));
            }
        """)
        if checkboxes:
            print(f"\n  Checkboxes:")
            for cb in checkboxes:
                print(f"    name={cb['name']} id={cb['id']} required={cb['required']} label={cb['label']}")

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        await ctx.close()


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False, slow_mo=300)

    sites = [
        ("iDelta", "https://delta8vapeoil.com/product/idelta-thca-flower/",
         "Need to find variant selectors"),
        ("Hempbombs", "https://www.hempbombs.com/thca/",
         "Need to find valid THCA product URL"),
        ("Mystic Labs", "https://mysticlabsd8.com/thca/",
         "Need non-bundle THCA product"),
        ("enjoy", "https://enjoyhemp.co/3-5g-thca-flower-blue-dream-for-cloud-nine-hybrid/",
         "Need to find privacy checkbox"),
        ("ELYXR", "https://www.elyxr.com/collections/thca-products/",
         "Need valid THCA product URL"),
    ]

    for name, url, info in sites:
        await scout(browser, name, url, info)

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
