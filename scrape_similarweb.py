"""
SimilarWeb Traffic Scraper — DTC + Brand Discovery

Queries the free SimilarWeb data endpoint for monthly traffic estimates
across THC/CBD gummy brand domains.

Outputs: brand_traffic.csv

Run:
    python3 scrape_similarweb.py
"""

import csv
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

OUTPUT_CSV = "brand_traffic.csv"
DTC_CSV = "dtc_gummies.csv"

# DTC brands we already scrape (domain from Shopify scraper)
# Plus additional known THC/CBD gummy brands for market discovery
EXTRA_BRANDS = [
    # Brands whose Shopify API was blocked but still have web traffic
    ("3Chi", "3chi.com"),
    ("Delta Extrax", "deltaextrax.com"),
    ("Hometown Hero", "hometownherocbd.com"),
    ("Diamond CBD", "diamondcbd.com"),
    ("Exhale Wellness", "exhalewell.com"),
    ("Budpop", "budpop.com"),
    ("Binoid", "binoidcbd.com"),
    ("Elyxr", "elyxr.com"),
    ("Mr. Hemp Flower", "mrhempflower.com"),
    ("Otter Space", "otterspacecbd.com"),
    ("Batch CBD", "mybatchcbd.com"),
    ("Green Roads", "greenroads.com"),
    ("Cycling Frog", "cyclingfrog.com"),
    ("Hemp Bombs", "hempbombs.com"),
    ("Verma Farms", "vermafarms.com"),
    ("Area 52", "area52.com"),
    # Additional THC/CBD gummy brands not in DTC scraper
    ("Koi CBD", "koicbd.com"),
    ("cbdMD", "cbdmd.com"),
    ("Lazarus Naturals", "lazarusnaturals.com"),
    ("Extract Labs", "extractlabs.com"),
    ("SunMed", "sunmed.com"),
    ("R+R Medicinals", "randrmed.com"),
    ("Slumber", "slumbercbn.com"),
    ("Sky Wellness", "skywellness.com"),
    ("Penguin CBD", "penguincbd.com"),
    ("Mystic Labs", "mysticlabsd8.com"),
    ("BioBliss", "biobliss.com"),
    ("Bloom Hemp", "bloomhemp.com"),
    ("Vida Optima", "vidaoptimacbd.com"),
    ("Eden's Herbals", "edensherbals.com"),
    ("JustDelta", "justdelta.com"),
    ("Harbor City Hemp", "harborcityhemp.com"),
    ("Botany Farms", "botanyfarms.com"),
    ("Boston Hempire", "bostonhempire.com"),
    ("Canna River", "cannariver.com"),
    ("Delta Remedys", "deltaremedys.com"),
    ("Elevate", "elevateright.com"),
    ("Flying Monkey", "flyingmonkeyusa.com"),
    ("Hi On Nature", "hiondelta8.com"),
    ("Koi Naturals", "koinaturals.com"),
    ("LOT420", "lot420.co"),
    ("No Cap Hemp Co", "nocaphempco.com"),
    ("Snapdragon", "snapdragonhemp.com"),
    ("Torch", "torchenterprise.com"),
    ("Utoya", "utoya.info"),
    ("Vena CBD", "venacbd.com"),
    ("Wana", "wana.com"),
    ("CANN", "drinkcann.com"),
    ("Kiva Confections", "kivaconfections.com"),
    ("Plus Products", "plusproducts.com"),
    ("Camino", "camino.plus"),
    ("Toast", "enjoytoast.com"),
    # Wave 2 — Brightfield + discovered brands
    ("BREZ", "drinkbrez.com"),
    ("Mellow Fellow", "mellowfellow.fun"),
    ("Crescent Canna", "crescentcanna.com"),
    ("Dad Grass", "dadgrass.com"),
    ("Royal CBD", "royalcbd.com"),
    ("Summit THC", "summitthc.com"),
    ("Eighty Six", "eightysixbrand.com"),
    ("CBDfx", "cbdfx.com"),
    ("Frosty Hemp Co", "frostyhempco.com"),
    ("ElevateRight", "elevateright.com"),
    ("BioWellnessX", "biowellnessx.com"),
    ("The Hemp Doctor", "thehempdoctor.com"),
    ("The Hemp Collect", "thehempcollect.com"),
    ("Lumi Labs", "lumigummies.com"),
    ("Kush Queen", "kushqueen.shop"),
    ("WYNK", "drinkwynk.com"),
    ("25 Hour Farms", "25hourfarms.com"),
    ("Naternal", "naternal.com"),
    ("Wild Theory", "wildtheory.com"),
    ("Redeem Therapeutics", "redeemrx.com"),
    ("PlusCBD", "pluscbdoil.com"),
    ("Rare Cannabinoid Co", "rarecannabinoidco.com"),
    ("Black Tie CBD", "blacktiecbd.net"),
    ("Snoozy", "getsnoozy.com"),
    ("Cannabis Life", "cannabislife.com"),
    # Brightfield top companies
    ("Enjoy Hemp", "enjoyhemp.com"),
    ("HoneyRoot Wellness", "honeyrootwellness.com"),
    ("Space Gods", "spacegods.com"),
    ("STIIIZY Hemp", "stiiizyhemp.com"),
    ("PURLYF", "purlyf.com"),
    ("Smilyn Wellness", "smilynwellness.com"),
    ("Happi Hemp", "happihemp.com"),
    ("XITE", "xitedibles.com"),
    ("CannaAid", "cannaaidshop.com"),
    ("Hidden Hills Club", "hiddenhillsclub.com"),
    ("WNC CBD", "wnccbd.com"),
    ("Nowadays", "hellonowadays.com"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

DELAY = 5  # seconds between requests to avoid rate limiting


def get_dtc_domains():
    """Load unique domains from DTC CSV."""
    domains = {}
    if Path(DTC_CSV).exists():
        with open(DTC_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                domain = r.get("shopDomain", "").strip()
                brand = r.get("brand", "").strip()
                if domain and brand and domain not in domains:
                    # Use the actual website domain, not checkout subdomain
                    if domain.startswith("checkout."):
                        domain = domain.replace("checkout.", "")
                    domains[domain] = brand
    return domains


def load_existing():
    """Load already-scraped domains to support resume."""
    try:
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            return {r["domain"]: r for r in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


def query_similarweb(domain):
    """Query the free SimilarWeb data endpoint for a domain."""
    url = f"https://data.similarweb.com/api/v1/data?domain={domain}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # Domain not found
        raise
    except (urllib.error.URLError, TimeoutError):
        return None


def parse_response(data, brand, domain):
    """Extract key metrics from SimilarWeb response."""
    if not data:
        return None

    engagements = data.get("Engagments", {})  # Note: SimilarWeb typo in their API
    visits_list = engagements.get("Visits") if isinstance(engagements.get("Visits"), list) else []

    # Get most recent month's visits
    monthly_visits = None
    if visits_list:
        # Last entry is most recent
        last = visits_list[-1]
        monthly_visits = last.get("Value") if isinstance(last, dict) else last

    # Fallback to single value
    if not monthly_visits and isinstance(engagements.get("Visits"), (int, float)):
        monthly_visits = engagements["Visits"]

    return {
        "domain": domain,
        "brand": brand,
        "monthlyVisits": monthly_visits,
        "bounceRate": engagements.get("BounceRate"),
        "pagesPerVisit": engagements.get("PagesPerVisit"),
        "avgVisitDuration": engagements.get("TimeOnSite"),
        "globalRank": data.get("GlobalRank", {}).get("Rank") if isinstance(data.get("GlobalRank"), dict) else data.get("GlobalRank"),
        "countryRank": data.get("CountryRank", {}).get("Rank") if isinstance(data.get("CountryRank"), dict) else None,
        "category": data.get("Category"),
        "categoryRank": data.get("CategoryRank", {}).get("Rank") if isinstance(data.get("CategoryRank"), dict) else None,
        "trafficSourceSearch": data.get("TrafficSources", {}).get("Search"),
        "trafficSourceDirect": data.get("TrafficSources", {}).get("Direct"),
        "trafficSourceSocial": data.get("TrafficSources", {}).get("Social"),
    }


def main():
    # Build master domain list
    dtc_domains = get_dtc_domains()
    all_domains = dict(dtc_domains)

    # Add extra brands (skip if already in DTC list)
    for brand, domain in EXTRA_BRANDS:
        if domain not in all_domains:
            all_domains[domain] = brand

    existing = load_existing()
    remaining = {d: b for d, b in all_domains.items() if d not in existing}

    print(f"Total domains: {len(all_domains)}")
    print(f"Already scraped: {len(existing)}")
    print(f"Remaining: {len(remaining)}")

    if not remaining:
        print("All done!")
        return

    results = list(existing.values())
    success = 0
    failed = 0

    for i, (domain, brand) in enumerate(remaining.items()):
        print(f"  [{i+1}/{len(remaining)}] {brand} ({domain})...", end=" ", flush=True)

        try:
            data = query_similarweb(domain)
            if data:
                parsed = parse_response(data, brand, domain)
                if parsed and parsed.get("monthlyVisits"):
                    results.append(parsed)
                    print(f"{parsed['monthlyVisits']:,.0f} visits/mo")
                    success += 1
                else:
                    results.append({"domain": domain, "brand": brand, "monthlyVisits": None})
                    print("no traffic data")
                    failed += 1
            else:
                results.append({"domain": domain, "brand": brand, "monthlyVisits": None})
                print("not found")
                failed += 1
        except Exception as e:
            results.append({"domain": domain, "brand": brand, "monthlyVisits": None})
            print(f"error: {e}")
            failed += 1

        # Save periodically
        if (i + 1) % 10 == 0:
            save_results(results)

        time.sleep(DELAY)

    save_results(results)
    print(f"\nDone! {success} with traffic, {failed} without → {OUTPUT_CSV}")


FIELDS = [
    "domain", "brand", "monthlyVisits", "bounceRate", "pagesPerVisit",
    "avgVisitDuration", "globalRank", "countryRank", "category",
    "categoryRank", "trafficSourceSearch", "trafficSourceDirect",
    "trafficSourceSocial",
]


def save_results(results):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    main()
