"""
Amazon Supplement Scraper — All Form Factors by Use Case

Scrapes Amazon search results for supplement products across all major
functional categories (sleep, stress, energy, focus, immunity, etc.)
and all form factors (gummies, capsules, tablets, powders).

Outputs: amazon_supplements.csv

Run:
    python3 scrape_amazon_supplements.py
"""

import asyncio
import csv
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright

OUTPUT_CSV = "amazon_supplements.csv"

# ── Search queries: GENERIC FIRST then gummy-specific ────────────────────────
# Run generic queries first to capture capsules/tablets/powders before ASINs
# get claimed by gummy queries. This reduces gummy bias.
SEARCH_QUERIES = [
    # ── GENERIC SUPPLEMENT QUERIES (run first) ──
    # Sleep
    "sleep supplement", "melatonin supplement", "melatonin capsules",
    "sleep aid tablets", "melatonin tablets",
    # Stress & Calm
    "calm supplement", "ashwagandha supplement", "ashwagandha capsules",
    "stress relief supplement", "magnesium supplement", "magnesium capsules",
    # Energy
    "energy supplement", "B12 supplement", "B12 tablets",
    "energy vitamins", "caffeine pills",
    # Focus & Brain
    "brain supplement", "nootropic supplement", "nootropic capsules",
    "focus supplement", "lion's mane supplement", "lion's mane capsules",
    # Immunity
    "immune support supplement", "elderberry supplement", "elderberry capsules",
    "vitamin C supplement", "vitamin C tablets", "zinc supplement",
    # Digestion
    "probiotic supplement", "probiotic capsules", "digestive supplement",
    "fiber supplement", "fiber powder", "digestive enzymes",
    # Beauty
    "biotin supplement", "biotin tablets", "collagen supplement",
    "collagen powder", "hair skin nails supplement",
    # General Wellness
    "multivitamin supplement", "multivitamin tablets", "vitamin D supplement",
    "vitamin D capsules", "omega 3 supplement", "fish oil capsules",
    # Pain Relief
    "turmeric supplement", "turmeric capsules", "joint supplement",
    "glucosamine supplement", "glucosamine chondroitin",
    # Women's Health
    "prenatal vitamins", "prenatal supplement", "women's multivitamin",
    "menopause supplement", "PMS supplement",
    # Men's Health
    "testosterone supplement", "testosterone capsules",
    "men's multivitamin", "prostate supplement",
    # Weight & Metabolism
    "weight loss supplement", "weight loss pills",
    "appetite suppressant", "metabolism supplement",
    # Mood
    "mood supplement", "5-HTP supplement", "5-HTP capsules",
    "SAM-e supplement", "SAM-e tablets",
    # ── GUMMY-SPECIFIC QUERIES (run second, capture remaining) ──
    "melatonin gummies", "sleep gummies",
    "ashwagandha gummies", "stress relief gummies", "magnesium gummies",
    "energy gummies", "caffeine gummies", "B12 gummies",
    "focus gummies", "nootropic gummies", "lion's mane gummies",
    "elderberry gummies", "immunity gummies", "vitamin C gummies", "zinc gummies",
    "probiotic gummies", "digestive gummies", "apple cider vinegar gummies", "fiber gummies",
    "biotin gummies", "collagen gummies", "hair skin nails gummies",
    "multivitamin gummies", "vitamin D gummies", "omega 3 gummies",
    "turmeric gummies", "calcium gummies",
    "PMS gummies", "women's health gummies", "prenatal gummies",
    "testosterone gummies",
    "weight loss gummies", "metabolism gummies",
    "mood gummies supplement",
]

