"""
Supplement Market Dashboard Builder

Reads amazon_supplements.csv and generates supplement_dashboard.html
with two Marimekko charts and a use case summary table.

Run:
    python3 build_supplement_dashboard.py
"""

import csv
import math
import re
from collections import defaultdict
from pathlib import Path

import plotly.graph_objects as go

INPUT_CSV = "amazon_supplements.csv"
BRIGHTFIELD_XLSX = "brightfield_hemp_thc.xlsx"
OUTPUT_HTML = "supplement_dashboard.html"

# Mood's current product lines — used to flag coverage in summary table
# Mood's actual product lines mapped to supplement use cases
# Source: Mood product catalog (Voice AI Agents/products.csv)
MOOD_PRODUCTS = {
    "Sleep": "Sleepytime Gummies (THC+CBN, Sleepy)",
    "Stress & Calm": "Chillout Gummies (D8, Chill)",
    "Energy": "Morning Gummies (D9, Energized)",
    "Immunity": "Immune Support Gummies (Happy)",
    "Pain Relief": "Pure Relief CBD Gummies (Soothing)",
    "Intimacy": "Sexual Euphoria Gummies (Aroused)",
    "Men's Health": "Testosterone Support Gummies (Functional)",
    "Women's Health": "PMS + Menopause Relief Gummies",
}
MOOD_CATEGORIES = set(MOOD_PRODUCTS.keys())

# ── Sub-categories for granular breakdown ────────────────────────────────────
SUB_CATEGORIES = {
    "Women's Health": {
        "PMS/Menstrual": r"pms|menstrual|period|cramp",
        "Prenatal": r"prenatal|pregnan|folic acid",
        "Menopause": r"menopause|hot flash|black cohosh",
        "Fertility": r"fertil|conceiv|ovulat",
        "Vaginal Health": r"vaginal|ph balance|yeast|uro\b",
    },
    "General Wellness": {
        "Multivitamin": r"multivitamin|multi[\s-]*vitamin|one\s*a\s*day",
        "Vitamin D": r"vitamin\s*d|d3\b",
        "Omega/Fish Oil": r"omega|fish\s*oil|dha|epa",
        "Iron": r"\biron\b|ferr",
        "Magnesium": r"magnesium",
    },
    "Beauty": {
        "Hair Growth": r"hair\s*growth|hair\s*loss|thinning",
        "Skin/Anti-Aging": r"skin|anti[\s-]*aging|wrinkle|collagen",
        "Nails": r"\bnail",
        "Biotin": r"biotin",
    },
    "Digestion": {
        "Probiotics": r"probiotic",
        "Fiber": r"fiber|psyllium",
        "ACV/Detox": r"apple\s*cider|acv|detox|cleans",
        "Digestive Enzymes": r"enzyme|digest.*support",
        "Bloating": r"bloat|gas\b|debloat",
    },
    "Stress & Calm": {
        "Ashwagandha": r"ashwagandha",
        "Magnesium (Calm)": r"magnesium.*calm|calm.*magnesium",
        "GABA/L-Theanine": r"gaba|l-theanine|theanine",
        "Cortisol": r"cortisol|adrenal",
    },
    "Focus & Brain": {
        "Lion's Mane": r"lion.?s\s*mane",
        "Nootropics": r"nootropic",
        "Memory": r"memory|cognitive|prevagen|neuriva",
        "Focus": r"focus|concentrat|attention",
    },
    "Pain Relief": {
        "Turmeric/Curcumin": r"turmeric|curcumin",
        "Glucosamine/Joint": r"glucosamine|chondroitin|joint",
        "General Pain": r"pain|inflamm|ache",
    },
    "Mood": {
        "5-HTP/Serotonin": r"5-htp|serotonin",
        "SAM-e": r"sam-e",
        "St. John's Wort": r"st\.?\s*john",
        "General Mood": r"\bmood\b|happy",
    },
    "Men's Health": {
        "Testosterone": r"testosterone|test\s*boost",
        "Prostate": r"prostate",
        "Virility/Libido": r"virility|libido|male\s*enhance",
    },
    "Sleep": {
        "Melatonin": r"melatonin",
        "Magnesium (Sleep)": r"magnesium.*sleep|sleep.*magnesium",
        "Herbal Sleep": r"valerian|chamomile|passionflower|lavender",
        "CBN/CBD Sleep": r"cbn|cbd.*sleep|sleep.*cbd",
    },
    "Energy": {
        "Caffeine": r"caffeine|green\s*tea.*extract",
        "B Vitamins": r"b12|b-12|vitamin\s*b|b\s*complex",
        "Maca/Adaptogens": r"maca|ginseng|rhodiola",
        "Creatine": r"creatine",
    },
    "Immunity": {
        "Elderberry": r"elderberry|sambucus",
        "Vitamin C": r"vitamin\s*c|ascorbic",
        "Zinc": r"\bzinc\b",
        "Mushroom Immune": r"mushroom.*immun|reishi|chaga|turkey\s*tail",
    },
    "Weight & Metabolism": {
        "ACV/Keto": r"apple\s*cider|acv|keto",
        "Appetite Control": r"appetite|hunger|satiet",
        "Fat Burn": r"fat\s*burn|thermogenic|garcinia|green\s*coffee",
        "GLP-1/Berberine": r"glp|berberine",
    },
}

# ── THC relevance scoring ────────────────────────────────────────────────────
THC_RELEVANCE = {
    "Sleep": 0.95,
    "Stress & Calm": 0.90,
    "Pain Relief": 0.85,
    "Mood": 0.80,
    "Intimacy": 0.70,
    "Energy": 0.60,
    "Focus & Brain": 0.50,
    "Women's Health": 0.40,
    "Men's Health": 0.35,
    "Immunity": 0.30,
    "Weight & Metabolism": 0.15,
    "General Wellness": 0.10,
    "Digestion": 0.15,
    "Beauty": 0.05,
}


def classify_subcategories(title, use_cases):
    """Classify product into sub-categories based on title and parent use cases."""
    lower = _normalize(title.lower())
    subs = []
    for uc in use_cases:
        if uc in SUB_CATEGORIES:
            for sub_name, pattern in SUB_CATEGORIES[uc].items():
                if re.search(pattern, lower):
                    subs.append(f"{uc}: {sub_name}")
    return subs


