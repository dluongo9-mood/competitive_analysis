#!/usr/bin/env python3
"""
Test the 5 stuck brands in a visible (non-headless) browser with
slower, more human-like interactions and brand-specific logic.
"""

import asyncio
import csv
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright, Page

SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

TEST_ZIPS = [
    {"state": "Ohio", "abbreviation": "OH", "zip": "43215"},
    {"state": "Texas", "abbreviation": "TX", "zip": "78701"},
]

BRANDS_TO_TEST = [
    {
        "name": "iDelta",
        "base_url": "https://delta8vapeoil.com",
        "product_url": "https://delta8vapeoil.com/product/idelta-thca-flower/",
        "platform": "woocommerce",
        "brightfield_rank": 4,
        "brightfield_funnel_pct": 25.6,
    },
    {
        "name": "Hempbombs",
        "base_url": "https://www.hempbombs.com",
        "product_url": "https://www.hempbombs.com/product/thca-gummies/",
        "platform": "woocommerce",
        "brightfield_rank": 12,
        "brightfield_funnel_pct": 14.1,
    },
    {
        "name": "Mystic Labs",
        "base_url": "https://mysticlabsd8.com",
        "product_url": "https://mysticlabsd8.com/thca-gummies/",
        "platform": "magento",
        "brightfield_rank": 9,
        "brightfield_funnel_pct": 16.1,
    },
    {
        "name": "enjoy",
        "base_url": "https://enjoyhemp.co",
        "product_url": "https://enjoyhemp.co/3-5g-thca-flower-blue-dream-for-cloud-nine-hybrid/",
        "platform": "bigcommerce",
        "brightfield_rank": 19,
        "brightfield_funnel_pct": 11.5,
    },
    {
        "name": "ELYXR",
        "base_url": "https://www.elyxr.com",
        "product_url": "https://www.elyxr.com/products/thca-live-resin-disposable-2g/",
        "platform": "shopify",
        "brightfield_rank": 23,
        "brightfield_funnel_pct": 11.0,
    },
]


async def screenshot(page: Page, name: str, label: str):
    safe = name.lower().replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SCREENSHOTS_DIR, f"{safe}_visible_{label}_{ts}.png")
    try:
        await page.screenshot(path=path, full_page=False)
        print(f"    [screenshot] {path}")
    except Exception:
        pass


async def dismiss_age_gate(page: Page):
    """Aggressively dismiss age gates with multiple strategies."""
    # Strategy 1: Click known buttons
    for text in ["YES", "Yes", "Yep, let's go", "I'm over 21", "ENTER", "Enter",
                  "I am 21 or older", "Verify", "VERIFY", "Continue", "I agree"]:
        for tag in ["button", "a", "span", "div"]:
            try:
                loc = page.locator(f"{tag}:has-text('{text}')").first
                if await loc.is_visible(timeout=500):
                    await loc.click(timeout=2000)
                    print(f"    [age] Clicked {tag}:'{text}'")
                    await page.wait_for_timeout(2000)
                    return True
            except Exception:
                continue

    # Strategy 2: JS click on modal buttons
    try:
        clicked = await page.evaluate("""
            () => {
                const overlays = document.querySelectorAll(
                    '[class*="age"], [class*="verify"], [class*="gate"], [class*="modal"], ' +
                    '[id*="age"], [id*="verify"], dialog, [role="dialog"]'
                );
                const allFixed = [...document.querySelectorAll('div')].filter(el => {
                    const s = getComputedStyle(el);
                    return (s.position === 'fixed' || s.position === 'absolute') && parseInt(s.zIndex) > 50;
                });
                const containers = [...overlays, ...allFixed];
                for (const c of containers) {
                    if (!c.innerText || !c.innerText.toLowerCase().includes('21')) continue;
                    const btns = c.querySelectorAll('button, a, [role="button"], span[onclick]');
                    for (const btn of btns) {
                        const t = btn.innerText.toLowerCase().trim();
                        if (['yes', 'enter', 'verify', 'confirm', 'agree', 'continue'].some(w => t.includes(w)) &&
                            !['no', 'exit', 'leave'].some(w => t === w)) {
                            btn.click();
                            return t;
                        }
                    }
                }
                return null;
            }
        """)
        if clicked:
            print(f"    [age] JS dismissed: '{clicked}'")
            await page.wait_for_timeout(2000)
            return True
    except Exception:
        pass

    # Strategy 3: localStorage
    try:
        await page.evaluate("""
            () => {
                ['age_verified','ageVerified','age-verified','agegate','verified','isAdult','over21']
                    .forEach(k => { localStorage.setItem(k, 'true'); localStorage.setItem(k, '1'); });
                document.cookie = 'age_verified=true;path=/;max-age=86400';
                document.cookie = 'ageVerified=true;path=/;max-age=86400';
            }
        """)
    except Exception:
        pass

    return False