# ── Use case classification ──────────────────────────────────────────────────
SUPPLEMENT_EFFECTS = {
    "Sleep":              r"sleep|melatonin|insomnia|night\s*time|rest|zzz|calm\s*sleep|nighttime",
    "Stress & Calm":      r"stress|calm|relax|ashwagandha|l-theanine|gaba|anxiety|cortisol",
    "Energy":             r"energy|caffeine|b12|b-12|vitamin\s*b|guarana|green\s*tea|maca",
    "Focus & Brain":      r"focus|brain|cognitive|nootropic|memory|concentration|lion.?s\s*mane|mental",
    "Immunity":           r"immun|elderberry|vitamin\s*c|zinc|echinacea",
    "Digestion":          r"digest|probiotic|prebiotic|gut|fiber|apple\s*cider|acv|bloat",
    "Beauty":             r"biotin|collagen|hair|skin|nail|beauty|keratin",
    "General Wellness":   r"multivitamin|multi[\s-]*vitamin|vitamin\s*d|omega|fish\s*oil|daily",
    "Joint & Bone":       r"joint|bone|turmeric|curcumin|glucosamine|calcium|vitamin\s*d3",
    "Women's Health":     r"pms|menstrual|period|prenatal|women|fertility|menopause|hormonal",
    "Men's Health":       r"testosterone|prostate|men.s\s*health|virility|libido",
    "Weight & Metabolism": r"weight|metabolism|appetite|keto|fat\s*burn|garcinia|thermogenic",
    "Mood":               r"\bmood\b|happy|serotonin|sam-e|5-htp|st\.?\s*john|depression",
}

# ── Form factor classification ───────────────────────────────────────────────
SUPPLEMENT_FORMS = {
    "Gummy":    r"gumm|chewy|chewable|gummi|jelly|gummie",
    "Capsule":  r"capsule|softgel|gel\s*cap|veggie\s*cap|vcap|caps\b",
    "Tablet":   r"tablet|caplet|chew\b|chews\b",
    "Powder":   r"powder|mix\b|scoop|drink\s*mix",
    "Liquid":   r"liquid|tincture|drop|syrup|shot|elixir|spray",
    "Lozenge":  r"lozenge|melt|dissolv|sublingual",
}

# ── Exclude junk ─────────────────────────────────────────────────────────────
EXCLUDE_PATTERNS = [
    r"t-shirt|hoodie|hat|cap|poster|sticker|mug|phone case|bag|backpack",
    r"dog|cat|pet|puppy|kitten|canine|feline",
    r"book|guide|cookbook|ebook",
    r"shampoo|conditioner|body\s*wash|lotion|cream|soap|deodorant",
    r"kratom|kava",
    r"candy|chocolate bar|cookie|brownie",
    r"face\s*mask|sheet\s*mask",
]
EXCLUDE_RE = re.compile("|".join(EXCLUDE_PATTERNS), re.IGNORECASE)


def classify_use_cases(title):
    """Return list of matching use cases from title."""
    effects = []
    lower = title.lower()
    for name, pattern in SUPPLEMENT_EFFECTS.items():
        if re.search(pattern, lower):
            effects.append(name)
    return effects


def classify_form_factor(title):
    """Return form factor from title."""
    lower = title.lower()
    for name, pattern in SUPPLEMENT_FORMS.items():
        if re.search(pattern, lower):
            return name
    return "Other"


def is_relevant(title):
    """Filter out non-supplement products."""
    if EXCLUDE_RE.search(title):
        return False
    lower = title.lower()
    # Must look like a supplement / consumable
    supp_words = r"supplement|vitamin|gumm|capsule|tablet|softgel|powder|tincture|probiotic|prebiotic|extract|herbal|mg\b|\bcount\b|\bct\b"
    if not re.search(supp_words, lower):
        return False
    return True