# ── Known supplement brands (longest match first) ────────────────────────────
KNOWN_BRANDS = {
    # Major supplement brands
    "nature made": "Nature Made", "nature's bounty": "Nature's Bounty",
    "nature's way": "Nature's Way", "nature's truth": "Nature's Truth",
    "nordic naturals": "Nordic Naturals", "now foods": "NOW Foods",
    "garden of life": "Garden of Life", "vitafusion": "Vitafusion",
    "olly": "OLLY", "natrol": "Natrol", "zzzquil": "ZzzQuil",
    "pure zzzs": "ZzzQuil", "airborne": "Airborne", "emergen-c": "Emergen-C",
    "emergen": "Emergen-C", "align": "Align", "culturelle": "Culturelle",
    "metamucil": "Metamucil", "benefiber": "Benefiber", "flintstones": "Flintstones",
    "centrum": "Centrum", "one a day": "One A Day",
    "smarty pants": "SmartyPants", "smartypants": "SmartyPants",
    "mary ruth": "MaryRuth", "mary ruth's": "MaryRuth", "maryruth": "MaryRuth",
    "maryruth's": "MaryRuth",
    "zahler": "Zahler", "carlyle": "Carlyle", "spring valley": "Spring Valley",
    "solgar": "Solgar", "kirkland": "Kirkland Signature",
    "kirkland signature": "Kirkland Signature",
    "amazon elements": "Amazon Elements", "amazon basics": "Amazon Basics",
    "365 by whole foods": "365 Whole Foods", "365 whole foods": "365 Whole Foods",
    "goli": "Goli", "goli nutrition": "Goli",
    "ritual": "Ritual", "hum": "HUM Nutrition", "hum nutrition": "HUM Nutrition",
    "persona": "Persona", "care/of": "Care/of", "nurish": "Nurish",
    "neuriva": "Neuriva", "prevagen": "Prevagen",
    "schiff": "Schiff", "move free": "Move Free",
    "osteo bi-flex": "Osteo Bi-Flex", "osteo bi": "Osteo Bi-Flex",
    "mega food": "MegaFood", "megafood": "MegaFood",
    "new chapter": "New Chapter", "rainbow light": "Rainbow Light",
    "country life": "Country Life", "bluebonnet": "Bluebonnet",
    "swanson": "Swanson", "doctor's best": "Doctor's Best",
    "life extension": "Life Extension", "jarrow": "Jarrow Formulas",
    "jarrow formulas": "Jarrow Formulas", "enzymedica": "Enzymedica",
    "youtheory": "Youtheory", "vital proteins": "Vital Proteins",
    "sports research": "Sports Research", "nutrafol": "Nutrafol",
    "black girl vitamins": "Black Girl Vitamins",
    "yum-v": "YUM-V's", "yum v": "YUM-V's",
    "lifeable": "Lifeable", "vitamatic": "Vitamatic",
    "focusfuel": "FocusFuel", "sakoon": "Sakoon",
    "lunakai": "Lunakai", "nutrachamps": "NutraChamps",
    "havasu": "Havasu Nutrition", "havasu nutrition": "Havasu Nutrition",
    "zhou": "Zhou Nutrition", "zhou nutrition": "Zhou Nutrition",
    "flo": "FLO", "flo vitamins": "FLO",
    "pink stork": "Pink Stork", "needed": "Needed",
    "perelel": "Perelel", "actif": "Actif",
    "force factor": "Force Factor", "nugenix": "Nugenix",
    "ancestral supplements": "Ancestral Supplements",
    "moon juice": "Moon Juice",
    "dr. formulated": "Garden of Life",
    "21st century": "21st Century",
    # Smaller / DTC brands found in missing titles
    "softbear": "Softbear", "kindnature": "Kindnature", "riev": "Riev",
    "o positiv": "O Positiv", "the genius brand": "The Genius Brand",
    "genius brand": "The Genius Brand",
    "proper,": "Proper", "proper ": "Proper",
    "re:root": "RE:ROOT", "nixit": "Nixit", "berkley": "Berkley Jensen",
    "berkley jensen": "Berkley Jensen",
    "nature's rhythm": "Nature's Rhythm",
    "horbäach": "Horbaach", "horbaach": "Horbaach", "horbách": "Horbaach",
    "the feel great vitamin": "Feel Great Vitamin Co",
    "feel great vitamin": "Feel Great Vitamin Co",
    "vital grow": "Vital Grow", "vitalgrow": "Vital Grow",
    "totaria": "Totaria", "reset+": "Reset+",
    "new elements": "New Elements",
    "natural vitality": "Natural Vitality",
    "nature's way sambucus": "Nature's Way", "nature's way alive": "Nature's Way",
    "nature's bounty optimal": "Nature's Bounty",
    "nature's bounty high": "Nature's Bounty",
    "nature's bounty melatonin": "Nature's Bounty",
    "nature made zero": "Nature Made", "nature made vitamin": "Nature Made",
    "nature made wellblends": "Nature Made",
    "nordic naturals zero": "Nordic Naturals",
    "nordic naturals ultimate": "Nordic Naturals",
    "nordic naturals vitamin": "Nordic Naturals",
    "vitafusion prenatal": "Vitafusion", "vitafusion extra": "Vitafusion",
    "vitafusion sugar": "Vitafusion", "vitafusion adult": "Vitafusion",
    "vitafusion max": "Vitafusion", "vitafusion magnesium": "Vitafusion",
    "vitafusion power": "Vitafusion",
    "olly ultra": "OLLY", "olly goodbye": "OLLY", "olly sleep": "OLLY",
    "olly happy": "OLLY", "olly women": "OLLY", "olly men": "OLLY",
    "new chapter": "New Chapter",
    "emergen-c": "Emergen-C", "emergen c": "Emergen-C",
    "dr. tobias": "Dr. Tobias", "dr tobias": "Dr. Tobias",
    "spring valley": "Spring Valley",
    "thorne": "THORNE", "smarty pants": "SmartyPants",
    "viva naturals": "Viva Naturals", "vivanaturals": "Viva Naturals",
    "nested naturals": "Nested Naturals",
    "amazing grass": "Amazing Grass",
    "zand": "Zand", "belive": "BeLive", "belive ": "BeLive",
    "flat tummy": "Flat Tummy", "skinnyfit": "SkinnyFit",
    "pure encapsulations": "Pure Encapsulations",
    "mary ruth organics": "MaryRuth", "maryruths": "MaryRuth",
    "365 by whole foods market": "365 Whole Foods",
    "equate": "Equate", "member's mark": "Member's Mark",
    "costco": "Kirkland Signature",
    "cvs health": "CVS Health", "cvs ": "CVS Health",
    "up & up": "Up & Up", "up&up": "Up & Up",
    "sundown": "Sundown Naturals", "sundown naturals": "Sundown Naturals",
    "nutra champs": "NutraChamps",
    "luxe keto": "Luxe Keto", "trim tummy": "Trim Tummy",
    "sambucol": "Sambucol",
    "naturesplus": "NaturesPlus", "nature's plus": "NaturesPlus",
    "doctor's best": "Doctor's Best",
    "sports research": "Sports Research",
    "trace minerals": "Trace Minerals",
    "ancestral supplements": "Ancestral Supplements",
    "bulk supplements": "BulkSupplements", "bulksupplements": "BulkSupplements",
    "novaferrum": "NovaFerrum",
    "the smurfs": "The Smurfs", "zarbee's": "Zarbee's", "zarbee": "Zarbee's",
    "natural factors": "Natural Factors",
    "neviss": "NEVISS", "enxos": "ENXOS", "bvivloo": "BVIVLOO",
    "venture pal": "Venture Pal", "jiankytz": "JIANKYTZ",
    # More small brands from PDP scraper results
    "helios": "Helios", "wellpath": "WellPath", "rae wellness": "Rae Wellness",
    "rae ": "Rae Wellness", "lemme": "Lemme",
    "llama naturals": "Llama Naturals", "hims": "Hims",
    "snap supplements": "Snap Supplements",
    "nature's craft": "Nature's Craft", "humann": "HumanN",
    "para today": "Para Today",
    "bubs naturals": "Bubs Naturals", "mielle": "Mielle",
    "frunutta": "Frunutta", "primal harvest": "Primal Harvest",
    "bioptimizers": "BiOptimizers", "cymbiotika": "Cymbiotika",
    "seeking health": "Seeking Health", "mav nutrition": "MAV Nutrition",
    "terra origin": "Terra Origin", "beam": "Beam",
    "sakara": "Sakara", "solaray": "Solaray",
    "host defense": "Host Defense", "real mushrooms": "Real Mushrooms",
    "genius mushrooms": "Genius Mushrooms",
    "double wood": "Double Wood", "double wood supplements": "Double Wood",
    "nootropics depot": "Nootropics Depot",
}
# Sort by longest key first for greedy matching
_BRAND_KEYS = sorted(KNOWN_BRANDS.keys(), key=len, reverse=True)

# Words that are NOT brands — filter these out
BAD_BRANDS = {
    "Magnesium", "Melatonin", "Calcium", "Ashwagandha", "Collagen", "Biotin",
    "Turmeric", "Elderberry", "Probiotic", "Prebiotic", "Omega", "Vitamin",
    "Mushroom", "Saffron", "Shilajit", "Creatine", "Berberine", "Fiber",
    "Gummies", "Gummy", "Sugar", "Vegan", "Organic", "Natural", "Premium",
    "Extra", "Advanced", "Ultra", "Super", "Maximum", "Hemp", "Lions",
    "Sea", "Hair", "Skin", "Kids", "Adult", "Women", "Men", "New",
    "Apple", "Keto", "GLP", "Proprietary", "Feminine", "Cortisol",
    "Liposomal", "Nootropic",
}


def fig_to_html(fig):
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": True})


# Additional use case patterns applied at load time
EXTRA_EFFECTS = {
    "Intimacy": r"intimacy|libido|sex|arousal|aphrodisiac|maca.*libido|horny\s*goat",
}

# Expanded form factor classification — applied at load time to eliminate "Other"
FORM_RULES = [
    # Order matters: check most specific first
    ("Gummy",   r"gumm|chewy|chewable|gummi|jelly|gummie"),
    ("Capsule",  r"capsule|softgel|gel\s*cap|veggie\s*cap|vcap|caps\b|pill"),
    ("Tablet",   r"tablet|caplet|chew\b|chews\b"),
    ("Powder",   r"powder|mix\b|scoop|drink\s*mix|sachet"),
    ("Liquid",   r"liquid|tincture|drops?\b|syrup|shot\b|elixir|spray|oil\b|serum"),
    ("Lozenge",  r"lozenge|melt\b|dissolv|sublingual|strip"),
    # Fallback heuristics for products that don't state their form
    ("Capsule",  r"\d+\s*(?:count|ct)\b.*(?:supplement|vitamin|support|formula|complex)"),
    ("Tablet",   r"\d+\s*(?:count|ct)\b.*(?:multivitamin|multi[\s-]?vitamin|one\s*a\s*day)"),
    ("Capsule",  r"(?:supplement|formula|complex|support)\s.*\d+\s*(?:count|ct)\b"),
    ("Capsule",  r"\b(?:mg|mcg)\b.*\d+\s*(?:count|ct|pack)\b"),
]


