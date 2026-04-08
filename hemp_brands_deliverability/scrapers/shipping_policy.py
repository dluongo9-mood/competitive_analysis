from __future__ import annotations

import re
from scrapers.base import BaseScraper
from config import SHIPPING_POLICY_PATHS, STATE_RESTRICTION_KEYWORDS


class ShippingPolicyScraper(BaseScraper):
    """Scrape shipping/FAQ pages for state restriction info."""

    async def check_brand(self, brand: dict, locations: list[dict]) -> list[dict]:
        results = []
        page = await self.new_page()

        try:
            policy_text, policy_url = await self._find_shipping_policy(page, brand)

            if not policy_text:
                for loc in locations:
                    results.append({
                        "brand": brand["name"],
                        "website": brand["base_url"],
                        "state": loc["state"],
                        "abbreviation": loc["abbreviation"],
                        "method": "shipping_policy",
                        "result": "no_policy_found",
                        "details": "Could not find a shipping policy page",
                        "policy_url": "",
                    })
                return results

            for loc in locations:
                result = self._analyze_policy_text(policy_text, loc)
                results.append({
                    "brand": brand["name"],
                    "website": brand["base_url"],
                    "state": loc["state"],
                    "abbreviation": loc["abbreviation"],
                    "method": "shipping_policy",
                    "policy_url": policy_url or "",
                    **result,
                })
        finally:
            await page.context.close()

        return results

    async def _find_shipping_policy(self, page, brand: dict) -> tuple[str | None, str | None]:
        """Try common shipping policy URL paths. Returns (text, url) or (None, None)."""
        base = brand["base_url"].rstrip("/")

        for path in SHIPPING_POLICY_PATHS:
            url = f"{base}{path}"
            print(f"  [policy] Trying {url}")
            ok = await self.safe_goto(page, url, timeout=15000)
            if ok:
                text = await self.get_page_text(page)
                lower = text.lower()
                if any(kw in lower for kw in ["shipping", "delivery", "ship to", "we ship"]):
                    print(f"  [policy] Found shipping content at {url}")
                    await self.screenshot(page, brand["name"], "shipping_policy")
                    return text, url

        # Also try searching for a shipping link on the homepage
        print(f"  [policy] Trying homepage footer links for {brand['name']}")
        ok = await self.safe_goto(page, base, timeout=15000)
        if ok:
            await self.dismiss_popups(page)
            links = await page.evaluate("""
                () => {
                    const anchors = document.querySelectorAll('a');
                    return Array.from(anchors)
                        .filter(a => /shipping|delivery/i.test(a.textContent))
                        .map(a => a.href)
                        .slice(0, 3);
                }
            """)
            for link in links:
                print(f"  [policy] Found footer link: {link}")
                ok = await self.safe_goto(page, link, timeout=15000)
                if ok:
                    text = await self.get_page_text(page)
                    if len(text) > 100:
                        await self.screenshot(page, brand["name"], "shipping_policy")
                        return text, link

        print(f"  [policy] No shipping policy found for {brand['name']}")
        return None, None

    def _analyze_policy_text(self, text: str, location: dict) -> dict:
        """Check if policy text mentions restrictions for a given state."""
        lower = text.lower()
        state_name = location["state"].lower()
        state_abbr = location["abbreviation"]

        # Check for the state name/abbreviation near restriction keywords
        mentions_state = state_name in lower or f" {state_abbr.lower()} " in f" {lower} "

        restriction_keywords_found = []
        for kw in STATE_RESTRICTION_KEYWORDS:
            if kw.lower() in lower:
                restriction_keywords_found.append(kw)

        # Look for state near restriction context (within ~200 chars)
        restricted = False
        context_snippets = []

        patterns = [
            rf"(?i)((?:do not|don'?t|cannot|can'?t|unable to|not able to)\s+(?:ship|deliver)[\w\s,]*{re.escape(state_name)})",
            rf"(?i)({re.escape(state_name)}[\w\s,]*(?:restricted|prohibited|excluded|not available|not eligible))",
            rf"(?i)(restricted\s+states?[\s:]*[^.]*{re.escape(state_name)})",
            rf"(?i)(restricted\s+states?[\s:]*[^.]*\b{re.escape(state_abbr)}\b)",
            rf"(?i)((?:do not|don'?t|cannot|can'?t|unable to)\s+(?:ship|deliver)[\w\s,]*\b{re.escape(state_abbr)}\b)",
        ]

        for pat in patterns:
            matches = re.findall(pat, text)
            if matches:
                restricted = True
                context_snippets.extend(matches[:2])

        if restricted:
            return {
                "result": "restricted",
                "details": f"Policy indicates restriction. Matches: {'; '.join(context_snippets[:3])}",
            }
        elif mentions_state and restriction_keywords_found:
            return {
                "result": "possibly_restricted",
                "details": f"State mentioned with keywords: {', '.join(restriction_keywords_found[:5])}",
            }
        elif restriction_keywords_found and not mentions_state:
            return {
                "result": "has_restrictions_other_states",
                "details": f"Restriction language found but {location['state']} not mentioned: {', '.join(restriction_keywords_found[:5])}",
            }
        else:
            return {
                "result": "no_restriction_found",
                "details": f"No restriction language found mentioning {location['state']}",
            }