EXTRACT_JS = """
() => {
    const items = [];
    const cards = document.querySelectorAll('[data-asin]');

    for (const card of cards) {
        const asin = card.getAttribute('data-asin');
        if (!asin || asin.length < 5) continue;

        const titleEl = card.querySelector('h2 a span, h2 span');
        if (!titleEl) continue;

        const title = titleEl.textContent.trim();
        if (!title) continue;

        // Price
        const priceWhole = card.querySelector('.a-price .a-price-whole');
        const priceFraction = card.querySelector('.a-price .a-price-fraction');
        let price = null;
        if (priceWhole) {
            price = priceWhole.textContent.replace(/[^0-9]/g, '');
            if (priceFraction) price += '.' + priceFraction.textContent.replace(/[^0-9]/g, '');
            else price += '.00';
        }

        // List price
        const listPriceEl = card.querySelector('.a-price.a-text-price .a-offscreen');
        const listPrice = listPriceEl ? listPriceEl.textContent.trim() : '';

        // Rating
        const ratingEl = card.querySelector('.a-icon-star-small .a-icon-alt, .a-icon-star-mini .a-icon-alt');
        let rating = null;
        if (ratingEl) {
            const m = ratingEl.textContent.match(/([\d.]+)/);
            if (m) rating = m[1];
        }

        // Review count
        let reviewCount = null;
        const revLink = card.querySelector('a[href*="#customerReviews"]');
        if (revLink) {
            const aria = revLink.getAttribute('aria-label') || '';
            const m = aria.match(/([\d,]+)/);
            if (m) reviewCount = m[1].replace(/,/g, '');
            else {
                const txt = revLink.textContent.replace(/[^0-9]/g, '');
                if (txt) reviewCount = txt;
            }
        }
        if (!reviewCount) {
            const csaContainer = card.querySelector('[data-csa-c-content-id*="customer-ratings-count"] a');
            if (csaContainer) {
                const aria = csaContainer.getAttribute('aria-label') || '';
                const m = aria.match(/([\d,]+)/);
                if (m) reviewCount = m[1].replace(/,/g, '');
            }
        }

        // Bought past month
        const boughtEl = card.querySelector('.a-row.a-size-base .a-size-base.a-color-secondary');
        let boughtPastMonth = '';
        if (boughtEl && /bought/i.test(boughtEl.textContent)) {
            boughtPastMonth = boughtEl.textContent.trim();
        }

        // Badges
        const isBestSeller = !!card.querySelector('[data-component-type="s-status-badge-component"]');
        const isAmazonChoice = !!card.querySelector('.a-badge-text');
        const isSponsored = !!card.querySelector('.a-color-secondary:has(> .a-text-bold)') ||
                           !!card.querySelector('[data-component-type="sp-sponsored-result"]');

        // Image
        const imgEl = card.querySelector('img.s-image');
        const image = imgEl ? imgEl.src : '';

        // URL
        const linkEl = card.querySelector('h2 a');
        const url = linkEl ? 'https://www.amazon.com' + linkEl.getAttribute('href').split('?')[0] : '';

        items.push({
            asin, title, price, listPrice,
            rating, reviewCount: reviewCount || '',
            isBestSeller: String(isBestSeller),
            isAmazonChoice: String(isAmazonChoice),
            isSponsored: String(isSponsored),
            boughtPastMonth,
            image, url
        });
    }
    return items;
}
"""