def _merge_pill_forms(ff):
    if ff in ("Capsule", "Tablet", "Capsule/Tablet"):
        return "Capsule/Tablet"
    return ff


def reclassify_form_factor(title, current_ff):
    """Reclassify form factor using expanded rules. Returns current_ff if no better match."""
    if current_ff != "Other":
        return current_ff
    lower = title.lower()
    for name, pattern in FORM_RULES:
        if re.search(pattern, lower):
            return name
    return "Capsule/Tablet"  # default for pill-format supplements that don't specify

# Rename use cases from scraper to match our preferred labels
USE_CASE_RENAMES = {
    "Joint & Bone": "Pain Relief",
}


def parse_sold(text):
    """Parse Amazon 'bought past month' badge into integer."""
    if not text:
        return 0
    text = text.lower().replace(",", "").replace("+", "")
    m = re.search(r"([\d.]+)\s*k", text)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else 0


def _normalize(text):
    """Normalize curly quotes/apostrophes to straight for matching."""
    return text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')


def extract_brand(title):
    """Extract brand from title using KNOWN_BRANDS dict + regex fallback."""
    lower = _normalize(title.lower())
    # 1. Check known brands (longest match first)
    for key in _BRAND_KEYS:
        if key in lower:
            return KNOWN_BRANDS[key]
    # 2. Regex fallback: first capitalized phrase before dash/pipe
    m = re.match(r"^([A-Z][A-Za-z'&\.\s]{1,30}?)[\s]*[-–—|]", title)
    if m:
        brand = m.group(1).strip()
        if brand.split()[0] not in BAD_BRANDS and len(brand) > 1:
            return brand
    # 3. Fallback: first 1-3 capitalized words
    m = re.match(r"^([A-Z][A-Za-z'&\.]+(?:\s[A-Z][A-Za-z'&\.]+){0,2})\s", title)
    if m:
        brand = m.group(1).strip()
        words = brand.split()
        if words and words[0] not in BAD_BRANDS:
            return brand
    return ""


