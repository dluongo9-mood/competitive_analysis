"""
Keepa-based Supplement Product Search — fills in non-gummy form factors.

Uses Keepa's product search API to find capsules, tablets, powders, and
other non-gummy supplements. No browser needed — pure API.

Appends to amazon_supplements.csv (skips existing ASINs).

Usage:
    python3 scrape_keepa_supplement_search.py
    # Uses KEEPA_API_KEY env var or the hardcoded key
"""

import csv
import gzip
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse

API_KEY = os.environ.get("KEEPA_API_KEY", "v52qpv55p41ia2cis7rql3jaaokmev1ils4ckklut1fgqe24qoepf0ftq1ii6qoi")
INPUT_CSV = "amazon_supplements.csv"
KEEPA_BASE = "https://api.keepa.com"

# Non-gummy supplement searches
SEARCHES = [
    # Sleep
    "melatonin capsules", "melatonin tablets", "sleep aid capsules",
    # Stress
    "ashwagandha capsules", "ashwagandha powder", "magnesium capsules",
    "magnesium powder", "stress supplement capsules",
    # Energy
    "B12 capsules", "B12 tablets", "energy supplement capsules",
    "caffeine tablets", "iron supplement tablets",
    # Focus
    "nootropic capsules", "lion's mane capsules", "focus supplement capsules",
    # Immunity
    "elderberry capsules", "vitamin C tablets", "zinc tablets",
    "immune supplement capsules",
    # Digestion
    "probiotic capsules", "digestive enzyme capsules", "fiber powder",
    "psyllium husk powder",
    # Beauty
    "biotin tablets", "collagen powder", "collagen capsules",
    "hair skin nails capsules",
    # General
    "multivitamin tablets", "vitamin D capsules", "omega 3 softgels",
    "fish oil capsules",
    # Pain/Joint
    "turmeric capsules", "glucosamine chondroitin capsules",
    "joint supplement capsules",
    # Women
    "prenatal vitamins tablets", "prenatal capsules", "menopause supplement",
    # Men
    "testosterone booster capsules", "prostate supplement",
    # Weight
    "weight loss capsules", "metabolism supplement",
    # Mood
    "5-HTP capsules", "SAM-e tablets",
]

SUPPLEMENT_EFFECTS = {
    "Sleep":              r"sleep|melatonin|insomnia|night\s*time|rest|zzz",
    "Stress & Calm":      r"stress|calm|relax|ashwagandha|l-theanine|gaba|anxiety|cortisol",
    "Energy":             r"energy|caffeine|b12|b-12|vitamin\s*b|guarana|green\s*tea|maca",
    "Focus & Brain":      r"focus|brain|cognitive|nootropic|memory|lion.?s\s*mane|mental",
    "Immunity":           r"immun|elderberry|vitamin\s*c|zinc|echinacea",
    "Digestion":          r"digest|probiotic|prebiotic|gut|fiber|apple\s*cider|acv|bloat|enzyme",
    "Beauty":             r"biotin|collagen|hair|skin|nail|beauty|keratin",
    "General Wellness":   r"multivitamin|multi[\s-]*vitamin|vitamin\s*d|omega|fish\s*oil|daily",
    "Pain Relief":        r"joint|bone|turmeric|curcumin|glucosamine|calcium|vitamin\s*d3|pain|inflamm",
    "Women's Health":     r"pms|menstrual|period|prenatal|women|fertility|menopause|hormonal",
    "Men's Health":       r"testosterone|prostate|men.s\s*health|virility|libido",
    "Weight & Metabolism": r"weight|metabolism|appetite|keto|fat\s*burn|garcinia",
    "Mood":               r"\bmood\b|happy|serotonin|sam-e|5-htp|st\.?\s*john",
}

SUPPLEMENT_FORMS = {
    "Gummy":    r"gumm|chewy|chewable|gummi|jelly",
    "Capsule":  r"capsule|softgel|gel\s*cap|veggie\s*cap|vcap",
    "Tablet":   r"tablet|caplet",
    "Powder":   r"powder|mix\b|scoop",
    "Liquid":   r"liquid|tincture|drop|syrup|shot|elixir",
    "Lozenge":  r"lozenge|melt|dissolv",
}


def keepa_request(endpoint, params):
    params["key"] = API_KEY
    url = f"{KEEPA_BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "supplement-analysis/1.0",
        "Accept": "application/json", "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        try:
            data = json.loads(gzip.decompress(raw))
        except Exception:
            data = json.loads(raw)
    return data


def classify_form(title):
    lower = title.lower()
    for name, pattern in SUPPLEMENT_FORMS.items():
        if re.search(pattern, lower):
            return name
    return "Other"


def classify_effects(title):
    lower = title.lower()
    effects = []
    for name, pattern in SUPPLEMENT_EFFECTS.items():
        if re.search(pattern, lower):
            effects.append(name)
    return effects or ["General Wellness"]