async def safe_goto(page: Page, url: str, timeout: int = 30000) -> bool:
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_timeout(3000)
        await dismiss_age_gate(page)
        await page.wait_for_timeout(1000)
        return resp and resp.status < 400
    except Exception as e:
        print(f"    [!] Failed: {url}: {e}")
        return False


async def woocommerce_add_and_checkout(page: Page, brand: dict, loc: dict) -> dict:
    """WooCommerce: add product, go to /checkout, fill billing fields."""
    product_url = brand["product_url"]
    base = brand["base_url"].rstrip("/")
    state = loc["state"]
    zip_code = loc["zip"]
    abbr = loc["abbreviation"]

    print(f"  [{brand['name']}] Loading product: {product_url}")
    ok = await safe_goto(page, product_url)
    if not ok:
        return {"result": "error", "details": "Could not load product page"}

    await screenshot(page, brand["name"], f"product_{abbr}")

    # WooCommerce: click add-to-cart and wait for AJAX
    added = False
    for sel in ["button.single_add_to_cart_button", "button[name='add-to-cart']",
                "button:has-text('Add to Cart')", "button:has-text('ADD TO CART')"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.scroll_into_view_if_needed()
                await btn.click(timeout=3000)
                print(f"    [cart] Clicked: {sel}")
                added = True
                await page.wait_for_timeout(4000)
                break
        except Exception:
            continue

    if not added:
        # JS fallback
        try:
            r = await page.evaluate("""
                () => {
                    const btn = document.querySelector('.single_add_to_cart_button') ||
                                document.querySelector('button[name="add-to-cart"]');
                    if (btn) { btn.click(); return 'clicked'; }
                    // Try submitting the cart form directly
                    const form = document.querySelector('form.cart');
                    if (form) { form.submit(); return 'form-submitted'; }
                    return null;
                }
            """)
            if r:
                print(f"    [cart] JS: {r}")
                added = True
                await page.wait_for_timeout(4000)
        except Exception:
            pass

    if not added:
        return {"result": "could_not_add_to_cart", "details": "Add-to-cart failed"}

    await screenshot(page, brand["name"], f"after_add_{abbr}")

    # Navigate directly to checkout
    print(f"    [checkout] Going to {base}/checkout/")
    ok = await safe_goto(page, f"{base}/checkout/")
    if not ok:
        # Try cart first
        ok = await safe_goto(page, f"{base}/cart/")
        if ok:
            await screenshot(page, brand["name"], f"cart_{abbr}")
            # Click proceed to checkout
            for sel in [".wc-proceed-to-checkout a", "a.checkout-button",
                        "a:has-text('Proceed to checkout')", "a:has-text('Checkout')"]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click(timeout=5000)
                        await page.wait_for_timeout(4000)
                        break
                except Exception:
                    continue

    if "checkout" not in page.url.lower():
        await screenshot(page, brand["name"], f"no_checkout_{abbr}")
        return {"result": "could_not_reach_checkout", "details": f"Ended up at {page.url}"}

    await screenshot(page, brand["name"], f"checkout_{abbr}")

    # Fill billing fields
    field_map = {
        "#billing_first_name": "Test",
        "#billing_last_name": "User",
        "#billing_address_1": "123 Main St",
        "#billing_city": loc["state"],  # Use state name as city placeholder
        "#billing_postcode": zip_code,
    }
    for sel, val in field_map.items():
        try:
            inp = page.locator(sel).first
            if await inp.is_visible(timeout=1000):
                await inp.clear()
                await inp.fill(val)
                print(f"    [form] Filled {sel} = {val}")
        except Exception:
            pass

    # Select state
    for sel in ["#billing_state", "#shipping_state", "select[name='billing_state']"]:
        try:
            select = page.locator(sel).first
            if await select.is_visible(timeout=1000):
                try:
                    await select.select_option(label=state)
                except Exception:
                    await select.select_option(value=abbr)
                print(f"    [form] Selected state: {state}")
                break
        except Exception:
            continue

    # Fill email
    try:
        email_inp = page.locator("#billing_email").first
        if await email_inp.is_visible(timeout=1000):
            await email_inp.fill("test@example.com")
    except Exception:
        pass

    await page.wait_for_timeout(4000)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(3000)

    await screenshot(page, brand["name"], f"filled_{abbr}")
    return await check_checkout_result(page)


async def bigcommerce_checkout(page: Page, brand: dict, loc: dict) -> dict:
    """BigCommerce (enjoy hemp): add to cart, checkout, handle email-first flow."""
    product_url = brand["product_url"]
    base = brand["base_url"].rstrip("/")
    state = loc["state"]
    zip_code = loc["zip"]
    abbr = loc["abbreviation"]

    print(f"  [{brand['name']}] Loading product: {product_url}")
    ok = await safe_goto(page, product_url)
    if not ok:
        return {"result": "error", "details": "Could not load product page"}

    # Add to cart
    for sel in ["input[value='Add to Cart']", "button:has-text('Add to Cart')",
                "#form-action-addToCart"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.click(timeout=3000)
                print(f"    [cart] Clicked: {sel}")
                await page.wait_for_timeout(3000)
                break
        except Exception:
            continue

    # Go to checkout
    ok = await safe_goto(page, f"{base}/checkout")
    if not ok:
        return {"result": "could_not_reach_checkout", "details": "Could not load checkout"}

    await screenshot(page, brand["name"], f"checkout_{abbr}")

    # Email + privacy checkbox + continue
    try:
        email = page.locator("input[name='email'], input[type='email']").first
        if await email.is_visible(timeout=2000):
            await email.fill("test@example.com")
            print(f"    [form] Filled email")
    except Exception:
        pass

    # Check ALL checkboxes (privacy, terms, etc.)
    try:
        checkboxes = await page.locator("input[type='checkbox']").all()
        for cb in checkboxes:
            try:
                if await cb.is_visible(timeout=300) and not await cb.is_checked():
                    await cb.check()
                    print(f"    [form] Checked a checkbox")
            except Exception:
                continue
    except Exception:
        pass

    # Click Continue
    for sel in ["button:has-text('Continue')", "button:has-text('CONTINUE')",
                "#checkout-customer-continue"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click(timeout=5000)
                print(f"    [form] Clicked continue: {sel}")
                await page.wait_for_timeout(5000)
                break
        except Exception:
            continue

    await screenshot(page, brand["name"], f"after_continue_{abbr}")

    # Now try to fill shipping address
    shipping_fields = {
        "input[name='firstName'], #firstNameInput": "Test",
        "input[name='lastName'], #lastNameInput": "User",
        "input[name='address1'], #addressLine1Input": "123 Main St",
        "input[name='city'], #cityInput": loc["state"],
        "input[name='postalCode'], #postCode": zip_code,
    }

    for sels, val in shipping_fields.items():
        for sel in sels.split(", "):
            try:
                inp = page.locator(sel).first
                if await inp.is_visible(timeout=1000):
                    await inp.clear()
                    await inp.fill(val)
                    print(f"    [form] Filled {sel} = {val}")
                    break
            except Exception:
                continue

    # Select state/province
    for sel in ["select[name='stateOrProvince']", "#provinceInput", "select[name='province']"]:
        try:
            select = page.locator(sel).first
            if await select.is_visible(timeout=1000):
                try:
                    await select.select_option(label=state)
                except Exception:
                    await select.select_option(value=abbr)
                print(f"    [form] Selected state: {state}")
                break
        except Exception:
            continue

    await page.wait_for_timeout(4000)
    await screenshot(page, brand["name"], f"filled_{abbr}")
    return await check_checkout_result(page)


async def shopify_variant_checkout(page: Page, brand: dict, loc: dict) -> dict:
    """Shopify (ELYXR): select variant first, then add to cart."""
    product_url = brand["product_url"]
    base = brand["base_url"].rstrip("/")
    state = loc["state"]
    zip_code = loc["zip"]
    abbr = loc["abbreviation"]

    print(f"  [{brand['name']}] Loading product: {product_url}")
    ok = await safe_goto(page, product_url)
    if not ok:
        return {"result": "error", "details": "Could not load product page"}

    await screenshot(page, brand["name"], f"product_{abbr}")

    # Select first available variant if needed
    try:
        await page.evaluate("""
            () => {
                // Click the first variant swatch/option
                const swatches = document.querySelectorAll(
                    '.swatch-element:not(.soldout) label, ' +
                    '.product-option label, ' +
                    'input[type="radio"][name*="option"]:not(:checked), ' +
                    '.variant-input:not(.soldout)'
                );
                if (swatches.length > 0) {
                    swatches[0].click();
                    return 'selected variant';
                }
                return null;
            }
        """)
    except Exception:
        pass

    await page.wait_for_timeout(1000)

    # Add to cart
    for sel in ["button[name='add']", "button:has-text('Add to Cart')",
                "button:has-text('ADD TO CART')", ".add-to-cart button",
                "form[action*='/cart/add'] button[type='submit']"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.click(timeout=3000)
                print(f"    [cart] Clicked: {sel}")
                await page.wait_for_timeout(3000)
                break
        except Exception:
            continue

    # Go to checkout
    ok = await safe_goto(page, f"{base}/checkout")
    if not ok:
        # Try cart first
        ok = await safe_goto(page, f"{base}/cart")
        if ok:
            for sel in ["a:has-text('Checkout')", "button:has-text('Checkout')"]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click(timeout=5000)
                        await page.wait_for_timeout(4000)
                        break
                except Exception:
                    continue

    # Check if cart is empty
    text = await page.evaluate("() => document.body?.innerText || ''")
    if "cart is empty" in text.lower():
        await screenshot(page, brand["name"], f"empty_cart_{abbr}")
        return {"result": "cart_empty_at_checkout", "details": "Cart empty — variant selection likely needed"}

    if "checkout" not in page.url.lower():
        return {"result": "could_not_reach_checkout", "details": f"Ended up at {page.url}"}

    await screenshot(page, brand["name"], f"checkout_{abbr}")

    # Shopify checkout: fill email, then shipping
    try:
        email = page.locator("input[name='email'], input[type='email'], #email").first
        if await email.is_visible(timeout=2000):
            await email.fill("test@example.com")
    except Exception:
        pass

    # Fill zip
    for sel in ["input[name='shipping_address[zip]']", "#checkout_shipping_address_zip",
                "input[name*='postal']", "input[name*='zip']", "input[autocomplete='postal-code']"]:
        try:
            inp = page.locator(sel).first
            if await inp.is_visible(timeout=1000):
                await inp.fill(zip_code)
                print(f"    [form] Filled zip: {sel}")
                break
        except Exception:
            continue

    # Select state
    for sel in ["select[name='shipping_address[province]']", "#checkout_shipping_address_province"]:
        try:
            select = page.locator(sel).first
            if await select.is_visible(timeout=1000):
                await select.select_option(label=state)
                print(f"    [form] Selected state: {state}")
                break
        except Exception:
            continue

    await page.wait_for_timeout(4000)
    await screenshot(page, brand["name"], f"filled_{abbr}")
    return await check_checkout_result(page)


async def magento_checkout(page: Page, brand: dict, loc: dict) -> dict:
    """Magento (Mystic Labs): find a simple product, add, checkout."""
    base = brand["base_url"].rstrip("/")
    state = loc["state"]
    zip_code = loc["zip"]
    abbr = loc["abbreviation"]

    # Try to find a simpler THCA product (not a bundle)
    thca_urls = [
        f"{base}/thca-gummies/",
        f"{base}/thca/",
    ]

    ok = False
    for url in thca_urls:
        print(f"  [{brand['name']}] Trying: {url}")
        ok = await safe_goto(page, url)
        if ok:
            break

    if not ok:
        return {"result": "error", "details": "Could not load THCA page"}

    await screenshot(page, brand["name"], f"product_{abbr}")

    # Add to cart (Magento uses form submit)
    for sel in ["button#product-addtocart-button", "button:has-text('Add to Cart')",
                "button.tocart", "#product-addtocart-button"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.scroll_into_view_if_needed()
                await btn.click(timeout=5000)
                print(f"    [cart] Clicked: {sel}")
                await page.wait_for_timeout(5000)
                break
        except Exception:
            continue

    await screenshot(page, brand["name"], f"after_add_{abbr}")

    # Go to checkout
    ok = await safe_goto(page, f"{base}/checkout/")
    if not ok:
        return {"result": "could_not_reach_checkout", "details": "Could not load checkout"}

    await screenshot(page, brand["name"], f"checkout_{abbr}")

    # Magento checkout: fill email, then shipping
    try:
        email = page.locator("#customer-email, input[name='username']").first
        if await email.is_visible(timeout=2000):
            await email.fill("test@example.com")
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(2000)
    except Exception:
        pass

    # Fill address fields
    magento_fields = {
        "input[name='firstname']": "Test",
        "input[name='lastname']": "User",
        "input[name='street[0]']": "123 Main St",
        "input[name='city']": "Columbus" if abbr == "OH" else "Austin",
        "input[name='postcode']": zip_code,
        "input[name='telephone']": "5551234567",
    }
    for sel, val in magento_fields.items():
        try:
            inp = page.locator(sel).first
            if await inp.is_visible(timeout=1000):
                await inp.clear()
                await inp.fill(val)
        except Exception:
            pass

    # Select state
    for sel in ["select[name='region_id']", "select[name='region']"]:
        try:
            select = page.locator(sel).first
            if await select.is_visible(timeout=1000):
                try:
                    await select.select_option(label=state)
                except Exception:
                    await select.select_option(value=abbr)
                print(f"    [form] Selected state: {state}")
                break
        except Exception:
            continue

    await page.wait_for_timeout(5000)
    await screenshot(page, brand["name"], f"filled_{abbr}")
    return await check_checkout_result(page)


async def check_checkout_result(page: Page) -> dict:
    """Analyze the checkout page for restriction or shipping signals."""
    text = await page.evaluate("() => document.body?.innerText || ''")
    lower = text.lower()

    # Cart empty?
    if any(p in lower for p in ["your cart is empty", "no items in your", "cart is empty"]):
        return {"result": "cart_empty_at_checkout", "details": "Cart was empty at checkout"}

    # Restrictions?
    restriction_phrases = [
        "does not ship to", "cannot ship to", "unable to ship",
        "not available in your area", "shipping is not available",
        "not eligible", "we don't ship to", "cannot be shipped",
        "unavailable for delivery", "prohibited", "cannot sell or ship",
    ]
    for phrase in restriction_phrases:
        if phrase in lower:
            idx = lower.index(phrase)
            snippet = text[max(0, idx-40):idx+len(phrase)+80].strip()
            return {"result": "restricted", "details": f"...{snippet}..."}

    # Check restricted more carefully
    if "restricted" in lower:
        idx = lower.index("restricted")
        snippet = text[max(0, idx-40):idx+100].strip()
        if any(kw in snippet.lower() for kw in ["ship", "state", "deliver", "order", "product"]):
            return {"result": "restricted", "details": f"...{snippet}..."}

    # Shipping available?
    ok_phrases = [
        "shipping rate", "delivery estimate", "free shipping", "standard shipping",
        "estimated delivery", "shipping method", "flat rate", "shipping:",
        "place order", "complete order", "pay now", "submit order",
        "enter your address to view shipping",
    ]
    for phrase in ok_phrases:
        if phrase in lower:
            return {"result": "deliverable", "details": f"Found '{phrase}' on checkout"}

    return {"result": "unclear", "details": "No clear signal on checkout page"}


async def test_brand(browser, brand: dict) -> list[dict]:
    """Test a single brand for both states."""
    results = []
    platform = brand["platform"]

    for loc in TEST_ZIPS:
        print(f"\n{'='*50}")
        print(f"{brand['name']} -> {loc['state']} ({loc['zip']})")
        print(f"{'='*50}")

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        try:
            if platform == "woocommerce":
                result = await woocommerce_add_and_checkout(page, brand, loc)
            elif platform == "bigcommerce":
                result = await bigcommerce_checkout(page, brand, loc)
            elif platform == "shopify":
                result = await shopify_variant_checkout(page, brand, loc)
            elif platform == "magento":
                result = await magento_checkout(page, brand, loc)
            else:
                result = {"result": "error", "details": f"Unknown platform: {platform}"}
        except Exception as e:
            await screenshot(page, brand["name"], f"error_{loc['abbreviation']}")
            result = {"result": "error", "details": str(e)[:200]}

        print(f"  => {result['result']}: {result['details'][:80]}")

        results.append({
            "brand": brand["name"],
            "website": brand["base_url"],
            "brightfield_rank": brand["brightfield_rank"],
            "brightfield_funnel_pct": brand["brightfield_funnel_pct"],
            "state": loc["state"],
            "abbreviation": loc["abbreviation"],
            "method": "cart_checkout",
            "result": result["result"],
            "details": result["details"],
            "policy_url": "",
        })

        await context.close()

    return results


async def main():
    brand_filter = None
    if len(sys.argv) > 1:
        brand_filter = [b.strip().lower() for b in sys.argv[1].split(",")]

    brands = BRANDS_TO_TEST
    if brand_filter:
        brands = [b for b in brands if b["name"].lower() in brand_filter]

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        slow_mo=500,  # Add 500ms delay between actions for more human-like behavior
    )

    all_results = []
    try:
        for brand in brands:
            results = await test_brand(browser, brand)
            all_results.extend(results)
    finally:
        await browser.close()
        await pw.stop()

    # Write results
    if all_results:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(RESULTS_DIR, f"deliverability_{ts}_visible.csv")
        fieldnames = all_results[0].keys()
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(fieldnames) + ["deliverable", "scraped_at"])
            w.writeheader()
            for r in all_results:
                r["deliverable"] = r["result"]
                r["scraped_at"] = datetime.now().isoformat()
                w.writerow(r)
        print(f"\nResults written to: {path}")

        # Summary
        print("\nSUMMARY")
        print("=" * 50)
        for r in all_results:
            print(f"  {r['brand']:20} -> {r['state']}: {r['result']}")


if __name__ == "__main__":
    asyncio.run(main())