def load_products():
    """Load supplement products from CSV."""
    products = []
    try:
        with open(INPUT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                price = 0
                try:
                    price = float(row.get("price", 0) or 0)
                except (ValueError, TypeError):
                    pass
                if price < 1:
                    continue

                sold = parse_sold(row.get("boughtPastMonth", ""))
                rating = None
                try:
                    rating = float(row.get("rating", "") or 0)
                except (ValueError, TypeError):
                    pass
                review_count = 0
                try:
                    review_count = int(row.get("reviewCount", "") or 0)
                except (ValueError, TypeError):
                    pass

                use_cases = [USE_CASE_RENAMES.get(uc.strip(), uc.strip())
                             for uc in row.get("useCase", "").split("|") if uc.strip()]

                # Apply extra use case patterns not in original scraper
                title_lower = row.get("title", "").lower()
                for effect_name, pattern in EXTRA_EFFECTS.items():
                    if effect_name not in use_cases and re.search(pattern, title_lower):
                        use_cases.append(effect_name)

                # Re-extract brand: prefer KNOWN_BRANDS match, fall back to CSV brand
                title = row.get("title", "")
                csv_brand = row.get("brand", "").strip()
                brand = extract_brand(title)  # KNOWN_BRANDS + regex
                if not brand:
                    # Use CSV brand from PDP scraper (Amazon's official brand field)
                    brand = csv_brand
                # Only label as unknown if truly no brand anywhere
                if not brand:
                    brand = "Unknown Brand"

                asin = row.get("asin", "")
                url = row.get("url", "").strip()
                if not url and asin:
                    url = f"https://www.amazon.com/dp/{asin}"

                products.append({
                    "asin": asin,
                    "title": title,
                    "brand": brand,
                    "formFactor": _merge_pill_forms(reclassify_form_factor(title, row.get("formFactor", "Other"))),
                    "useCases": use_cases,
                    "subCategories": classify_subcategories(title, use_cases),
                    "price": price,
                    "soldPastMonth": sold,
                    "rating": rating,
                    "reviewCount": review_count,
                    "revenue": price * sold if sold else 0,
                    "url": url,
                })
    except FileNotFoundError:
        print(f"ERROR: {INPUT_CSV} not found. Run scrape_amazon_supplements.py first.")
        return []

    branded = sum(1 for p in products if p["brand"])
    print(f"  Brand extraction: {branded}/{len(products)} ({100*branded/len(products):.0f}%)")
    return products


def load_brightfield_demand():
    """Load Brightfield consumer demand data for hemp THC gummies.
    Source: Brightfield Group Hemp-Derived THC report — gummies desired effects."""
    return {
        "Relax": 63.7,
        "Sleep": 49.4,
        "Emotional relief": 48.6,
        "Physical relief": 42.0,
        "General well-being": 34.5,
        "Fun / celebrations": 25.8,
        "Focus": 25.6,
        "Stimulate appetite": 23.3,
        "Energy": 21.0,
        "Spark creativity": 18.8,
        "Enhance intimacy": 14.1,
        "Athletic / gym": 6.8,
    }


# Map Brightfield THC gummy effects to our supplement use cases
BF_TO_SUPPLEMENT = {
    "Relax": "Stress & Calm",
    "Sleep": "Sleep",
    "Emotional relief": "Mood",
    "Physical relief": "Pain Relief",
    "General well-being": "General Wellness",
    "Focus": "Focus & Brain",
    "Energy": "Energy",
    "Enhance intimacy": "Intimacy",
}


def chart_usecase_brand_marimekko(products):
    """Marimekko: use case columns (width=revenue), brand stacks."""
    uc_brand_rev = defaultdict(lambda: defaultdict(float))
    uc_totals = defaultdict(float)
    for p in products:
        if p["revenue"] <= 0:
            continue
        brand = p["brand"] or "Unknown"
        for uc in p["useCases"]:
            uc_brand_rev[uc][brand] += p["revenue"]
            uc_totals[uc] += p["revenue"]

    if not uc_totals:
        fig = go.Figure()
        fig.add_annotation(text="No revenue data available", showarrow=False, font=dict(size=14))
        fig.update_layout(height=400, template="plotly_white")
        return fig

    sorted_uc = sorted(uc_totals.keys(), key=lambda k: -uc_totals[k])[:13]
    total_rev = sum(uc_totals[uc] for uc in sorted_uc)
    MAX_BRANDS = 10

    uc_stacks = {}
    uc_other_detail = {}  # breakdown of "Other Brands" per use case
    all_brand_names = set()
    for uc in sorted_uc:
        sorted_brands = sorted(uc_brand_rev[uc].items(), key=lambda x: -x[1])
        top = sorted_brands[:MAX_BRANDS]
        rest_brands = sorted_brands[MAX_BRANDS:]
        rest = sum(r for _, r in rest_brands)
        stack = list(top)
        if rest > 0:
            stack.append(("Other Brands", rest))
            # Store top 10 of the "other" brands for hover detail
            uc_other_detail[uc] = rest_brands[:10]
        uc_stacks[uc] = stack
        for b, _ in stack:
            all_brand_names.add(b)

    palette = ["#2563EB", "#DC2626", "#059669", "#D97706", "#7C3AED",
               "#DB2777", "#0891B2", "#65A30D", "#EA580C", "#4F46E5",
               "#BE185D", "#0D9488", "#B45309", "#7C2D12", "#6D28D9",
               "#991B1B", "#115E59", "#78350F", "#312E81", "#831843"]
    brand_color = {}
    ci = 0
    for b in sorted(all_brand_names):
        if b == "Other Brands":
            brand_color[b] = "#E5E7EB"
        else:
            brand_color[b] = palette[ci % len(palette)]
            ci += 1

    MIN_WIDTH_PCT = 5
    raw_widths = {uc: math.sqrt(uc_totals[uc]) for uc in sorted_uc}
    raw_sum = sum(raw_widths.values())
    widths = [(uc, max(100 * raw_widths[uc] / raw_sum, MIN_WIDTH_PCT)) for uc in sorted_uc]
    w_sum = sum(w for _, w in widths)
    widths = [(uc, w * 100 / w_sum) for uc, w in widths]
    gap = 0.8
    total_gap = gap * (len(widths) - 1)
    scale = (100 - total_gap) / 100
    widths = [(uc, w * scale) for uc, w in widths]

    x_starts = []
    x = 0
    for uc, w in widths:
        x_starts.append(x)
        x += w + gap

    fig = go.Figure()
    for col_idx, (uc, col_width) in enumerate(widths):
        x_center = x_starts[col_idx] + col_width / 2
        uc_rev = uc_totals[uc]
        stack = uc_stacks[uc]
        y_bottom = 0
        for brand, rev in reversed(stack):
            pct = 100 * rev / uc_rev
            if brand == "Other Brands" and uc in uc_other_detail:
                detail_lines = [f"  {b}: ${r:,.0f}/mo ({100*r/uc_rev:.1f}%)" for b, r in uc_other_detail[uc]]
                hover = f"<b>Other Brands</b> — {uc}<br>${rev:,.0f}/mo ({pct:.1f}%)<br>{'<br>'.join(detail_lines)}"
                if len(uc_other_detail[uc]) < len([x for x in sorted(uc_brand_rev[uc].items(), key=lambda x: -x[1])[MAX_BRANDS:]]):
                    hover += f"<br>  + {len(sorted(uc_brand_rev[uc].items(), key=lambda x: -x[1])[MAX_BRANDS:]) - len(uc_other_detail[uc])} more"
            else:
                hover = f"<b>{brand}</b><br>{uc}<br>${rev:,.0f}/mo ({pct:.1f}%)"
            fig.add_trace(go.Bar(
                x=[x_center], y=[pct], width=col_width, base=y_bottom,
                marker_color=brand_color.get(brand, "#999"),
                marker_line=dict(color="white", width=1.5),
                showlegend=False,
                hovertext=hover,
                hoverinfo="text",
            ))
            if pct >= 8 and col_width >= 4:
                label = f"<b>{brand}</b><br>${rev/1000:,.0f}K" if pct >= 18 else brand[:12]
                fig.add_annotation(
                    x=x_center, y=y_bottom + pct / 2, text=label, showarrow=False,
                    font=dict(size=9, color="white" if brand != "Other Brands" else "#555"),
                )
            y_bottom += pct

    fig.update_layout(
        xaxis=dict(
            tickmode="array",
            tickvals=[x_starts[i] + widths[i][1] / 2 for i in range(len(widths))],
            ticktext=[f"<b>{uc}</b><br>${uc_totals[uc]/1e6:.1f}M/mo ({100*uc_totals[uc]/total_rev:.0f}%)" for uc, _ in widths],
            range=[-1, 101], showgrid=False,
        ),
        yaxis=dict(title="Brand Share (%)", range=[0, 105], ticksuffix="%"),
        barmode="overlay",
        title=f"Supplement Market Map — Use Case × Brand Share<br>"
              f"<sup>Amazon measured revenue. Column width ∝ category size. Products can appear in multiple categories.</sup>",
        height=700, template="plotly_white", margin=dict(t=80, b=120),
    )
    return fig


def chart_usecase_formfactor_marimekko(products, mode="count"):
    """Marimekko: use case columns, form factor stacks. mode='count' or 'revenue'."""
    uc_ff_val = defaultdict(lambda: defaultdict(float))
    uc_totals = defaultdict(float)
    for p in products:
        ff = p["formFactor"]
        val = p["revenue"] if mode == "revenue" else 1
        if mode == "revenue" and val <= 0:
            continue
        for uc in p["useCases"]:
            uc_ff_val[uc][ff] += val
            uc_totals[uc] += val
    uc_ff_count = uc_ff_val  # alias for compatibility below

    if not uc_totals:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False, font=dict(size=14))
        fig.update_layout(height=400, template="plotly_white")
        return fig

    sorted_uc = sorted(uc_totals.keys(), key=lambda k: -uc_totals[k])[:13]
    total_prods = sum(uc_totals[uc] for uc in sorted_uc)

    # Fixed form factor colors
    ff_colors = {
        "Gummy": "#2563EB",
        "Capsule": "#DC2626",
        "Tablet": "#D97706",
        "Powder": "#059669",
        "Liquid": "#7C3AED",
        "Lozenge": "#DB2777",
        "Other": "#9CA3AF",
    }

    # Get all form factors present
    all_ffs = set()
    for uc in sorted_uc:
        all_ffs.update(uc_ff_count[uc].keys())
    # Sort: Gummy first, then by total count
    ff_order = ["Gummy"] + [ff for ff in sorted(all_ffs - {"Gummy"}, key=lambda f: -sum(uc_ff_count[uc].get(f, 0) for uc in sorted_uc))]

    MIN_WIDTH_PCT = 5
    raw_widths = {uc: math.sqrt(uc_totals[uc]) for uc in sorted_uc}
    raw_sum = sum(raw_widths.values())
    widths = [(uc, max(100 * raw_widths[uc] / raw_sum, MIN_WIDTH_PCT)) for uc in sorted_uc]
    w_sum = sum(w for _, w in widths)
    widths = [(uc, w * 100 / w_sum) for uc, w in widths]
    gap = 0.8
    total_gap = gap * (len(widths) - 1)
    scale = (100 - total_gap) / 100
    widths = [(uc, w * scale) for uc, w in widths]

    x_starts = []
    x = 0
    for uc, w in widths:
        x_starts.append(x)
        x += w + gap

    fig = go.Figure()
    # Add legend entries first
    for ff in ff_order:
        if ff in all_ffs:
            fig.add_trace(go.Bar(
                x=[None], y=[None], name=ff,
                marker_color=ff_colors.get(ff, "#999"),
                showlegend=True,
            ))

    for col_idx, (uc, col_width) in enumerate(widths):
        x_center = x_starts[col_idx] + col_width / 2
        uc_total = uc_totals[uc]
        y_bottom = 0
        for ff in reversed(ff_order):
            count = uc_ff_count[uc].get(ff, 0)
            if count == 0:
                continue
            pct = 100 * count / uc_total
            fig.add_trace(go.Bar(
                x=[x_center], y=[pct], width=col_width, base=y_bottom,
                marker_color=ff_colors.get(ff, "#999"),
                marker_line=dict(color="white", width=1.5),
                showlegend=False,
                hovertext=f"<b>{ff}</b><br>{uc}<br>{count:,} products ({pct:.0f}%)",
                hoverinfo="text",
            ))
            if pct >= 10 and col_width >= 4:
                fig.add_annotation(
                    x=x_center, y=y_bottom + pct / 2,
                    text=f"<b>{ff}</b><br>{pct:.0f}%",
                    showarrow=False,
                    font=dict(size=9, color="white" if ff != "Other" else "#555"),
                )
            y_bottom += pct

    # Gummy penetration annotations at top of each column
    for col_idx, (uc, col_width) in enumerate(widths):
        x_center = x_starts[col_idx] + col_width / 2
        gummy_pct = 100 * uc_ff_count[uc].get("Gummy", 0) / uc_totals[uc]
        fig.add_annotation(
            x=x_center, y=103, text=f"<b>{gummy_pct:.0f}%</b>",
            showarrow=False,
            font=dict(size=10, color="#2563EB" if gummy_pct >= 50 else "#DC2626"),
        )

    fig.update_layout(
        xaxis=dict(
            tickmode="array",
            tickvals=[x_starts[i] + widths[i][1] / 2 for i in range(len(widths))],
            ticktext=[f"<b>{uc}</b><br>{'${:,.0f}'.format(uc_totals[uc]) if mode == 'revenue' else '{:,}'.format(int(uc_totals[uc]))}" for uc, _ in widths],
            range=[-1, 101], showgrid=False,
        ),
        yaxis=dict(title="Form Factor Mix (%)", range=[0, 110], ticksuffix="%"),
        barmode="overlay",
        title=(f"Form Factor by Use Case — {'Revenue ($)' if mode == 'revenue' else 'Product Count'}<br>"
              f"<sup>Blue % at top = gummy share. Red = gummies underrepresented. {'Revenue-weighted.' if mode == 'revenue' else f'{len(products):,} products.'}</sup>"),
        height=700, template="plotly_white", margin=dict(t=80, b=120),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _compute_review_cagr_by_usecase(keepa_rows, products):
    """Compute 2-year review count CAGR per use case from Keepa data."""
    if not keepa_rows:
        return {}

    # Get earliest and latest review counts per ASIN
    asin_range = {}
    for r in keepa_rows:
        asin = r["asin"]
        rc = r.get("reviewCount")
        date = r.get("date", "")
        if not rc or not date:
            continue
        try:
            rc = int(rc)
        except ValueError:
            continue
        if asin not in asin_range:
            asin_range[asin] = {"earliest_date": date, "earliest_rc": rc, "latest_date": date, "latest_rc": rc}
        if date < asin_range[asin]["earliest_date"]:
            asin_range[asin]["earliest_date"] = date
            asin_range[asin]["earliest_rc"] = rc
        if date > asin_range[asin]["latest_date"]:
            asin_range[asin]["latest_date"] = date
            asin_range[asin]["latest_rc"] = rc

    # Map ASIN → use cases
    asin_ucs = {}
    for p in products:
        asin_ucs[p["asin"]] = p["useCases"]

    # Aggregate per use case: sum of review growth
    uc_early = defaultdict(int)
    uc_late = defaultdict(int)
    for asin, rng in asin_range.items():
        # Only use ASINs with at least 1 year of data
        if rng["latest_date"][:4] <= rng["earliest_date"][:4]:
            continue
        for uc in asin_ucs.get(asin, []):
            uc_early[uc] += rng["earliest_rc"]
            uc_late[uc] += rng["latest_rc"]

    # Compute CAGR
    result = {}
    for uc in uc_late:
        early = max(uc_early.get(uc, 1), 1)
        late = uc_late.get(uc, 0)
        if late > early:
            # Approximate years from data range
            years = 2.0  # rough approximation for Keepa data span
            cagr = (late / early) ** (1 / years) - 1
            result[uc] = cagr
    return result


def build_summary_table(products, keepa_rows=None):
    """Build HTML summary table of use cases ranked by estimated revenue."""
    review_cagr = _compute_review_cagr_by_usecase(keepa_rows or [], products)
    uc_stats = defaultdict(lambda: {"products": 0, "revenue": 0, "brands": set(),
                                     "gummy_count": 0, "top_brand": defaultdict(float),
                                     "sub_cats": defaultdict(lambda: {"count": 0, "revenue": 0})})
    for p in products:
        brand = p["brand"] or "Unknown"
        for uc in p["useCases"]:
            s = uc_stats[uc]
            s["products"] += 1
            s["revenue"] += p["revenue"]
            s["brands"].add(brand)
            if p["formFactor"] == "Gummy":
                s["gummy_count"] += 1
            s["top_brand"][brand] += p["revenue"]
        # Track sub-categories
        for sc in p.get("subCategories", []):
            # sc is like "Women's Health: Prenatal"
            parts = sc.split(": ", 1)
            if len(parts) == 2:
                parent_uc, sub_name = parts
                uc_stats[parent_uc]["sub_cats"][sub_name]["count"] += 1
                uc_stats[parent_uc]["sub_cats"][sub_name]["revenue"] += p["revenue"]

    rows = []
    for uc, s in sorted(uc_stats.items(), key=lambda x: -x[1]["revenue"]):
        top_brand = max(s["top_brand"].items(), key=lambda x: x[1])[0] if s["top_brand"] else "—"
        gummy_pct = 100 * s["gummy_count"] / s["products"] if s["products"] else 0
        mood_product = MOOD_PRODUCTS.get(uc, "")
        mood_plays = "Yes" if mood_product else "No"
        mood_color = "#dcfce7" if mood_plays == "Yes" else "#fef2f2"
        mood_text_color = "#166534" if mood_plays == "Yes" else "#991b1b"

        # THC relevance
        thc_rel = THC_RELEVANCE.get(uc, 0)
        if thc_rel >= 0.7:
            rel_color, rel_bg = "#166534", "#dcfce7"
        elif thc_rel >= 0.4:
            rel_color, rel_bg = "#854d0e", "#fef9c3"
        else:
            rel_color, rel_bg = "#991b1b", "#fef2f2"

        # Sub-category breakdown
        sub_cats = s["sub_cats"]
        if sub_cats:
            sorted_subs = sorted(sub_cats.items(), key=lambda x: -x[1]["revenue"])[:5]
            sub_html_parts = []
            for sub_name, sub_data in sorted_subs:
                sub_rev = f"${sub_data['revenue']/1e6:.1f}M" if sub_data["revenue"] >= 1e6 else f"${sub_data['revenue']/1e3:,.0f}K"
                sub_html_parts.append(f"<b>{sub_name}</b>: {sub_data['count']:,} ({sub_rev})")
            sub_html = " · ".join(sub_html_parts)
        else:
            sub_html = "<span style='color:#9ca3af;'>—</span>"

        rev_str = f"${s['revenue']/1e6:.1f}M" if s["revenue"] >= 1e6 else f"${s['revenue']/1e3:,.0f}K"

        # Review CAGR
        cagr = review_cagr.get(uc)
        if cagr is not None:
            cagr_str = f"{cagr:+.0%}"
            cagr_color = "#166534" if cagr > 0.3 else "#854d0e" if cagr > 0.1 else "#991b1b"
        else:
            cagr_str = "—"
            cagr_color = "#9ca3af"

        rows.append(f"""
        <tr>
          <td style="padding:8px 12px; font-weight:600;">{uc}</td>
          <td style="padding:8px 12px; text-align:right;">{s['products']:,}</td>
          <td style="padding:8px 12px; text-align:right; font-weight:600;">{rev_str}/mo</td>
          <td style="padding:8px 12px; text-align:right; color:{cagr_color}; font-weight:600;">{cagr_str}</td>
          <td style="padding:8px 12px; text-align:center;">
            <span style="background:{rel_bg}; color:{rel_color}; padding:2px 8px; border-radius:3px; font-size:11px; font-weight:600;">{thc_rel:.0%}</span>
          </td>
          <td style="padding:8px 12px;">{top_brand}</td>
          <td style="padding:8px 12px; text-align:right;">{gummy_pct:.0f}%</td>
          <td style="padding:8px 12px; text-align:center;">
            <span style="background:{mood_color}; color:{mood_text_color}; padding:2px 8px; border-radius:3px; font-size:11px; font-weight:600;">{mood_plays}</span>
          </td>
          <td style="padding:8px 12px; font-size:11px; color:#6b7280;">{mood_product or '—'}</td>
        </tr>
        <tr>
          <td colspan="9" style="padding:2px 12px 10px 24px; font-size:11px; color:#6b7280; border-bottom:1px solid #e2e8f0;">{sub_html}</td>
        </tr>""")

    # Total row
    total_products = len(products)
    total_revenue = sum(p["revenue"] for p in products)
    total_brands = len(set(p["brand"] for p in products if p["brand"] and p["brand"] != "Unknown Brand"))
    total_gummy = sum(1 for p in products if p["formFactor"] == "Gummy")
    total_gummy_pct = 100 * total_gummy / total_products if total_products else 0
    total_rev_str = f"${total_revenue/1e6:.1f}M" if total_revenue >= 1e6 else f"${total_revenue/1e3:,.0f}K"
    mood_count = sum(1 for uc in uc_stats if uc in MOOD_CATEGORIES)

    rows.append(f"""
        <tr style="border-top:3px solid #1e293b; font-weight:700; background:#f8fafc;">
          <td style="padding:10px 12px;">Total (deduplicated)</td>
          <td style="padding:10px 12px; text-align:right;">{total_products:,}</td>
          <td style="padding:10px 12px; text-align:right;">{total_rev_str}/mo</td>
          <td style="padding:10px 12px;"></td>
          <td style="padding:10px 12px;"></td>
          <td style="padding:10px 12px;">—</td>
          <td style="padding:10px 12px; text-align:right;">{total_gummy_pct:.0f}%</td>
          <td style="padding:10px 12px; text-align:center;">{mood_count}/{len(uc_stats)}</td>
          <td style="padding:10px 12px; font-size:11px; color:#6b7280;">—</td>
        </tr>""")

    return "\n".join(rows)


def load_keepa_data():
    """Load Keepa historical data if available."""
    keepa_csv = "keepa_supplements.csv"
    try:
        rows = []
        with open(keepa_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)
        print(f"  Keepa data: {len(rows):,} data points")
        return rows
    except FileNotFoundError:
        print(f"  Keepa data: not available (run scrape_keepa_supplements.py)")
        return []


def _no_keepa_fig(title):
    fig = go.Figure()
    fig.add_annotation(text="Keepa data not available yet — run scrape_keepa_supplements.py",
                       showarrow=False, font=dict(size=14))
    fig.update_layout(height=400, template="plotly_white", title=title)
    return fig


def _aggregate_reviews_by_month(keepa_rows, products, group_fn):
    """Aggregate review counts into monthly time series grouped by group_fn(product).
    group_fn takes a product dict and returns a list of group keys (e.g., brand, use cases, form factor)."""
    # Build ASIN → product lookup
    asin_product = {}
    for p in products:
        asin_product[p["asin"]] = p

    # Get review time series per ASIN, sampled monthly
    from collections import defaultdict
    # For each ASIN, get (date, reviewCount) pairs
    asin_series = defaultdict(list)
    for r in keepa_rows:
        rc = r.get("reviewCount")
        if rc and r.get("date"):
            try:
                asin_series[r["asin"]].append((r["date"][:7], int(rc)))  # YYYY-MM
            except ValueError:
                pass

    # For each ASIN, keep only the max review count per month
    asin_monthly = {}
    for asin, pts in asin_series.items():
        monthly = {}
        for month, rc in pts:
            monthly[month] = max(monthly.get(month, 0), rc)
        asin_monthly[asin] = monthly

    # Aggregate by group
    group_monthly = defaultdict(lambda: defaultdict(int))
    for asin, monthly in asin_monthly.items():
        prod = asin_product.get(asin)
        if not prod:
            continue
        groups = group_fn(prod)
        for g in groups:
            for month, rc in monthly.items():
                group_monthly[g][month] = max(group_monthly[g][month], group_monthly[g].get(month, 0))
                group_monthly[g][month] += rc

    # Re-aggregate properly: sum across ASINs per group per month
    group_monthly2 = defaultdict(lambda: defaultdict(int))
    for asin, monthly in asin_monthly.items():
        prod = asin_product.get(asin)
        if not prod:
            continue
        groups = group_fn(prod)
        for g in groups:
            for month, rc in monthly.items():
                group_monthly2[g][month] += rc

    return dict(group_monthly2)


def _make_time_series_chart(group_monthly, title, subtitle, yaxis_title, height=500, max_traces=12):
    """Build a line chart from {group: {month: value}} data."""
    palette = ["#2563EB", "#DC2626", "#059669", "#D97706", "#7C3AED",
               "#DB2777", "#0891B2", "#65A30D", "#EA580C", "#4F46E5",
               "#BE185D", "#0D9488"]

    # Sort groups by latest value
    def latest_val(monthly):
        if not monthly:
            return 0
        return monthly.get(max(monthly.keys()), 0)

    sorted_groups = sorted(group_monthly.items(), key=lambda x: -latest_val(x[1]))[:max_traces]

    fig = go.Figure()
    for i, (group, monthly) in enumerate(sorted_groups):
        months = sorted(monthly.keys())
        values = [monthly[m] for m in months]
        fig.add_trace(go.Scatter(
            x=months, y=values, name=group,
            mode="lines",
            line=dict(color=palette[i % len(palette)], width=2),
            hovertext=[f"<b>{group}</b><br>{m}: {v:,}" for m, v in zip(months, values)],
            hoverinfo="text",
        ))

    fig.update_layout(
        title=f"{title}<br><sup>{subtitle}</sup>",
        xaxis_title="Month", yaxis_title=yaxis_title,
        yaxis=dict(tickformat=","),
        height=height, template="plotly_white",
        legend=dict(font=dict(size=10)),
    )
    return fig


def chart_reviews_by_brand(keepa_rows, products):
    """Time series: cumulative review count over time by brand."""
    if not keepa_rows:
        return _no_keepa_fig("Review Count by Brand Over Time")

    group_monthly = _aggregate_reviews_by_month(
        keepa_rows, products,
        lambda p: [p["brand"]] if p["brand"] != "Unknown Brand" else []
    )
    return _make_time_series_chart(
        group_monthly,
        "Review Count by Brand Over Time",
        "Cumulative reviews per month for top brands. Source: Keepa.",
        "Total Reviews", height=550, max_traces=12,
    )


def chart_reviews_by_usecase(keepa_rows, products):
    """Time series: cumulative review count over time by use case."""
    if not keepa_rows:
        return _no_keepa_fig("Review Count by Use Case Over Time")

    group_monthly = _aggregate_reviews_by_month(
        keepa_rows, products,
        lambda p: p["useCases"] if p["useCases"] else ["General Wellness"]
    )
    return _make_time_series_chart(
        group_monthly,
        "Review Count by Use Case Over Time",
        "Cumulative reviews per month. Products in multiple categories counted in each. Source: Keepa.",
        "Total Reviews", height=500, max_traces=13,
    )


def chart_reviews_by_formfactor(keepa_rows, products):
    """Time series: cumulative review count over time by form factor."""
    if not keepa_rows:
        return _no_keepa_fig("Review Count by Form Factor Over Time")

    group_monthly = _aggregate_reviews_by_month(
        keepa_rows, products,
        lambda p: [p["formFactor"]]
    )
    return _make_time_series_chart(
        group_monthly,
        "Review Count by Form Factor Over Time",
        "Cumulative reviews per month. Steeper = faster growing format. Source: Keepa.",
        "Total Reviews", height=450, max_traces=6,
    )


def chart_brightfield_overlay(products, bf_demand):
    """Bar chart: supplement revenue vs implied THC demand in $ (same axis)."""
    # Compute supplement revenue per use case
    uc_rev = defaultdict(float)
    for p in products:
        if p["revenue"] <= 0:
            continue
        for uc in p["useCases"]:
            uc_rev[uc] += p["revenue"]

    # Total market revenue for scaling THC demand % into $
    total_market_rev = sum(p["revenue"] for p in products if p["revenue"] > 0)

    # Build aligned data
    categories = []
    supp_revs = []
    thc_implied_revs = []
    bf_pcts = []
    for bf_name, supp_name in BF_TO_SUPPLEMENT.items():
        if supp_name in uc_rev:
            categories.append(supp_name)
            supp_rev = uc_rev[supp_name] / 1e6
            supp_revs.append(supp_rev)
            pct = bf_demand.get(bf_name, 0)
            bf_pcts.append(pct)
            # Implied demand: if X% of THC consumers want this, scale to total market $
            thc_implied = (pct / 100) * total_market_rev / 1e6
            thc_implied_revs.append(thc_implied)

    fig = go.Figure()

    # Supplement revenue bars
    fig.add_trace(go.Bar(
        x=categories, y=supp_revs, name="Current Supplement Revenue",
        marker_color="#2563EB", opacity=0.8,
        text=[f"${r:.0f}M" for r in supp_revs], textposition="outside",
        hovertext=[f"<b>{c}</b><br>Supplement revenue: ${r:.1f}M/mo" for c, r in zip(categories, supp_revs)],
        hoverinfo="text",
    ))

    # Implied THC demand in $
    fig.add_trace(go.Bar(
        x=categories, y=thc_implied_revs, name=f"Implied THC Demand ({bf_pcts[0]:.0f}% of ${total_market_rev/1e6:.0f}M)",
        marker_color="#DC2626", opacity=0.4,
        text=[f"${r:.0f}M ({p:.0f}%)" for r, p in zip(thc_implied_revs, bf_pcts)],
        textposition="outside", textfont=dict(color="#DC2626", size=10),
        hovertext=[f"<b>{c}</b><br>THC demand: {p:.0f}% of consumers → ${r:.1f}M implied"
                   for c, p, r in zip(categories, bf_pcts, thc_implied_revs)],
        hoverinfo="text",
    ))

    fig.update_layout(
        title="Gummy THC Demand vs Supplement Market Size (same $ scale)<br>"
              f"<sup>Red = if {bf_pcts[0]:.0f}% of THC consumers want 'Stress & Calm', that implies ${thc_implied_revs[0]:.0f}M of the ${total_market_rev/1e6:.0f}M total market. Blue = actual supplement revenue.</sup>",
        yaxis=dict(title="Monthly Revenue ($M)", tickprefix="$", ticksuffix="M"),
        height=550, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        barmode="group",
    )
    return fig


def build_html(products):
    """Generate the full dashboard HTML."""
    total = len(products)
    if total == 0:
        print("No products loaded!")
        return

    brands = set(p["brand"] for p in products if p["brand"])
    with_revenue = sum(1 for p in products if p["revenue"] > 0)
    total_revenue = sum(p["revenue"] for p in products)
    avg_price = sum(p["price"] for p in products) / total if total else 0

    # Use case counts
    uc_counts = defaultdict(int)
    for p in products:
        for uc in p["useCases"]:
            uc_counts[uc] += 1

    # Form factor counts
    ff_counts = defaultdict(int)
    for p in products:
        ff_counts[p["formFactor"]] += 1
    gummy_count = ff_counts.get("Gummy", 0)
    gummy_pct = gummy_count / total if total else 0

    # Generate charts
    print("Generating charts...")
    chart_brand = fig_to_html(chart_usecase_brand_marimekko(products))
    chart_ff_count = fig_to_html(chart_usecase_formfactor_marimekko(products, mode="count"))
    chart_ff_rev = fig_to_html(chart_usecase_formfactor_marimekko(products, mode="revenue"))

    # Brightfield THC demand overlay chart
    bf_demand = load_brightfield_demand()
    chart_bf = fig_to_html(chart_brightfield_overlay(products, bf_demand))

    # Keepa review count charts
    keepa_rows = load_keepa_data()
    keepa_asins = len(set(r["asin"] for r in keepa_rows)) if keepa_rows else 0
    chart_rev_brand = fig_to_html(chart_reviews_by_brand(keepa_rows, products))
    chart_rev_uc = fig_to_html(chart_reviews_by_usecase(keepa_rows, products))
    chart_rev_ff = fig_to_html(chart_reviews_by_formfactor(keepa_rows, products))

    # Summary table rows
    table_rows = build_summary_table(products, keepa_rows)

    # Product explorer data (JSON for JS table)
    import json
    product_rows = []
    for p in sorted(products, key=lambda x: -x["revenue"]):
        product_rows.append({
            "t": p["title"][:100],
            "b": p["brand"] or "—",
            "ff": p["formFactor"],
            "uc": ", ".join(p["useCases"][:3]),
            "p": f"${p['price']:.2f}",
            "s": f"{p['soldPastMonth']:,}" if p["soldPastMonth"] else "—",
            "r": f"${p['revenue']:,.0f}" if p["revenue"] else "—",
            "rt": f"{p['rating']:.1f}" if p["rating"] else "—",
            "rc": f"{p['reviewCount']:,}" if p["reviewCount"] else "—",
            "u": p["url"],
        })
    products_json = json.dumps(product_rows)

    fmt_rev = lambda v: f"${v/1e6:.1f}M" if v >= 1e6 else f"${v/1e3:,.0f}K"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Supplement Market Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f4f8; color:#1a202c; }}
  .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2563EB 100%); color:white; padding:32px 40px; }}
  .header h1 {{ font-size:28px; margin-bottom:6px; }}
  .header p {{ font-size:14px; opacity:0.85; }}
  .stats {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:16px; }}
  .stat {{ background:rgba(255,255,255,0.15); border-radius:8px; padding:12px 20px; min-width:100px; }}
  .stat .num {{ font-size:22px; font-weight:800; }}
  .stat .label {{ font-size:11px; opacity:0.8; margin-top:2px; }}
  .grid {{ max-width:1280px; margin:0 auto; padding:24px; display:grid; grid-template-columns:repeat(2,1fr); gap:16px; }}
  .card {{ background:white; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,0.1); overflow:hidden; }}
  .full-width {{ grid-column: 1 / -1; }}
  .section-header {{ grid-column:1/-1; padding:20px 0 4px; }}
  .section-header h2 {{ font-size:20px; color:#1e293b; }}
  .section-header p {{ font-size:13px; color:#718096; }}
  table {{ border-collapse:collapse; width:100%; }}
  th {{ text-align:left; padding:8px 12px; font-size:12px; font-weight:700; color:#6b7280;
       text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid #e2e8f0; }}
  td {{ border-bottom:1px solid #f0f0f0; font-size:13px; }}
  #explorer-table th {{ cursor:pointer; user-select:none; }}
  #explorer-table th:hover {{ color:#2563EB; }}
  #dt-search {{ padding:8px 12px; border:1px solid #e2e8f0; border-radius:6px; width:300px; font-size:13px; }}
  #dt-filter {{ padding:8px 12px; border:1px solid #e2e8f0; border-radius:6px; font-size:13px; }}
  .product-link {{ color:#2563EB; text-decoration:none; }}
  .product-link:hover {{ text-decoration:underline; }}
  @media (max-width:800px) {{ .grid {{ grid-template-columns:1fr; }} #dt-search {{ width:100%; }} }}
</style>
</head>
<body>

<div class="header">
  <h1>Supplement Market Dashboard</h1>
  <p>Amazon supplement landscape by use case and form factor — identifying whitespace for functional gummy expansion</p>
  <div class="stats">
    <div class="stat"><div class="num">{total:,}</div><div class="label">Products</div></div>
    <div class="stat"><div class="num">{gummy_count:,}</div><div class="label">Gummies ({gummy_pct:.0%})</div></div>
    <div class="stat"><div class="num">{len(brands):,}</div><div class="label">Brands</div></div>
    <div class="stat"><div class="num">{len(uc_counts)}</div><div class="label">Use Cases</div></div>
    <div class="stat"><div class="num">${avg_price:.2f}</div><div class="label">Avg Price</div></div>
    <div class="stat"><div class="num">{fmt_rev(total_revenue)}/mo</div><div class="label">Tracked Revenue</div></div>
  </div>
</div>

<div class="grid">

  <div class="card full-width" style="padding:20px 24px; background:linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border-left:4px solid #2563EB;">
    <div style="font-size:14px; color:#1e3a5f; line-height:1.7; margin-bottom:12px;">
      <b>US Supplement Gummy Market:</b> <b>$3.5B&ndash;$4.2B</b> (2024, Grand View Research / GM Insights).
      Growing at <b>9.5&ndash;11.6% CAGR</b>, projected to reach <b>$6.7B&ndash;$10.8B</b> by 2030&ndash;2032.
      Our Amazon scrape captures <b>{total:,} products</b> across <b>{len(brands):,} brands</b>
      with <b>{fmt_rev(total_revenue)}/mo</b> in tracked revenue &mdash;
      approximately <b>{100*total_revenue*12/4.2e9:.0f}%</b> of the total market (Amazon is ~30&ndash;35% of US supplement sales).
    </div>
    <table style="font-size:12px; border-collapse:collapse; width:100%;">
      <tr style="border-bottom:1px solid #bfdbfe;">
        <td style="padding:4px 8px; font-weight:600; color:#1e3a5f;">Source</td>
        <td style="padding:4px 8px; font-weight:600; color:#1e3a5f; text-align:right;">US Market (2024)</td>
        <td style="padding:4px 8px; font-weight:600; color:#1e3a5f; text-align:right;">Projection</td>
        <td style="padding:4px 8px; font-weight:600; color:#1e3a5f; text-align:right;">CAGR</td>
      </tr>
      <tr style="border-bottom:1px solid #dbeafe;">
        <td style="padding:4px 8px;"><a href="https://www.gminsights.com/industry-analysis/gummy-supplements-market" target="_blank" style="color:#2563EB;">GM Insights</a></td>
        <td style="padding:4px 8px; text-align:right; font-weight:600;">$4.2B US (2024)</td>
        <td style="padding:4px 8px; text-align:right;">$27.1B global by 2034</td>
        <td style="padding:4px 8px; text-align:right;">9.5% (global)</td>
      </tr>
      <tr style="border-bottom:1px solid #dbeafe;">
        <td style="padding:4px 8px;"><a href="https://www.grandviewresearch.com/industry-analysis/us-gummy-market-report" target="_blank" style="color:#2563EB;">Grand View Research</a></td>
        <td style="padding:4px 8px; text-align:right; font-weight:600;">$3.5B US (2024)</td>
        <td style="padding:4px 8px; text-align:right;">$6.7B US by 2030</td>
        <td style="padding:4px 8px; text-align:right;">11.6% (US)</td>
      </tr>
      <tr style="border-bottom:1px solid #dbeafe;">
        <td style="padding:4px 8px;"><a href="https://www.fortunebusinessinsights.com/gummy-supplements-market-109478" target="_blank" style="color:#2563EB;">Fortune Business Insights</a></td>
        <td style="padding:4px 8px; text-align:right; font-weight:600;">$5.2B NA (2025)</td>
        <td style="padding:4px 8px; text-align:right;">$10.8B US by 2032</td>
        <td style="padding:4px 8px; text-align:right;">13.2% (global)</td>
      </tr>
    </table>
    <div style="font-size:10px; color:#6b7280; margin-top:6px;">Vitamins segment = ~36% ($1.5B). CBD/CBN gummies growing fastest at 17% CAGR. Adults = 79% of market. Offline channels = 80% of sales.</div>
    <details style="margin-top:8px;"><summary style="cursor:pointer; font-size:11px; color:#2563EB; font-weight:600;">Sampling methodology</summary>
    <div style="margin-top:6px; font-size:11px; color:#4b5563; line-height:1.6;">
      <b>Source:</b> Amazon.com product search results (Playwright headless browser, Apr 2026).<br>
      <b>Queries:</b> 75 search terms across 13 use case categories. Mix of gummy-specific and generic supplement queries
      (e.g., "melatonin gummies" + "melatonin supplement" + "melatonin capsules"). Gummy-specific queries outnumber
      generic ones ~2:1, which biases product count toward gummies. Revenue-weighted views partially correct this since
      non-gummy products often have higher price points.<br>
      <b>Sort:</b> Best sellers first (<code>exact-aware-popularity-rank</code>), up to 20 pages per query.<br>
      <b>Dedup:</b> By ASIN &mdash; each product counted once regardless of how many queries found it.<br>
      <b>Filters:</b> Price &gt; $1, must contain supplement/vitamin/form-factor keyword in title. Excludes pet, apparel, books, cosmetics.<br>
      <b>Revenue:</b> Estimated from Amazon "bought in past month" badges &times; listed price. Only ~60% of products display this badge.<br>
      <b>Limitations:</b> Amazon search returns ~50 results per page, capped at ~20 pages. Total addressable catalog is 100K+ supplements &mdash;
      our {total:,} products represent the top-ranked ~10% by popularity. Long-tail niche products are underrepresented.
      Revenue estimates are approximate (Amazon rounds "bought" counts and not all products display them).
    </div></details>
  </div>

  <div class="section-header">
    <h2>Use Case × Brand Share</h2>
    <p>Who dominates each supplement category? Based on estimated monthly revenue (price × units sold past month). Column width proportional to category revenue.</p>
  </div>
  <div class="card full-width">{chart_brand}</div>

  <div class="section-header">
    <h2>Form Factor Penetration</h2>
    <p>Where are gummies dominant vs underrepresented? Blue % = gummy share of category.</p>
  </div>
  <div class="card full-width" style="padding:20px;">
    <details>
      <summary style="cursor:pointer; font-weight:700; font-size:13px; color:#2d3748;">Category Definitions — how products are classified (click to expand)</summary>
      <div style="margin-top:12px; display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:8px; font-size:12px;">
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Sleep</b><br><span style="color:#718096;">melatonin, insomnia, nighttime, rest, zzz</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Stress &amp; Calm</b><br><span style="color:#718096;">ashwagandha, l-theanine, GABA, cortisol, anxiety</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Energy</b><br><span style="color:#718096;">caffeine, B12, vitamin B, guarana, green tea, maca</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Focus &amp; Brain</b><br><span style="color:#718096;">nootropic, memory, concentration, lion's mane, cognitive</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Immunity</b><br><span style="color:#718096;">elderberry, vitamin C, zinc, echinacea</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Digestion</b><br><span style="color:#718096;">probiotic, prebiotic, gut, fiber, apple cider vinegar</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Beauty</b><br><span style="color:#718096;">biotin, collagen, hair, skin, nails, keratin</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>General Wellness</b><br><span style="color:#718096;">multivitamin, vitamin D, omega, fish oil, daily</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Pain Relief</b><br><span style="color:#718096;">joint, bone, turmeric, curcumin, glucosamine, calcium, vitamin D3</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Women's Health</b><br><span style="color:#718096;">PMS, menstrual, prenatal, fertility, menopause</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Men's Health</b><br><span style="color:#718096;">testosterone, prostate, virility, libido</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Weight &amp; Metabolism</b><br><span style="color:#718096;">appetite, keto, fat burn, garcinia, thermogenic</span></div>
        <div style="padding:8px; background:#f8fafc; border-radius:6px;"><b>Mood</b><br><span style="color:#718096;">serotonin, SAM-e, 5-HTP, St. John's wort</span></div>
      </div>
      <div style="margin-top:8px; font-size:11px; color:#9ca3af;">Products are classified by keyword matching in titles. A product can belong to multiple categories.</div>
    </details>
  </div>
  <div class="card full-width">{chart_ff_count}</div>
  <div class="card full-width">{chart_ff_rev}</div>

  <div class="section-header">
    <h2>Gummy THC Consumer Demand vs Supplement Market Size</h2>
    <p>Brightfield survey: what gummy THC consumers want. Bars: supplement category size on Amazon. Overlap = competitive opportunity.</p>
  </div>
  <div class="card full-width">{chart_bf}</div>

  <div class="section-header">
    <h2>Review Count Analysis</h2>
    <p>Lifetime review counts from Keepa — a proxy for cumulative consumer demand and product maturity.
    Based on the current top {keepa_asins} best-selling products by volume (sorted by Amazon "bought in past month"). Data grows as more products are indexed.</p>
  </div>
  <div class="card full-width">{chart_rev_brand}</div>
  <div class="card">{chart_rev_uc}</div>
  <div class="card">{chart_rev_ff}</div>

  <div class="section-header">
    <h2>Use Case Summary</h2>
    <p>All categories ranked by estimated Amazon revenue. "Mood Plays" = Mood has or plans a product in this category.</p>
  </div>
  <div class="card full-width" style="padding:20px;">
    <table>
      <thead>
        <tr>
          <th>Use Case</th>
          <th style="text-align:right;">Products</th>
          <th style="text-align:right;">Est. Rev</th>
          <th style="text-align:right;">Review CAGR</th>
          <th style="text-align:center;">THC Fit</th>
          <th>Top Brand</th>
          <th style="text-align:right;">Gummy %</th>
          <th style="text-align:center;">Mood Plays</th>
          <th>Mood Product</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>

  <div class="section-header">
    <h2>Product Explorer</h2>
    <p>All {total:,} products with links. Search and filter to validate data.</p>
  </div>
  <div class="card full-width" style="padding:20px;">
    <div style="display:flex; flex-wrap:wrap; gap:12px; margin-bottom:16px; align-items:end;">
      <div>
        <label style="font-size:12px; font-weight:600; color:#718096; display:block; margin-bottom:4px;">Search</label>
        <input type="text" id="dt-search" placeholder="Product name, brand...">
      </div>
      <div>
        <label style="font-size:12px; font-weight:600; color:#718096; display:block; margin-bottom:4px;">Use Case</label>
        <select id="dt-filter">
          <option value="">All</option>
          {"".join(f'<option value="{uc}">{uc}</option>' for uc in sorted(uc_counts.keys()))}
        </select>
      </div>
      <div>
        <label style="font-size:12px; font-weight:600; color:#718096; display:block; margin-bottom:4px;">Form Factor</label>
        <select id="dt-ff-filter">
          <option value="">All</option>
          {"".join(f'<option value="{ff}">{ff}</option>' for ff in sorted(ff_counts.keys()))}
        </select>
      </div>
      <div style="font-size:12px; color:#718096;" id="dt-count">Showing {total:,} products</div>
    </div>
    <div style="overflow-x:auto; max-height:600px; overflow-y:auto;">
      <table id="explorer-table">
        <thead><tr style="position:sticky; top:0; background:white;">
          <th style="min-width:250px;">Product</th>
          <th>Brand</th>
          <th>Form</th>
          <th>Use Case</th>
          <th style="text-align:right;">Price</th>
          <th style="text-align:right;">Sold/mo</th>
          <th style="text-align:right;">Rev/mo</th>
          <th style="text-align:right;">Rating</th>
          <th style="text-align:right;">Reviews</th>
        </tr></thead>
        <tbody id="explorer-body"></tbody>
      </table>
    </div>
  </div>

</div>

<script>
const ALL_PRODUCTS = {products_json};
const tbody = document.getElementById('explorer-body');
const searchEl = document.getElementById('dt-search');
const filterEl = document.getElementById('dt-filter');
const ffFilterEl = document.getElementById('dt-ff-filter');
const countEl = document.getElementById('dt-count');

function renderTable() {{
  const q = searchEl.value.toLowerCase();
  const uc = filterEl.value;
  const ff = ffFilterEl.value;
  const filtered = ALL_PRODUCTS.filter(p => {{
    if (q && !p.t.toLowerCase().includes(q) && !p.b.toLowerCase().includes(q)) return false;
    if (uc && !p.uc.includes(uc)) return false;
    if (ff && p.ff !== ff) return false;
    return true;
  }});
  const show = filtered.slice(0, 500);
  tbody.innerHTML = show.map(p => `<tr>
    <td style="padding:6px 8px; font-size:12px;">${{p.u ? `<a href="${{p.u}}" target="_blank" class="product-link">${{p.t}}</a>` : p.t}}</td>
    <td style="padding:6px 8px; font-size:12px; white-space:nowrap;">${{p.b}}</td>
    <td style="padding:6px 8px; font-size:11px;">${{p.ff}}</td>
    <td style="padding:6px 8px; font-size:11px;">${{p.uc}}</td>
    <td style="padding:6px 8px; text-align:right; font-size:12px;">${{p.p}}</td>
    <td style="padding:6px 8px; text-align:right; font-size:12px;">${{p.s}}</td>
    <td style="padding:6px 8px; text-align:right; font-size:12px; font-weight:600;">${{p.r}}</td>
    <td style="padding:6px 8px; text-align:right; font-size:12px;">${{p.rt}}</td>
    <td style="padding:6px 8px; text-align:right; font-size:12px;">${{p.rc}}</td>
  </tr>`).join('');
  countEl.textContent = `Showing ${{show.length}} of ${{filtered.length.toLocaleString()}} products`;
}}
searchEl.addEventListener('input', renderTable);
filterEl.addEventListener('change', renderTable);
ffFilterEl.addEventListener('change', renderTable);
renderTable();
</script>

</body>
</html>"""

    Path(OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"\n✅ Dashboard saved → {OUTPUT_HTML}")
    print(f"   Open in browser: open {OUTPUT_HTML}")


def main():
    print("Loading data...")
    products = load_products()
    if not products:
        return
    print(f"  {len(products):,} products loaded")

    build_html(products)


if __name__ == "__main__":
    main()