def load_existing():
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            return {r["asin"]: r for r in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


FIELDS = [
    "asin", "title", "brand", "formFactor", "useCase", "price", "listPrice",
    "rating", "reviewCount", "boughtPastMonth",
    "isBestSeller", "isAmazonChoice", "isSponsored",
    "searchQuery", "image", "url",
]


def save_results(all_products):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for p in all_products:
            writer.writerow({k: p.get(k, "") for k in FIELDS})


def extract_brand(title):
    """Best-effort brand extraction from Amazon title.
    Pattern: brand names usually appear as the first capitalized phrase before a dash or product descriptor."""
    # Check for 'Brand: X' pattern
    m = re.match(r"^([A-Z][A-Za-z'&\.\s]{1,30}?)[\s]*[-–—|]", title)
    if m:
        brand = m.group(1).strip()
        # Filter generic words
        generic = {"New", "Premium", "Extra", "Advanced", "Natural", "Organic", "Pure",
                   "Ultra", "Super", "Best", "High", "Max", "Pro", "The"}
        if brand not in generic and len(brand) > 1:
            return brand
    # Fallback: first 1-3 capitalized words
    m = re.match(r"^([A-Z][A-Za-z'&\.]+(?:\s[A-Z][A-Za-z'&\.]+){0,2})\s", title)
    if m:
        brand = m.group(1).strip()
        generic = {"New", "Premium", "Extra", "Advanced", "Natural", "Organic", "Pure",
                   "Ultra", "Super", "Best", "High", "Max", "Pro", "The", "Pack",
                   "Count", "Vitamin", "Supplement", "Gummies", "Capsules", "Tablets"}
        words = brand.split()
        if words and words[0] not in generic:
            return brand
    return ""


async def scrape_query(page, query, existing_asins):
    """Scrape all pages for a given search query."""
    products = []
    base_url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}&s=exact-aware-popularity-rank"

    for page_num in range(1, 21):  # Up to 20 pages per query
        url = f"{base_url}&page={page_num}" if page_num > 1 else base_url
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2000)

            items = await page.evaluate(EXTRACT_JS)
            if not items:
                print(f"    Page {page_num}: no results, stopping")
                break

            new = 0
            for item in items:
                if item["asin"] in existing_asins:
                    continue
                if not is_relevant(item["title"]):
                    continue

                # Classify
                item["formFactor"] = classify_form_factor(item["title"])
                use_cases = classify_use_cases(item["title"])
                item["useCase"] = "|".join(use_cases) if use_cases else "General Wellness"
                item["brand"] = extract_brand(item["title"])
                item["searchQuery"] = query

                products.append(item)
                existing_asins.add(item["asin"])
                new += 1

            print(f"    Page {page_num}: {len(items)} items, {new} new (relevant)")

            # Check for "next" button
            has_next = await page.evaluate("""
                () => !!document.querySelector('.s-pagination-next:not(.s-pagination-disabled)')
            """)
            if not has_next:
                break

            await page.wait_for_timeout(1500)

        except Exception as e:
            print(f"    Page {page_num} error: {e}")
            break

    return products


async def main():
    existing = load_existing()
    existing_asins = set(existing.keys())
    all_products = list(existing.values())
    print(f"Existing products: {len(all_products)}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await ctx.new_page()

        # Warm up session
        print("Establishing session...")
        await page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3000)
        print("Session ready.\n")

        for i, query in enumerate(SEARCH_QUERIES):
            print(f"[{i+1}/{len(SEARCH_QUERIES)}] Searching: {query}")
            products = await scrape_query(page, query, existing_asins)
            all_products.extend(products)
            print(f"  → {len(products)} new products (total: {len(all_products):,})\n")
            save_results(all_products)

            # Brief pause between queries to avoid rate limiting
            if i < len(SEARCH_QUERIES) - 1:
                await page.wait_for_timeout(2000)

        await browser.close()

    save_results(all_products)

    # Summary
    forms = {}
    effects = {}
    for p in all_products:
        ff = p.get("formFactor", "Other")
        forms[ff] = forms.get(ff, 0) + 1
        for uc in p.get("useCase", "").split("|"):
            if uc:
                effects[uc] = effects.get(uc, 0) + 1

    print(f"\n{'='*50}")
    print(f"Done! {len(all_products):,} total products → {OUTPUT_CSV}")
    print(f"\nForm Factors:")
    for ff, n in sorted(forms.items(), key=lambda x: -x[1]):
        print(f"  {ff:15s} {n:,}")
    print(f"\nUse Cases:")
    for uc, n in sorted(effects.items(), key=lambda x: -x[1]):
        print(f"  {uc:20s} {n:,}")


if __name__ == "__main__":
    asyncio.run(main())
