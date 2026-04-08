import os
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser


SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


class BaseScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self._playwright = None
        self._browser = None

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        return page

    async def safe_goto(self, page: Page, url: str, timeout: int = 30000) -> bool:
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if response and response.status < 400:
                await page.wait_for_timeout(2000)
                return True
            return False
        except Exception as e:
            print(f"  [!] Failed to load {url}: {e}")
            return False

    async def get_page_text(self, page: Page) -> str:
        return await page.evaluate("() => document.body?.innerText || ''")

    async def screenshot(self, page: Page, brand_name: str, label: str):
        safe_name = brand_name.lower().replace(" ", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOTS_DIR, f"{safe_name}_{label}_{ts}.png")
        try:
            await page.screenshot(path=path, full_page=False)
            print(f"  [screenshot] {path}")
        except Exception:
            pass

    async def dismiss_popups(self, page: Page):
        """Try to close common popups/modals that block interaction."""
        await self._dismiss_age_gate(page)
        await self._dismiss_generic_popups(page)

    async def _dismiss_age_gate(self, page: Page):
        """Detect and dismiss age verification gates common on hemp/cannabis sites."""
        # Check if an age gate is present by looking at visible page text
        try:
            has_age_gate = await page.evaluate("""
                () => {
                    const text = document.body?.innerText?.toLowerCase() || '';
                    // Look for age gate keywords
                    const keywords = [
                        'confirm your age', 'verify your age', 'age verification',
                        'are you 21', 'are you over 21', 'must be 21',
                        '21+ to enter', '21 years', 'of legal age',
                        'old enough', 'over 21'
                    ];
                    return keywords.some(kw => text.includes(kw));
                }
            """)
            if not has_age_gate:
                return
        except Exception:
            return

        print("  [popup] Age gate detected, attempting to dismiss...")

        # Strategy 1: Click buttons/links by text (ordered most-specific to least)
        age_button_texts = [
            "Yep, let's go",  # Mellow Fellow
            "I'm over 21",    # Mystic Labs
            "I am over 21",
            "I'm 21 or older",
            "I am 21 or older",
            "I am of legal age",
            "YES",             # Cookies
            "Yes",
            "ENTER",           # Generic
            "Enter",           # Mood
            "I Agree",
            "I agree",
            "Confirm",
            "Continue",
            "VERIFY",
            "Verify",
        ]

        for text in age_button_texts:
            for tag in ["button", "a", "span", "div"]:
                sel = f"{tag}:has-text('{text}')"
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=500):
                        await btn.click(timeout=3000)
                        print(f"  [popup] Dismissed age gate: {tag} '{text}'")
                        await page.wait_for_timeout(2000)
                        return
                except Exception:
                    continue

        # Strategy 2: JavaScript-based approach - find clickable elements in modals/overlays
        try:
            clicked = await page.evaluate("""
                () => {
                    // Find modal/overlay containers
                    const containers = document.querySelectorAll(
                        'dialog, [role="dialog"], .modal, .overlay, .popup, ' +
                        '[class*="age"], [class*="verify"], [id*="age"], [id*="verify"], ' +
                        '[class*="gate"], [class*="modal"], [class*="overlay"]'
                    );

                    // Also check for fixed/absolute positioned overlays
                    const allEls = document.querySelectorAll('div, section');
                    for (const el of allEls) {
                        const style = window.getComputedStyle(el);
                        if ((style.position === 'fixed' || style.position === 'absolute') &&
                            style.zIndex > 100 &&
                            el.innerText && el.innerText.toLowerCase().includes('21')) {
                            containers.length === 0 ? null : null;  // just to avoid empty block
                            // Add to our search
                            const btns = el.querySelectorAll('button, a, [role="button"]');
                            for (const btn of btns) {
                                const btnText = btn.innerText.toLowerCase().trim();
                                const positiveWords = ['yes', 'enter', 'verify', 'confirm',
                                                       'agree', 'continue', 'over 21', "i'm 21"];
                                const negativeWords = ['no', 'exit', 'leave', 'not'];
                                if (positiveWords.some(w => btnText.includes(w)) &&
                                    !negativeWords.some(w => btnText === w)) {
                                    btn.click();
                                    return btn.innerText.trim();
                                }
                            }
                        }
                    }

                    for (const container of containers) {
                        const btns = container.querySelectorAll('button, a, [role="button"]');
                        for (const btn of btns) {
                            const btnText = btn.innerText.toLowerCase().trim();
                            const positiveWords = ['yes', 'enter', 'verify', 'confirm',
                                                   'agree', 'continue', 'over 21', "i'm 21"];
                            const negativeWords = ['no', 'exit', 'leave', 'not'];
                            if (positiveWords.some(w => btnText.includes(w)) &&
                                !negativeWords.some(w => btnText === w)) {
                                btn.click();
                                return btn.innerText.trim();
                            }
                        }
                    }
                    return null;
                }
            """)
            if clicked:
                print(f"  [popup] Dismissed age gate (JS fallback): '{clicked}'")
                await page.wait_for_timeout(2000)
                return
        except Exception:
            pass

        # Strategy 3: Set localStorage/cookies to bypass on reload
        try:
            await page.evaluate("""
                () => {
                    // Common age-gate storage keys
                    const keys = [
                        'age_verified', 'ageVerified', 'age-verified',
                        'agegate', 'age_gate', 'ageGate',
                        'verified', 'isAdult', 'is_adult',
                        'over21', 'is_over_21', 'age_check'
                    ];
                    for (const key of keys) {
                        localStorage.setItem(key, 'true');
                        localStorage.setItem(key, '1');
                    }
                    // Set cookies
                    document.cookie = 'age_verified=true; path=/; max-age=86400';
                    document.cookie = 'ageVerified=true; path=/; max-age=86400';
                    document.cookie = 'agegate=true; path=/; max-age=86400';
                }
            """)
            print("  [popup] Set age verification cookies/localStorage as backup")
        except Exception:
            pass

    async def _dismiss_generic_popups(self, page: Page):
        """Close common popups, newsletter modals, cookie banners."""
        selectors = [
            "button[aria-label='Close']",
            "button.close",
            ".modal-close",
            "[data-dismiss='modal']",
            "button:has-text('No thanks')",
            "button:has-text('No Thanks')",
            "button:has-text('Close')",
            "button:has-text('Dismiss')",
            "button:has-text('Accept')",
            ".popup-close",
            "#cookie-accept",
            "button:has-text('Got it')",
            "button:has-text('Maybe Later')",
            "button:has-text('Not Now')",
            "[aria-label='close']",
            ".close-button",
            ".dismiss-button",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=500):
                    await btn.click(timeout=1000)
                    await page.wait_for_timeout(500)
            except Exception:
                pass
