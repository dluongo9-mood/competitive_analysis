#!/usr/bin/env python3
"""Targeted fixes for the 4 remaining stuck brands (Hempbombs is N/A)."""

import asyncio
import csv
import os
from datetime import datetime
from playwright.async_api import async_playwright, Page

SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

TEST_ZIPS = [
    {"state": "Ohio", "abbreviation": "OH", "zip": "43215"},
    {"state": "Texas", "abbreviation": "TX", "zip": "78701"},
]


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
                .forEach(k => localStorage.setItem(k, 'true'));
            document.cookie = 'age_verified=true;path=/;max-age=86400';
        }""")
    except Exception:
        pass


async def screenshot(page, name, label):
    safe = name.lower().replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SCREENSHOTS_DIR, f"{safe}_fix_{label}_{ts}.png")
    try:
        await page.screenshot(path=path, full_page=False)
        print(f"    [ss] {os.path.basename(path)}")
    except Exception:
        pass


async def check_result(page) -> dict:
    text = await page.evaluate("() => document.body?.innerText || ''")
    lower = text.lower()

    if any(p in lower for p in ["your cart is empty", "no items", "cart is empty"]):
        return {"result": "cart_empty_at_checkout", "details": "Cart empty at checkout"}

    for phrase in ["does not ship to", "cannot ship to", "unable to ship",
                   "not available in your area", "shipping is not available",
                   "we don't ship to", "cannot be shipped",
                   "cannot sell or ship"]:
        if phrase in lower:
            idx = lower.index(phrase)
            snippet = text[max(0, idx-40):idx+len(phrase)+80].strip()
            return {"result": "restricted", "details": f"...{snippet}..."}

    if "restricted" in lower:
        idx = lower.index("restricted")
        snippet = text[max(0, idx-40):idx+100].strip()
        snippet_l = snippet.lower()
        # Only flag if near shipping context AND not just a generic footer disclaimer
        if (any(kw in snippet_l for kw in ["ship", "state", "deliver", "order"]) and
                "void where" not in snippet_l and "by law" not in snippet_l):
            return {"result": "restricted", "details": f"...{snippet}..."}

    for phrase in ["shipping rate", "free shipping", "standard shipping",
                   "estimated delivery", "shipping method", "flat rate",
                   "shipping:", "place order", "complete order", "pay now",
                   "shipping calculated", "enter your address to view shipping",
                   "enter address to calculate", "delivery:",
                   "shipping options", "shipping protection"]:
        if phrase in lower:
            return {"result": "deliverable", "details": f"Found '{phrase}' on checkout"}

    return {"result": "unclear", "details": "No clear signal"}


# ============================================================
# iDelta: Select variant (size + strain) then add-to-cart
# ============================================================
async def test_idelta(page, loc):
    url = "https://delta8vapeoil.com/product/idelta-thca-flower/"
    print(f"  Loading {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)
    await dismiss_age_gate(page)

    # Select size = 3.5g
    try:
        size_select = page.locator("#choose-size")
        await size_select.select_option(label="3.5g")
        print(f"    Selected size: 3.5g")
        await page.wait_for_timeout(1500)
    except Exception as e:
        print(f"    [!] Size select failed: {e}")

    # Select strain
    try:
        strain_select = page.locator("#strain")
        await strain_select.select_option(label="Ghost OG Kush")
        print(f"    Selected strain: Ghost OG Kush")
        await page.wait_for_timeout(1500)
    except Exception as e:
        print(f"    [!] Strain select failed: {e}")

    await screenshot(page, "iDelta", f"variants_{loc['abbreviation']}")

    # Wait for the button to become enabled
    await page.wait_for_timeout(2000)

    # Click add-to-cart
    try:
        btn = page.locator("button.single_add_to_cart_button").first
        await btn.scroll_into_view_if_needed()
        await btn.click(timeout=5000)
        print(f"    Clicked add-to-cart")
        await page.wait_for_timeout(4000)
    except Exception as e:
        print(f"    [!] Add-to-cart failed: {e}")
        return {"result": "could_not_add_to_cart", "details": str(e)[:200]}

    await screenshot(page, "iDelta", f"after_add_{loc['abbreviation']}")

    # Go to checkout
    await page.goto("https://delta8vapeoil.com/checkout/", wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)
    await dismiss_age_gate(page)

    # If redirected to cart (empty), fail
    if "/cart" in page.url and "checkout" not in page.url:
        # Try clicking proceed to checkout on the cart page
        try:
            btn = page.locator(".wc-proceed-to-checkout a, a.checkout-button").first
            if await btn.is_visible(timeout=2000):
                await btn.click(timeout=5000)
                await page.wait_for_timeout(4000)
        except Exception:
            pass

    await screenshot(page, "iDelta", f"checkout_{loc['abbreviation']}")

    if "checkout" not in page.url.lower():
        text = await page.evaluate("() => document.body?.innerText || ''")
        if "currently empty" in text.lower():
            return {"result": "cart_empty_at_checkout", "details": "Cart empty — variant may not have been selected"}
        return {"result": "could_not_reach_checkout", "details": f"Ended up at {page.url}"}

    # Fill WooCommerce billing fields
    for sel, val in [("#billing_first_name", "Test"), ("#billing_last_name", "User"),
                     ("#billing_address_1", "123 Main St"),
                     ("#billing_city", "Columbus" if loc["abbreviation"] == "OH" else "Austin"),
                     ("#billing_postcode", loc["zip"]),
                     ("#billing_email", "test@example.com"),
                     ("#billing_phone", "5551234567")]:
        try:
            inp = page.locator(sel).first
            if await inp.is_visible(timeout=1000):
                await inp.clear()
                await inp.fill(val)
        except Exception:
            pass

    # Select state
    try:
        await page.locator("#billing_state").select_option(label=loc["state"])
        print(f"    Selected state: {loc['state']}")
    except Exception:
        try:
            await page.locator("#billing_state").select_option(value=loc["abbreviation"])
        except Exception:
            pass

    await page.wait_for_timeout(5000)
    await screenshot(page, "iDelta", f"filled_{loc['abbreviation']}")
    return await check_result(page)


# ============================================================
# Mystic Labs: Click add-to-cart on the /thca/ category page
# ============================================================
async def test_mystic_labs(page, loc):
    url = "https://mysticlabsd8.com/thca/"
    print(f"  Loading {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)
    await dismiss_age_gate(page)
    await page.wait_for_timeout(1000)
    await dismiss_age_gate(page)

    await screenshot(page, "Mystic Labs", f"category_{loc['abbreviation']}")

    # Click the first "Add to Cart" button on the category page
    try:
        btn = page.locator("button.tocart, button:has-text('Add to Cart')").first
        await btn.scroll_into_view_if_needed()
        await btn.click(timeout=5000)
        print(f"    Clicked category add-to-cart")
        await page.wait_for_timeout(5000)
    except Exception as e:
        print(f"    [!] Add-to-cart failed: {e}")
        return {"result": "could_not_add_to_cart", "details": str(e)[:200]}

    await dismiss_age_gate(page)
    await screenshot(page, "Mystic Labs", f"after_add_{loc['abbreviation']}")

    # Go to checkout
    await page.goto("https://mysticlabsd8.com/checkout/", wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(5000)
    await dismiss_age_gate(page)
    await screenshot(page, "Mystic Labs", f"checkout_{loc['abbreviation']}")

    # Check for empty cart
    text = await page.evaluate("() => document.body?.innerText || ''")
    if "no items" in text.lower() or "empty" in text.lower():
        return {"result": "cart_empty_at_checkout", "details": "Cart empty despite add-to-cart"}

    # Magento checkout: fill email
    try:
        email = page.locator("#customer-email, input[name='username']").first
        if await email.is_visible(timeout=3000):
            await email.fill("test@example.com")
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(3000)
    except Exception:
        pass

    # Fill shipping fields
    for sel, val in [("input[name='firstname']", "Test"),
                     ("input[name='lastname']", "User"),
                     ("input[name='street[0]']", "123 Main St"),
                     ("input[name='city']", "Columbus" if loc["abbreviation"] == "OH" else "Austin"),
                     ("input[name='postcode']", loc["zip"]),
                     ("input[name='telephone']", "5551234567")]:
        try:
            inp = page.locator(sel).first
            if await inp.is_visible(timeout=1000):
                await inp.clear()
                await inp.fill(val)
        except Exception:
            pass

    # Select country = US and state
    for sel in ["select[name='country_id']"]:
        try:
            await page.locator(sel).select_option(value="US")
            await page.wait_for_timeout(2000)
        except Exception:
            pass

    for sel in ["select[name='region_id']"]:
        try:
            s = page.locator(sel).first
            if await s.is_visible(timeout=2000):
                await s.select_option(label=loc["state"])
                print(f"    Selected state: {loc['state']}")
        except Exception:
            pass

    await page.wait_for_timeout(5000)
    await screenshot(page, "Mystic Labs", f"filled_{loc['abbreviation']}")
    return await check_result(page)


# ============================================================
# enjoy: BigCommerce checkout — fill email, check privacy, advance
# ============================================================
async def test_enjoy(page, loc):
    url = "https://enjoyhemp.co/3-5g-thca-flower-blue-dream-for-cloud-nine-hybrid/"
    print(f"  Loading {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)
    await dismiss_age_gate(page)

    # Add to cart
    try:
        btn = page.locator("input[value='Add to Cart'], #form-action-addToCart").first
        if await btn.is_visible(timeout=2000):
            await btn.click(timeout=5000)
            print(f"    Clicked add-to-cart")
            await page.wait_for_timeout(4000)
    except Exception:
        # JS fallback
        await page.evaluate("""
            () => {
                const btn = document.querySelector('input[value="Add to Cart"]') ||
                            document.querySelector('#form-action-addToCart');
                if (btn) btn.click();
            }
        """)
        await page.wait_for_timeout(4000)

    await screenshot(page, "enjoy", f"after_add_{loc['abbreviation']}")

    # Go to checkout
    await page.goto("https://enjoyhemp.co/checkout", wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(4000)
    await screenshot(page, "enjoy", f"checkout_{loc['abbreviation']}")

    # Fill email
    try:
        email = page.locator("input[name='email'], input[type='email']").first
        if await email.is_visible(timeout=2000):
            await email.fill("test@example.com")
            print(f"    Filled email")
    except Exception:
        pass

    # Check ALL checkboxes on the page (including privacy policy)
    try:
        await page.evaluate("""
            () => {
                document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    if (!cb.checked) {
                        cb.checked = true;
                        cb.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                });
            }
        """)
        print(f"    Checked all checkboxes via JS")
    except Exception:
        pass

    await page.wait_for_timeout(1000)

    # Click Continue
    try:
        btn = page.locator("button:has-text('Continue'), button:has-text('CONTINUE')").first
        if await btn.is_visible(timeout=2000):
            await btn.click(timeout=5000)
            print(f"    Clicked Continue")
            await page.wait_for_timeout(5000)
    except Exception:
        pass

    await screenshot(page, "enjoy", f"after_continue_{loc['abbreviation']}")

    # Check if shipping section expanded — look for address fields
    # BigCommerce shipping step: fill address
    shipping_visible = False
    for sel, val in [
        ("#firstNameInput, input[name='firstName'], input[id*='first']", "Test"),
        ("#lastNameInput, input[name='lastName'], input[id*='last']", "User"),
        ("#addressLine1Input, input[name='address1'], input[id*='address']", "123 Main St"),
        ("#cityInput, input[name='city'], input[id*='city']",
         "Columbus" if loc["abbreviation"] == "OH" else "Austin"),
        ("#postCode, input[name='postalCode'], input[id*='postCode'], input[id*='postal']",
         loc["zip"]),
    ]:
        for s in sel.split(", "):
            try:
                inp = page.locator(s).first
                if await inp.is_visible(timeout=1500):
                    await inp.clear()
                    await inp.fill(val)
                    print(f"    Filled {s} = {val}")
                    shipping_visible = True
                    break
            except Exception:
                continue

    # Country + state
    for sel in ["#countryCodeInput, select[name='countryCode']"]:
        for s in sel.split(", "):
            try:
                select = page.locator(s).first
                if await select.is_visible(timeout=1000):
                    await select.select_option(value="US")
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                continue

    for sel in ["#provinceInput, select[name='stateOrProvince'], select[name='province']"]:
        for s in sel.split(", "):
            try:
                select = page.locator(s).first
                if await select.is_visible(timeout=1000):
                    try:
                        await select.select_option(label=loc["state"])
                    except Exception:
                        await select.select_option(value=loc["abbreviation"])
                    print(f"    Selected state: {loc['state']}")
                    break
            except Exception:
                continue

    if not shipping_visible:
        # The shipping step didn't open — try scrolling to it
        try:
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight / 3)")
            await page.wait_for_timeout(2000)
        except Exception:
            pass

    await page.wait_for_timeout(4000)

    # Click Continue to shipping method if there's another step
    try:
        btn = page.locator("button:has-text('Continue'), #checkout-shipping-continue").first
        if await btn.is_visible(timeout=2000):
            await btn.click(timeout=5000)
            await page.wait_for_timeout(4000)
    except Exception:
        pass

    await screenshot(page, "enjoy", f"filled_{loc['abbreviation']}")
    return await check_result(page)


# ============================================================
# ELYXR: Use the Mystery THCA flower (simple product, no variant)
# ============================================================
async def test_elyxr(page, loc):
    url = "https://www.elyxr.com/products/mystery-1-8oz-natural-thca-flower/"
    print(f"  Loading {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)
    await dismiss_age_gate(page)

    await screenshot(page, "ELYXR", f"product_{loc['abbreviation']}")

    # Click add-to-cart
    added = False
    for sel in ["button[name='add']", "button:has-text('Add to Cart')",
                "button:has-text('ADD TO CART')", ".add-to-cart button"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.scroll_into_view_if_needed()
                await btn.click(timeout=5000)
                print(f"    Clicked: {sel}")
                added = True
                await page.wait_for_timeout(4000)
                break
        except Exception:
            continue

    if not added:
        # JS fallback with form submission
        try:
            r = await page.evaluate("""
                () => {
                    // Try the Shopify form submit approach
                    const form = document.querySelector('form[action*="/cart/add"]');
                    if (form) {
                        const formData = new FormData(form);
                        fetch('/cart/add.js', {method: 'POST', body: formData})
                            .then(r => r.json())
                            .then(data => console.log('Added:', data));
                        return 'fetch-added';
                    }
                    const btn = document.querySelector('button[name="add"], .add-to-cart');
                    if (btn) { btn.click(); return 'clicked'; }
                    return null;
                }
            """)
            if r:
                print(f"    JS add-to-cart: {r}")
                added = True
                await page.wait_for_timeout(4000)
        except Exception:
            pass

    if not added:
        return {"result": "could_not_add_to_cart", "details": "All add-to-cart methods failed"}

    await screenshot(page, "ELYXR", f"after_add_{loc['abbreviation']}")

    # Navigate to checkout via cart
    await page.goto("https://www.elyxr.com/cart", wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)

    cart_text = await page.evaluate("() => document.body?.innerText || ''")
    if "cart is empty" in cart_text.lower():
        # Last resort: try the /cart/add.js approach and retry
        await screenshot(page, "ELYXR", f"empty_cart_{loc['abbreviation']}")
        return {"result": "cart_empty_at_checkout", "details": "Cart still empty after add-to-cart"}

    await screenshot(page, "ELYXR", f"cart_{loc['abbreviation']}")

    # Click checkout on cart page
    try:
        btn = page.locator("a:has-text('Checkout'), button:has-text('Checkout'), a[href*='checkout']").first
        if await btn.is_visible(timeout=2000):
            await btn.click(timeout=5000)
            await page.wait_for_timeout(4000)
    except Exception:
        await page.goto("https://www.elyxr.com/checkout", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(4000)

    await screenshot(page, "ELYXR", f"checkout_{loc['abbreviation']}")

    # Fill Shopify checkout
    try:
        email = page.locator("input[name='email'], input[type='email']").first
        if await email.is_visible(timeout=2000):
            await email.fill("test@example.com")
    except Exception:
        pass

    for sel in ["input[name='shipping_address[zip]']", "#checkout_shipping_address_zip",
                "input[name*='postal']", "input[name*='zip']"]:
        try:
            inp = page.locator(sel).first
            if await inp.is_visible(timeout=1000):
                await inp.fill(loc["zip"])
                print(f"    Filled zip: {sel}")
                break
        except Exception:
            continue

    for sel in ["select[name='shipping_address[province]']", "#checkout_shipping_address_province"]:
        try:
            s = page.locator(sel).first
            if await s.is_visible(timeout=1000):
                await s.select_option(label=loc["state"])
                print(f"    Selected state: {loc['state']}")
                break
        except Exception:
            continue

    await page.wait_for_timeout(4000)
    await screenshot(page, "ELYXR", f"filled_{loc['abbreviation']}")
    return await check_result(page)


# ============================================================
# Main
# ============================================================
async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        slow_mo=400,
    )

    brands = [
        {"name": "iDelta", "func": test_idelta, "rank": 4, "pct": 25.6,
         "base_url": "https://delta8vapeoil.com"},
        {"name": "Mystic Labs", "func": test_mystic_labs, "rank": 9, "pct": 16.1,
         "base_url": "https://mysticlabsd8.com"},
        {"name": "enjoy", "func": test_enjoy, "rank": 19, "pct": 11.5,
         "base_url": "https://enjoyhemp.co"},
        {"name": "ELYXR", "func": test_elyxr, "rank": 23, "pct": 11.0,
         "base_url": "https://www.elyxr.com"},
    ]

    all_results = []

    for brand in brands:
        for loc in TEST_ZIPS:
            print(f"\n{'='*50}")
            print(f"{brand['name']} -> {loc['state']} ({loc['zip']})")
            print(f"{'='*50}")

            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await ctx.new_page()
            try:
                result = await brand["func"](page, loc)
            except Exception as e:
                await screenshot(page, brand["name"], f"error_{loc['abbreviation']}")
                result = {"result": "error", "details": str(e)[:200]}

            print(f"  => {result['result']}: {result['details'][:80]}")

            all_results.append({
                "brand": brand["name"],
                "website": brand["base_url"],
                "brightfield_rank": brand["rank"],
                "brightfield_funnel_pct": brand["pct"],
                "state": loc["state"],
                "abbreviation": loc["abbreviation"],
                "method": "cart_checkout",
                "result": result["result"],
                "details": result["details"],
                "policy_url": "",
                "deliverable": result["result"],
                "scraped_at": datetime.now().isoformat(),
            })

            await ctx.close()

    await browser.close()
    await pw.stop()

    # Write results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(RESULTS_DIR, f"deliverability_{ts}_targeted.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_results[0].keys()))
        w.writeheader()
        w.writerows(all_results)
    print(f"\nResults: {path}")

    print("\nSUMMARY")
    print("=" * 50)
    for r in all_results:
        print(f"  {r['brand']:20} -> {r['state']}: {r['result']}")


if __name__ == "__main__":
    asyncio.run(main())
