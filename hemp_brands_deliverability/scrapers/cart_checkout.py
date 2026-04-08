from __future__ import annotations

from scrapers.base import BaseScraper
from playwright.async_api import Page


class CartCheckoutScraper(BaseScraper):
    """Add a THCA product to cart and test checkout with zip codes."""

    async def check_brand(self, brand: dict, locations: list[dict]) -> list[dict]:
        results = []
        page = await self.new_page()

        try:
            # Step 1: Find a THCA product
            product_url = await self._find_thca_product(page, brand)
            if not product_url:
                for loc in locations:
                    results.append({
                        "brand": brand["name"],
                        "website": brand["base_url"],
                        "state": loc["state"],
                        "abbreviation": loc["abbreviation"],
                        "method": "cart_checkout",
                        "result": "no_thca_product_found",
                        "details": "Could not find a THCA product to add to cart",
                    })
                return results

            # Step 2: Test each location
            for loc in locations:
                result = await self._test_checkout_with_zip(page, brand, loc)
                results.append({
                    "brand": brand["name"],
                    "website": brand["base_url"],
                    "state": loc["state"],
                    "abbreviation": loc["abbreviation"],
                    "method": "cart_checkout",
                    **result,
                })
        finally:
            await page.context.close()

        return results

    async def _find_thca_product(self, page: Page, brand: dict) -> str | None:
        """Navigate to the THCA collection and find a product link."""
        thca_url = brand.get("thca_url", "")
        print(f"  [cart] Navigating to THCA collection: {thca_url}")

        ok = await self.safe_goto(page, thca_url, timeout=20000)
        if not ok:
            # Try base_url + common THCA paths
            for path in ["/collections/thca", "/product-category/thca/", "/thca/", "/collections/thca-flower"]:
                url = brand["base_url"].rstrip("/") + path
                print(f"  [cart] Trying fallback: {url}")
                ok = await self.safe_goto(page, url, timeout=15000)
                if ok:
                    break
            if not ok:
                return None

        await self.dismiss_popups(page)
        await self.screenshot(page, brand["name"], "thca_collection")

        # Find product links on the page
        product_link = await page.evaluate("""
            () => {
                // Common product card selectors
                const selectors = [
                    'a[href*="/products/"]',
                    'a[href*="/product/"]',
                    '.product-card a',
                    '.product-item a',
                    '.grid-item a',
                    '.collection-product a',
                    'a.product-link',
                    '.product a[href]',
                ];

                for (const sel of selectors) {
                    const links = document.querySelectorAll(sel);
                    for (const link of links) {
                        const text = (link.textContent + ' ' + link.getAttribute('href')).toLowerCase();
                        if (text.includes('thca') || text.includes('thc-a')) {
                            return link.href;
                        }
                    }
                    // If no THCA-specific match, just take the first product link
                    if (links.length > 0) {
                        return links[0].href;
                    }
                }
                return null;
            }
        """)

        if product_link:
            print(f"  [cart] Found product: {product_link}")
        else:
            print(f"  [cart] No product links found on collection page")

        return product_link

    async def _test_checkout_with_zip(self, page: Page, brand: dict, location: dict) -> dict:
        """Add product to cart and attempt to enter zip code at checkout."""
        zip_code = location["zip_code"]
        state = location["state"]
        print(f"  [cart] Testing checkout for {brand['name']} -> {state} ({zip_code})")

        try:
            # Re-navigate to THCA collection to find a product
            product_url = await self._find_thca_product(page, brand)
            if not product_url:
                return {"result": "no_thca_product_found", "details": "Could not find product"}

            # Go to the product page
            ok = await self.safe_goto(page, product_url, timeout=20000)
            if not ok:
                return {"result": "error", "details": f"Could not load product page: {product_url}"}

            await self.dismiss_popups(page)
            await page.wait_for_timeout(2000)
            # Dismiss again in case the age gate appeared after page load
            await self.dismiss_popups(page)

            # Try to add to cart
            added = await self._add_to_cart(page)
            if not added:
                await self.screenshot(page, brand["name"], f"add_to_cart_fail_{location['abbreviation']}")
                return {"result": "could_not_add_to_cart", "details": "Add to cart button not found or failed"}

            await self.screenshot(page, brand["name"], f"added_to_cart_{location['abbreviation']}")

            # WooCommerce AJAX: wait for cart widget to update, then check cart page
            await page.wait_for_timeout(3000)

            # Verify item was actually added by checking cart count or navigating to cart
            try:
                cart_count = await page.evaluate("""
                    () => {
                        // Check common cart count indicators
                        const indicators = document.querySelectorAll(
                            '.cart-count, .cart-contents-count, .mini-cart-count, ' +
                            '.header-cart-count, [data-cart-count], .cart-quantity'
                        );
                        for (const el of indicators) {
                            const num = parseInt(el.textContent);
                            if (num > 0) return num;
                        }
                        return 0;
                    }
                """)
                if cart_count > 0:
                    print(f"  [cart] Cart count verified: {cart_count} items")
            except Exception:
                pass

            # Navigate to checkout
            checkout_result = await self._go_to_checkout(page, brand)
            if not checkout_result:
                return {"result": "could_not_reach_checkout", "details": "Could not navigate to checkout page"}

            await page.wait_for_timeout(3000)
            await self.screenshot(page, brand["name"], f"checkout_{location['abbreviation']}")

            # Enter zip code / state and look for restriction messages
            delivery_result = await self._enter_shipping_info(page, location)
            await self.screenshot(page, brand["name"], f"shipping_check_{location['abbreviation']}")

            return delivery_result

        except Exception as e:
            await self.screenshot(page, brand["name"], f"error_{location['abbreviation']}")
            return {"result": "error", "details": str(e)[:200]}

    async def _add_to_cart(self, page: Page) -> bool:
        """Find and click the add-to-cart button."""
        # Shopify selectors
        shopify_selectors = [
            "button[name='add']",
            "form[action*='/cart/add'] button[type='submit']",
            ".product-form button[type='submit']",
            "#add-to-cart",
        ]
        # WooCommerce selectors
        woo_selectors = [
            "button.single_add_to_cart_button",
            ".single_add_to_cart_button",
            "button[name='add-to-cart']",
            "input[name='add-to-cart']",
            ".woocommerce button[type='submit']",
            "form.cart button[type='submit']",
        ]
        # Generic text-based selectors
        text_selectors = [
            "button:has-text('Add to Cart')",
            "button:has-text('Add to cart')",
            "button:has-text('ADD TO CART')",
            "button:has-text('Add To Cart')",
            "input[value='Add to Cart']",
            "input[value='ADD TO CART']",
            "button.add-to-cart",
            ".add-to-cart button",
            "button[data-action='add-to-cart']",
            "button:has-text('Add To Bag')",
            "a:has-text('Add to Cart')",
            "a.add-to-cart",
        ]

        all_selectors = shopify_selectors + woo_selectors + text_selectors

        for sel in all_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=800):
                    await btn.scroll_into_view_if_needed(timeout=2000)
                    await btn.click(timeout=3000)
                    print(f"  [cart] Clicked add-to-cart: {sel}")
                    # Wait longer for WooCommerce AJAX add-to-cart
                    await page.wait_for_timeout(3000)
                    return True
            except Exception:
                continue

        # JS fallback: find any button/input whose text or value matches "add to cart"
        try:
            clicked = await page.evaluate("""
                () => {
                    const els = document.querySelectorAll('button, input[type="submit"], a');
                    for (const el of els) {
                        const text = (el.innerText || el.value || '').toLowerCase().trim();
                        if (text.includes('add to cart') || text.includes('add to bag')) {
                            el.scrollIntoView();
                            el.click();
                            return text;
                        }
                    }
                    return null;
                }
            """)
            if clicked:
                print(f"  [cart] Clicked add-to-cart (JS fallback): '{clicked}'")
                await page.wait_for_timeout(3000)
                return True
        except Exception:
            pass

        return False

    async def _go_to_checkout(self, page: Page, brand: dict) -> bool:
        """Navigate to the checkout page."""
        await self.dismiss_popups(page)

        # First try clicking checkout buttons on the current page (cart drawer, etc.)
        checkout_selectors = [
            "a:has-text('Checkout')",
            "a:has-text('Check out')",
            "button:has-text('Checkout')",
            "button:has-text('Check out')",
            "a[href*='checkout']",
            "button:has-text('Proceed to Checkout')",
            "a:has-text('Proceed to Checkout')",
            "button:has-text('CHECKOUT')",
            "a:has-text('CHECKOUT')",
            # WooCommerce cart page
            ".wc-proceed-to-checkout a",
            "a.checkout-button",
            ".checkout-button",
        ]

        for sel in checkout_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click(timeout=5000)
                    print(f"  [cart] Clicked checkout: {sel}")
                    await page.wait_for_timeout(3000)
                    await self.dismiss_popups(page)
                    return True
            except Exception:
                continue

        # Direct navigation to checkout URLs (works for WooCommerce and Shopify)
        base = brand["base_url"].rstrip("/")
        checkout_urls = [
            f"{base}/checkout",
            f"{base}/checkout/",
            f"{base}/cart",        # Go to cart first for WooCommerce
        ]

        for url in checkout_urls:
            ok = await self.safe_goto(page, url, timeout=15000)
            if not ok:
                continue
            await self.dismiss_popups(page)

            # If we're on a cart page, try to proceed to checkout
            if "/cart" in page.url and "checkout" not in page.url:
                for sel in checkout_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1000):
                            await btn.click(timeout=5000)
                            await page.wait_for_timeout(3000)
                            await self.dismiss_popups(page)
                            print(f"  [cart] Clicked checkout from cart: {sel}")
                            return True
                    except Exception:
                        continue

                # WooCommerce: try JS click on proceed-to-checkout
                try:
                    clicked = await page.evaluate("""
                        () => {
                            const link = document.querySelector('.wc-proceed-to-checkout a, a.checkout-button');
                            if (link) { link.click(); return true; }
                            return false;
                        }
                    """)
                    if clicked:
                        print(f"  [cart] Clicked WooCommerce checkout (JS)")
                        await page.wait_for_timeout(3000)
                        await self.dismiss_popups(page)
                        return True
                except Exception:
                    pass

            # If we reached /checkout directly
            if "checkout" in page.url.lower():
                return True

        return False

    async def _enter_shipping_info(self, page: Page, location: dict) -> dict:
        """Enter zip code/state at checkout and check for restriction messages."""
        zip_code = location["zip_code"]
        state = location["state"]
        abbreviation = location["abbreviation"]

        # First check if cart is empty (ELYXR-type issue)
        try:
            text = await self.get_page_text(page)
            lower = text.lower()
            if any(phrase in lower for phrase in ["your cart is empty", "no items in your", "cart is empty"]):
                return {
                    "result": "cart_empty_at_checkout",
                    "details": "Cart was empty when reaching checkout — add-to-cart may not have worked",
                }
        except Exception:
            pass

        # Some checkouts require email first (enjoy hemp pattern)
        # Fill a dummy email to unlock the shipping step
        email_selectors = [
            "input[name='email']",
            "input[type='email']",
            "input[name='checkout[email]']",
            "#checkout_email",
            "input[placeholder*='email' i]",
            "input[placeholder*='Email']",
        ]
        for sel in email_selectors:
            try:
                inp = page.locator(sel).first
                if await inp.is_visible(timeout=1000):
                    await inp.fill("test@example.com")
                    print(f"  [cart] Filled email in {sel}")

                    # Check any required checkboxes (privacy policy, terms, etc.)
                    for cb_sel in [
                        "input[type='checkbox'][required]",
                        "input[name*='privacy']",
                        "input[name*='terms']",
                        "input[name*='agree']",
                        "input[name*='policy']",
                    ]:
                        try:
                            cb = page.locator(cb_sel).first
                            if await cb.is_visible(timeout=500):
                                if not await cb.is_checked():
                                    await cb.check()
                                    print(f"  [cart] Checked: {cb_sel}")
                        except Exception:
                            continue

                    # Look for a Continue button to advance to shipping step
                    for btn_sel in [
                        "button:has-text('Continue')",
                        "button:has-text('CONTINUE')",
                        "button[type='submit']:has-text('Continue')",
                        "#continue_button",
                    ]:
                        try:
                            btn = page.locator(btn_sel).first
                            if await btn.is_visible(timeout=1000):
                                await btn.click(timeout=3000)
                                print(f"  [cart] Clicked continue: {btn_sel}")
                                await page.wait_for_timeout(4000)
                                break
                        except Exception:
                            continue
                    break
            except Exception:
                continue

        # Zip code selectors — Shopify, WooCommerce, BigCommerce, generic
        zip_selectors = [
            # Shopify
            "input[name='shipping_address[zip]']",
            "#checkout_shipping_address_zip",
            # WooCommerce
            "#billing_postcode",
            "#shipping_postcode",
            "input[name='billing_postcode']",
            "input[name='shipping_postcode']",
            # BigCommerce / generic
            "input[name*='zip']",
            "input[name*='postal']",
            "input[name*='postcode']",
            "input[placeholder*='ZIP' i]",
            "input[placeholder*='Zip']",
            "input[placeholder*='Postal' i]",
            "input[placeholder*='Postcode' i]",
            "input[autocomplete='postal-code']",
            "#shipping-zip",
            # Magento
            "input[name='postcode']",
            "#shipping-new-address-form input[name='postcode']",
        ]

        filled_zip = False
        for sel in zip_selectors:
            try:
                inp = page.locator(sel).first
                if await inp.is_visible(timeout=800):
                    await inp.clear()
                    await inp.fill(zip_code)
                    filled_zip = True
                    print(f"  [cart] Filled zip code {zip_code} in {sel}")
                    break
            except Exception:
                continue

        # If still not filled, try JS approach
        if not filled_zip:
            try:
                filled_js = await page.evaluate(f"""
                    () => {{
                        const selectors = [
                            'input[name*="zip"]', 'input[name*="postal"]',
                            'input[name*="postcode"]', 'input[autocomplete="postal-code"]',
                            'input[placeholder*="ZIP"]', 'input[placeholder*="Zip"]',
                            'input[placeholder*="Postal"]'
                        ];
                        for (const sel of selectors) {{
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent !== null) {{
                                el.value = '{zip_code}';
                                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                                el.dispatchEvent(new Event('blur', {{bubbles: true}}));
                                return sel;
                            }}
                        }}
                        return null;
                    }}
                """)
                if filled_js:
                    filled_zip = True
                    print(f"  [cart] Filled zip code {zip_code} via JS: {filled_js}")
            except Exception:
                pass

        # State/province selectors — Shopify, WooCommerce, generic
        state_selectors = [
            # Shopify
            "select[name='shipping_address[province]']",
            "#checkout_shipping_address_province",
            # WooCommerce
            "#billing_state",
            "#shipping_state",
            "select[name='billing_state']",
            "select[name='shipping_state']",
            "#calc_shipping_state",
            # Generic
            "select[name*='state']",
            "select[name*='province']",
            "select[name*='region']",
        ]

        for sel in state_selectors:
            try:
                select = page.locator(sel).first
                if await select.is_visible(timeout=800):
                    # Try label first, then value
                    try:
                        await select.select_option(label=state)
                        print(f"  [cart] Selected state: {state} in {sel}")
                    except Exception:
                        try:
                            await select.select_option(value=abbreviation)
                            print(f"  [cart] Selected state by abbr: {abbreviation} in {sel}")
                        except Exception:
                            pass
                    break
            except Exception:
                continue

        if not filled_zip:
            # Check if page text has any restriction info even without filling
            text = await self.get_page_text(page)
            lower = text.lower()
            if any(kw in lower for kw in ["restricted", "cannot ship", "not available"]):
                return {
                    "result": "restricted_on_page",
                    "details": "Restriction language found on checkout page before entering zip",
                }
            return {
                "result": "could_not_enter_zip",
                "details": "No zip code input field found on checkout page",
            }

        # Wait for the page to process the zip/state
        await page.wait_for_timeout(2000)

        # Tab out of field to trigger validation
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(2000)

        # WooCommerce: click "Update totals" or trigger shipping calculation
        for btn_sel in [
            "button:has-text('Update')",
            "button[name='calc_shipping']",
            "#place_order",
        ]:
            try:
                btn = page.locator(btn_sel).first
                if await btn.is_visible(timeout=500):
                    # Don't click place_order, just check it exists (means checkout is live)
                    if btn_sel == "#place_order":
                        break
                    await btn.click(timeout=2000)
                    print(f"  [cart] Clicked update: {btn_sel}")
                    await page.wait_for_timeout(3000)
                    break
            except Exception:
                continue

        # Check for error/restriction messages
        text = await self.get_page_text(page)
        lower = text.lower()

        restriction_phrases = [
            "does not ship to",
            "cannot ship to",
            "unable to ship",
            "not available in your area",
            "shipping is not available",
            "not eligible",
            "we don't ship to",
            "this product cannot be shipped",
            "unavailable for delivery",
            "prohibited",
            "cannot sell or ship",
        ]

        for phrase in restriction_phrases:
            if phrase in lower:
                idx = lower.index(phrase)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(phrase) + 100)
                snippet = text[start:end].strip()
                return {
                    "result": "restricted",
                    "details": f"Checkout restriction: ...{snippet}...",
                }

        # Check for "restricted" but only if near shipping/state context
        # (avoid false positives from unrelated page text)
        if "restricted" in lower:
            import re
            match = re.search(r'.{0,50}restricted.{0,100}', text, re.IGNORECASE)
            if match:
                snippet = match.group(0).strip()
                # Only flag if it's near shipping-related words
                snippet_lower = snippet.lower()
                if any(kw in snippet_lower for kw in ["ship", "state", "deliver", "order", "product"]):
                    return {
                        "result": "restricted",
                        "details": f"Checkout restriction: ...{snippet}...",
                    }

        # Check for shipping rate being shown (indicates delivery IS available)
        shipping_ok_phrases = [
            "shipping rate",
            "delivery estimate",
            "free shipping",
            "standard shipping",
            "estimated delivery",
            "ships to",
            "shipping method",
            "flat rate",
            "shipping:",       # WooCommerce shows "Shipping: $X.XX"
            "place order",     # WooCommerce checkout has this when ready
            "shipping calculated at", # some Shopify themes
        ]

        for phrase in shipping_ok_phrases:
            if phrase in lower:
                return {
                    "result": "deliverable",
                    "details": f"Shipping options available (found '{phrase}' on checkout page)",
                }

        return {
            "result": "unclear",
            "details": "Zip entered but no clear restriction or shipping confirmation found",
        }