def load_existing_asins():
    asins = set()
    try:
        with open(INPUT_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                asins.add(r.get("asin", ""))
    except FileNotFoundError:
        pass
    return asins


def append_products(new_products):
    """Append new products to the CSV."""
    fields = [
        "asin", "title", "brand", "formFactor", "useCase", "price", "listPrice",
        "rating", "reviewCount", "boughtPastMonth",
        "isBestSeller", "isAmazonChoice", "isSponsored",
        "searchQuery", "image", "url",
    ]
    with open(INPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        for p in new_products:
            writer.writerow({k: p.get(k, "") for k in fields})


def main():
    existing = load_existing_asins()
    print(f"Existing ASINs: {len(existing):,}")

    # Check tokens
    try:
        data = keepa_request("search", {"domain": 1, "type": "product", "term": "test", "page": 0})
        tokens = data.get("tokensLeft", 0)
        rate = data.get("refillRate", 1)
        print(f"Tokens: {tokens}, Refill: {rate}/min")
        if tokens < 5:
            wait = max(0, (10 - tokens) / max(rate, 1) * 60) + 10
            print(f"Waiting {wait:.0f}s for tokens...")
            time.sleep(wait)
    except Exception as e:
        if "429" in str(e):
            print("Rate limited. Waiting 15 min...")
            time.sleep(900)
        else:
            print(f"Error: {e}")
            return

    total_new = 0
    for i, term in enumerate(SEARCHES):
        print(f"\n[{i+1}/{len(SEARCHES)}] Searching: {term}")

        try:
            data = keepa_request("search", {
                "domain": 1, "type": "product", "term": term, "page": 0,
            })
        except Exception as e:
            if "429" in str(e):
                print(f"  Rate limited. Waiting 2 min...")
                time.sleep(120)
                continue
            print(f"  Error: {e}")
            continue

        asins = data.get("asinList", [])
        tokens = data.get("tokensLeft", 0)
        print(f"  Found {len(asins)} ASINs, tokens: {tokens}")

        new_asins = [a for a in asins if a not in existing]
        print(f"  New: {len(new_asins)}")

        if not new_asins:
            time.sleep(1)
            continue

        # Fetch product details in batches of 10
        for batch_start in range(0, len(new_asins), 10):
            batch = new_asins[batch_start:batch_start + 10]

            try:
                pdata = keepa_request("product", {
                    "domain": 1, "asin": ",".join(batch),
                })
            except Exception as e:
                if "429" in str(e):
                    print(f"  Rate limited on product fetch. Waiting 2 min...")
                    time.sleep(120)
                    continue
                print(f"  Product fetch error: {e}")
                continue

            tokens = pdata.get("tokensLeft", 0)
            products = pdata.get("products", [])
            new_rows = []

            for prod in products:
                asin = prod.get("asin", "")
                title = prod.get("title", "")
                if not title or asin in existing:
                    continue

                brand = prod.get("brand", "")
                # Current price (Amazon price in cents)
                csv_prices = prod.get("csv", [])
                price = None
                if csv_prices and len(csv_prices) > 0 and csv_prices[0]:
                    # Last value in the Amazon price series
                    arr = csv_prices[0]
                    for j in range(len(arr) - 1, 0, -2):
                        if arr[j] > 0:
                            price = arr[j] / 100.0
                            break

                # Sales rank for "bought past month" estimate
                sales_rank = None
                if csv_prices and len(csv_prices) > 3 and csv_prices[3]:
                    arr = csv_prices[3]
                    for j in range(len(arr) - 1, 0, -2):
                        if arr[j] > 0:
                            sales_rank = arr[j]
                            break

                rating = None
                review_count = None
                if csv_prices and len(csv_prices) > 16 and csv_prices[16]:
                    arr = csv_prices[16]
                    for j in range(len(arr) - 1, 0, -2):
                        if arr[j] > 0:
                            rating = arr[j] / 10.0
                            break
                if csv_prices and len(csv_prices) > 17 and csv_prices[17]:
                    arr = csv_prices[17]
                    for j in range(len(arr) - 1, 0, -2):
                        if arr[j] > 0:
                            review_count = arr[j]
                            break

                form_factor = classify_form(title)
                effects = classify_effects(title)

                new_rows.append({
                    "asin": asin,
                    "title": title,
                    "brand": brand,
                    "formFactor": form_factor,
                    "useCase": "|".join(effects),
                    "price": f"{price:.2f}" if price else "",
                    "rating": f"{rating:.1f}" if rating else "",
                    "reviewCount": str(review_count) if review_count else "",
                    "boughtPastMonth": "",  # Keepa doesn't have this directly
                    "searchQuery": term,
                    "url": f"https://www.amazon.com/dp/{asin}",
                })
                existing.add(asin)

            if new_rows:
                append_products(new_rows)
                total_new += len(new_rows)
                print(f"  +{len(new_rows)} products (total new: {total_new})")

            if tokens < 5:
                wait = max(0, (10 - tokens)) * 60 + 10
                print(f"  Low tokens ({tokens}). Waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                time.sleep(2)

        time.sleep(2)

    print(f"\n{'='*50}")
    print(f"Done! Added {total_new} new products to {INPUT_CSV}")


if __name__ == "__main__":
    main()
