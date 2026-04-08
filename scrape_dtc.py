"""
DTC THC Gummy Brand Scraper — Shopify /products.json API

Queries known hemp-derived THC/CBD gummy brand Shopify stores.

Outputs: dtc_gummies.csv

Run:
    python3 scrape_dtc.py
"""

import asyncio
import csv
import json
import re
import time
import urllib.request
from pathlib import Path

OUTPUT_CSV = "dtc_gummies.csv"

FIELDS = [
    "productId", "brand", "shopDomain", "productName", "productType",
    "price", "compareAtPrice", "formFactor", "thcType", "cannabinoids",
    "variantCount", "tags", "url",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Known Shopify THC/CBD gummy brand stores
SHOPS = [
    ("3Chi",                "3chi.com"),
    ("Delta Extrax",        "deltaextrax.com"),
    ("Hometown Hero",       "hometownherocbd.com"),
    ("Koi CBD",             "koicbd.com"),
    ("Diamond CBD",         "diamondcbd.com"),
    ("Exhale Wellness",     "exhalewell.com"),
    ("Budpop",              "budpop.com"),
    ("Moonwlkr",            "moonwlkr.com"),
    ("Binoid",              "binoidcbd.com"),
    ("Elyxr",               "elyxr.com"),
    ("Urb",                 "urb.shop"),
    ("TRĒ House",           "trehouse.com"),
    ("Mr. Hemp Flower",     "mrhempflower.com"),
    ("Viia Hemp",           "viiahemp.com"),
    ("Delta Munchies",      "deltamunchies.com"),
    ("Otter Space",         "otterspacecbd.com"),
    ("Sunday Scaries",      "sundayscaries.com"),
    ("cbdMD",               "cbdmd.com"),
    ("Charlotte's Web",     "charlottesweb.com"),
    ("Joy Organics",        "joyorganics.com"),
    ("Cornbread Hemp",      "cornbreadhemp.com"),
    ("Five CBD",            "fivecbd.com"),
    ("Medterra",            "medterracbd.com"),
    ("Batch CBD",           "mybatchcbd.com"),
    ("Plain Jane",          "plainjane.com"),
    ("Green Roads",         "greenroads.com"),
    ("Social CBD",          "socialcbd.com"),
    ("Tillmans Tranquils",  "tillmanstranquils.com"),
    ("Cycling Frog",        "cyclingfrog.com"),
    ("WYLD",                "wyldcbd.com"),
    ("Cheef Botanicals",    "cheefbotanicals.com"),
    ("Galaxy Treats",       "galaxytreats.com"),
    ("Hemp Bombs",          "hempbombs.com"),
    ("Verma Farms",         "vermafarms.com"),
    ("Just CBD",            "justcbdstore.com"),
    ("Feals",               "feals.com"),
    ("Neurogan",            "neurogan.com"),
    ("Secret Nature",       "secretnaturecbd.com"),
    ("Area 52",             "area52.com"),
    ("Kanha",               "kanhalife.com"),
    ("Mood",                "checkout.mood.com"),
    # Wave 2 — Brightfield top companies + industry lists
    ("Lazarus Naturals",    "lazarusnaturals.com"),
    ("Extract Labs",        "extractlabs.com"),
    ("SunMed",              "sunmed.com"),
    ("R+R Medicinals",      "randrmed.com"),
    ("Slumber",             "slumbercbn.com"),
    ("Sky Wellness",        "skywellness.com"),
    ("Penguin CBD",         "penguincbd.com"),
    ("Mystic Labs",         "mysticlabsd8.com"),
    ("BioBliss",            "biobliss.com"),
    ("Bloom Hemp",          "bloomhemp.com"),
    ("Vida Optima",         "vidaoptimacbd.com"),
    ("Eden's Herbals",      "edensherbals.com"),
    ("JustDelta",           "justdelta.com"),
    ("Harbor City Hemp",    "harborcityhemp.com"),
    ("Botany Farms",        "botanyfarms.com"),
    ("Boston Hempire",      "bostonhempire.com"),
    ("Canna River",         "cannariver.com"),
    ("Flying Monkey",       "flyingmonkeyusa.com"),
    ("Hi On Nature",        "hiondelta8.com"),
    ("No Cap Hemp Co",      "nocaphempco.com"),
    ("Snapdragon",          "snapdragonhemp.com"),
    ("Torch",               "torchenterprise.com"),
    ("Vena CBD",            "venacbd.com"),
    ("Wana",                "wana.com"),
    ("CANN",                "drinkcann.com"),
    ("Kiva Confections",    "kivaconfections.com"),
    ("Plus Products",       "plusproducts.com"),
    ("Camino",              "camino.plus"),
    ("Toast",               "enjoytoast.com"),
    ("BREZ",                "drinkbrez.com"),
    ("Mellow Fellow",       "mellowfellow.fun"),
    ("Crescent Canna",      "crescentcanna.com"),
    # Wave 3 — discovered via brand research
    # THC-forward
    ("Dad Grass",           "dadgrass.com"),
    ("Royal CBD",           "royalcbd.com"),
    ("Summit THC",          "summitthc.com"),
    ("Eighty Six",          "eightysixbrand.com"),
    ("CBDfx",               "cbdfx.com"),
    ("Frosty Hemp Co",      "frostyhempco.com"),
    ("ElevateRight",        "elevateright.com"),
    ("BioWellnessX",        "biowellnessx.com"),
    ("The Hemp Doctor",     "thehempdoctor.com"),
    ("The Hemp Collect",    "thehempcollect.com"),
    ("JustKana",            "justkana.com"),
    ("Lumi Labs",           "lumigummies.com"),
    ("Kush Queen",          "kushqueen.shop"),
    ("WYNK",                "drinkwynk.com"),
    ("25 Hour Farms",       "25hourfarms.com"),
    # CBD + functional
    ("Naternal",            "naternal.com"),
    ("Wild Theory",         "wildtheory.com"),
    ("Redeem Therapeutics", "redeemrx.com"),
    ("Uncle Bud's",         "unclebudshemp.com"),
    ("PlusCBD",             "pluscbdoil.com"),
    ("Happy Hemp",          "gethappyhemp.com"),
    ("Rare Cannabinoid Co", "rarecannabinoidco.com"),
    ("Black Tie CBD",       "blacktiecbd.net"),
    # Sleep / functional specific
    ("Snoozy",              "getsnoozy.com"),
    ("Dizzies",             "dizziesfun.com"),
    ("Cannabis Life",       "cannabislife.com"),
    # Wave 4 — Brightfield top companies (missing domains filled in)
    ("Enjoy Hemp",          "enjoyhemp.com"),
    ("HoneyRoot Wellness",  "honeyrootwellness.com"),
    ("Space Gods",          "spacegods.com"),
    ("STIIIZY Hemp",        "stiiizyhemp.com"),
    ("PURLYF",              "purlyf.com"),
    ("Smilyn Wellness",     "smilynwellness.com"),
    ("Happi Hemp",          "happihemp.com"),
    ("XITE",                "xitedibles.com"),
    ("CannaAid",            "cannaaidshop.com"),
    ("Hidden Hills Club",   "hiddenhillsclub.com"),
    ("WNC CBD",             "wnccbd.com"),
    ("Nowadays",            "hellonowadays.com"),
    # Cake — large brand but controversial (counterfeit issues); skip for now
    # Cookies — dispensary-first brand, hemp line exists but no clear DTC site
]


# Cannabinoid type detection
CANNABINOID_PATTERNS = [
    ("Delta-9 THC",  [r"delta[\s-]*9", r"d9[\s-]thc", r"d9\b", r"\bΔ9"]),
    ("Delta-8 THC",  [r"delta[\s-]*8", r"d8[\s-]thc", r"d8\b", r"\bΔ8"]),
    ("CBD",          [r"\bcbd\b", r"cannabidiol"]),
    ("CBN",          [r"\bcbn\b", r"cannabinol"]),
    ("CBG",          [r"\bcbg\b", r"cannabigerol"]),
    ("THC-V",        [r"\bthcv\b", r"thc[\s-]*v\b"]),
    ("THC-P",        [r"\bthcp\b", r"thc[\s-]*p\b"]),
    ("HHC",          [r"\bhhc\b"]),
    ("THC-A",        [r"\bthca\b", r"thc[\s-]*a\b"]),
    ("Full Spectrum", [r"full[\s-]*spectrum"]),
    ("Broad Spectrum", [r"broad[\s-]*spectrum"]),
]

# THC type classification
THC_TYPE_RULES = [
    ("Delta-8",       [r"delta[\s-]*8", r"\bd8\b", r"\bΔ8"]),
    ("Delta-9",       [r"delta[\s-]*9", r"\bd9\b", r"\bΔ9"]),
    ("THC-A",         [r"\bthca\b", r"thc[\s-]*a\b"]),
    ("THC-P",         [r"\bthcp\b", r"thc[\s-]*p\b"]),
    ("THC-V",         [r"\bthcv\b"]),
    ("HHC",           [r"\bhhc\b"]),
    ("Full Spectrum",  [r"full[\s-]*spectrum"]),
    ("CBD Only",      [r"\bcbd\b"]),
]

FORM_FACTOR_RULES = [
    ("Gummy",      [r"gumm(?:y|ies)", r"chew(?:able)?s?"]),
    ("Tincture",   [r"tincture", r"drops?", r"oil\b"]),
    ("Vape",       [r"vape", r"cartridge", r"disposable", r"pen\b"]),
    ("Edible",     [r"chocolate", r"cookie", r"brownie", r"candy", r"caramel"]),
    ("Capsule",    [r"capsule", r"softgel", r"pill"]),
    ("Flower",     [r"flower", r"pre[\s-]*roll", r"joint"]),
    ("Topical",    [r"cream", r"balm", r"salve", r"lotion", r"topical"]),
    ("Beverage",   [r"seltzer", r"drink", r"shot\b", r"sparkling"]),
]


def extract_cannabinoids(text):
    found = []
    t = (text or "").lower()
    for name, patterns in CANNABINOID_PATTERNS:
        if any(re.search(p, t) for p in patterns):
            found.append(name)
    return ", ".join(found) if found else ""


def classify_thc_type(text):
    t = (text or "").lower()
    for label, patterns in THC_TYPE_RULES:
        if any(re.search(p, t) for p in patterns):
            return label
    return "Other"


def infer_form_factor(text):
    t = (text or "").lower()
    for label, patterns in FORM_FACTOR_RULES:
        if any(re.search(p, t) for p in patterns):
            return label
    return "Other"


def is_relevant(text):
    """Check if product is THC/CBD related."""
    t = (text or "").lower()
    kw = ["thc", "cbd", "delta", "hemp", "cannabin", "hhc", "gumm", "full spectrum",
          "broad spectrum", "cbn", "cbg", "cannabis", "d8", "d9"]
    return any(k in t for k in kw)


def fetch_all_products(domain):
    """Try Shopify /products.json API first."""
    products = []
    page = 1
    while True:
        url = f"https://{domain}/products.json?limit=250&page={page}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            if page == 1:
                # API blocked — try Playwright fallback
                return None  # signal to use fallback
            print(f"    Error page {page}: {e}")
            break

        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
        time.sleep(0.5)

    return products


PLAYWRIGHT_EXTRACT_JS = """
() => {
    const products = [];
    // Try common product card selectors across Shopify themes
    const selectors = [
        '.product-card', '.product-item', '[class*="ProductCard"]',
        '.grid-product', '.product-block', '.collection-product',
        '[data-product-card]', '.product__card', '.product-tile',
        '.boost-pfs-filter-product-item',
    ];
    let cards = [];
    for (const sel of selectors) {
        cards = document.querySelectorAll(sel);
        if (cards.length > 0) break;
    }
    // Fallback: look for product links
    if (cards.length === 0) {
        cards = document.querySelectorAll('a[href*="/products/"]');
    }
    const seen = new Set();
    for (const card of cards) {
        const linkEl = card.tagName === 'A' ? card : card.querySelector('a[href*="/products/"]');
        const href = linkEl ? linkEl.href : null;
        if (!href || seen.has(href)) continue;
        seen.add(href);

        const nameEl = card.querySelector('h2, h3, h4, [class*="title"], [class*="name"]');
        const name = nameEl ? nameEl.textContent.trim() : (linkEl ? linkEl.textContent.trim().split('\\n')[0] : '');
        if (!name || name.length < 3) continue;

        const priceEl = card.querySelector('[class*="price"], .money, [class*="Price"]');
        let price = null;
        if (priceEl) {
            const m = priceEl.textContent.match(/\\$(\\d+(?:\\.\\d+)?)/);
            if (m) price = m[1];
        }

        products.push({
            title: name,
            handle: href.split('/products/')[1]?.split('?')[0] || '',
            price: price,
            url: href,
        });
    }
    return products;
}
"""


async def fetch_products_playwright(domain):
    """Fallback: scrape product listings with Playwright for blocked Shopify stores."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("    Playwright not available for fallback")
        return []

    products = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = await ctx.new_page()

        # Try /collections/all first (most Shopify stores), then /products
        for path in ["/collections/all", "/products", "/collections"]:
            url = f"https://{domain}{path}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                await page.wait_for_timeout(3000)

                items = await page.evaluate(PLAYWRIGHT_EXTRACT_JS)
                if items:
                    products.extend(items)
                    print(f"    Playwright: {len(items)} products from {path}")

                    # Try to paginate — scroll down and check for more
                    for _ in range(5):
                        prev_count = len(products)
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(2000)
                        more = await page.evaluate(PLAYWRIGHT_EXTRACT_JS)
                        new_items = [i for i in more
                                     if i.get("url") not in {p.get("url") for p in products}]
                        if not new_items:
                            break
                        products.extend(new_items)

                    break  # got products, stop trying paths
            except Exception as e:
                continue

        await browser.close()

    # Convert to Shopify-like format
    formatted = []
    for item in products:
        formatted.append({
            "id": hash(item.get("url", "")),
            "title": item.get("title", ""),
            "handle": item.get("handle", ""),
            "product_type": "",
            "tags": [],
            "body_html": "",
            "variants": [{"price": item.get("price")}] if item.get("price") else [],
        })
    return formatted


def process_product(brand, domain, raw):
    name = raw.get("title", "")
    body = raw.get("body_html", "") or ""
    ptype = raw.get("product_type", "")
    tags = ", ".join(raw.get("tags", []))
    full_text = f"{name} {body} {ptype} {tags}"

    # Get price from first variant
    variants = raw.get("variants", [])
    price = None
    compare_price = None
    if variants:
        price = variants[0].get("price")
        compare_price = variants[0].get("compare_at_price")

    return {
        "productId": raw.get("id"),
        "brand": brand,
        "shopDomain": domain,
        "productName": name,
        "productType": ptype,
        "price": price,
        "compareAtPrice": compare_price,
        "formFactor": infer_form_factor(full_text),
        "thcType": classify_thc_type(full_text),
        "cannabinoids": extract_cannabinoids(full_text),
        "variantCount": len(variants),
        "tags": tags,
        "url": f"https://{domain}/products/{raw.get('handle', '')}",
    }


def main():
    all_products = []
    shopify_ok = 0
    playwright_ok = 0
    failed = 0

    for brand, domain in SHOPS:
        print(f"  {brand} ({domain})...")
        raw_products = None
        try:
            raw_products = fetch_all_products(domain)
        except Exception as e:
            print(f"    Shopify API error: {e}")

        # Playwright fallback for blocked stores
        if raw_products is None:
            print(f"    Shopify API blocked — trying Playwright...")
            try:
                raw_products = asyncio.run(fetch_products_playwright(domain))
                if raw_products:
                    playwright_ok += 1
                else:
                    print(f"    Playwright: no products found")
                    failed += 1
                    continue
            except Exception as e:
                print(f"    Playwright failed: {e}")
                failed += 1
                continue
        else:
            if raw_products:
                shopify_ok += 1
            else:
                failed += 1
                continue

        relevant = 0
        for raw in raw_products:
            name = raw.get("title", "")
            body = raw.get("body_html", "") or ""
            ptype = raw.get("product_type", "")
            tags = ", ".join(raw.get("tags", []))
            full_text = f"{name} {body} {ptype} {tags}"

            if not is_relevant(full_text):
                continue

            product = process_product(brand, domain, raw)
            all_products.append(product)
            relevant += 1

        print(f"    {len(raw_products)} total, {relevant} relevant")
        time.sleep(1)

    # Save
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_products)

    print(f"\nDone! {len(all_products):,} products → {OUTPUT_CSV}")
    print(f"  Shopify API: {shopify_ok} | Playwright fallback: {playwright_ok} | Failed: {failed}")


if __name__ == "__main__":
    main()
