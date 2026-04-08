"""
Zyla Site Traffic API — DTC Brand Traffic Estimates

Queries the Zyla Site Traffic API for monthly visits and engagement
across all DTC gummy brand domains.

Outputs: brand_traffic.csv

Run:
    python3 scrape_zyla_traffic.py
"""

import csv
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

OUTPUT_CSV = "brand_traffic.csv"
ZYLA_TOKEN = "13245|wz1WnbxayhaUGC82N5RySSresljAg1Hj2oQNuh2d"
ENDPOINT = "https://zylalabs.com/api/29/site+traffic+api/93/traffic+source+and+overview"

FIELDS = [
    "domain", "brand", "monthlyVisits", "bounceRate", "pagesPerVisit",
    "avgVisitDuration", "globalRank", "countryRank", "category",
    "categoryRank", "trafficSourceSearch", "trafficSourceDirect",
    "trafficSourceSocial",
    # Extended fields
    "visits_month1", "visits_month2", "visits_month3",
    "visits_month1_date", "visits_month2_date", "visits_month3_date",
    "topCountry", "topCountryShare",
    "trafficSourceReferral", "trafficSourceMail", "trafficSourcePaid",
]

DELAY = 1.5  # seconds between requests (API limit: 1 req/sec)


def get_dtc_domains():
    """Load unique brand domains from DTC CSV."""
    domains = {}
    if Path("dtc_gummies.csv").exists():
        with open("dtc_gummies.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                domain = r.get("shopDomain", "").strip()
                brand = r.get("brand", "").strip()
                if domain and brand and domain not in domains:
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


def query_zyla(domain):
    """Query Zyla Site Traffic API."""
    url = f"{ENDPOINT}?domain={domain}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {ZYLA_TOKEN}",
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 429:
            print("      Rate limited — waiting 10s...")
            time.sleep(10)
            return query_zyla(domain)  # retry once
        if e.code == 403:
            # Try with subprocess curl as fallback
            return query_zyla_curl(domain)
        raise
    except (urllib.error.URLError, TimeoutError):
        return None


def query_zyla_curl(domain):
    """Fallback: use curl subprocess to avoid urllib SSL/header issues."""
    import subprocess
    url = f"{ENDPOINT}?domain={domain}"
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "30", url,
             "-H", f"Authorization: Bearer {ZYLA_TOKEN}",
             "-H", "Accept: application/json"],
            capture_output=True, text=True, timeout=35,
        )
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass
    return None


def parse_response(data, brand, domain):
    """Extract key metrics from Zyla response."""
    if not data:
        return None

    engagements = data.get("Engagments", {})
    visits = engagements.get("Visits")
    if visits:
        try:
            visits = int(float(visits))
        except (ValueError, TypeError):
            visits = None

    bounce = engagements.get("BounceRate")
    if bounce:
        try:
            bounce = float(bounce)
        except (ValueError, TypeError):
            bounce = None

    pages = engagements.get("PagePerVisit")
    if pages:
        try:
            pages = float(pages)
        except (ValueError, TypeError):
            pages = None

    duration = engagements.get("TimeOnSite")
    if duration:
        try:
            duration = float(duration)
        except (ValueError, TypeError):
            duration = None

    # Monthly visit history
    est_visits = data.get("EstimatedMonthlyVisits", {})
    sorted_months = sorted(est_visits.items())
    v1_date, v1 = sorted_months[0] if len(sorted_months) > 0 else (None, None)
    v2_date, v2 = sorted_months[1] if len(sorted_months) > 1 else (None, None)
    v3_date, v3 = sorted_months[2] if len(sorted_months) > 2 else (None, None)

    # Rankings
    global_rank = data.get("GlobalRank", {})
    if isinstance(global_rank, dict):
        global_rank = global_rank.get("Rank")

    country_rank = data.get("CountryRank", {})
    if isinstance(country_rank, dict):
        country_rank = country_rank.get("Rank")

    cat_rank_data = data.get("CategoryRank", {})
    category = cat_rank_data.get("Category") if isinstance(cat_rank_data, dict) else None
    cat_rank = cat_rank_data.get("Rank") if isinstance(cat_rank_data, dict) else None

    # Traffic sources
    sources = data.get("TrafficSources", {})
    search = sources.get("Search")
    direct = sources.get("Direct")
    social = sources.get("Social")
    referral = sources.get("Referral") or sources.get("Referrals")
    mail = sources.get("Mail")
    paid = sources.get("Paid Search") or sources.get("Paid Referrals")

    # Top country
    top_countries = data.get("TopCountryShares", [])
    top_country = top_countries[0].get("CountryCode") if top_countries else None
    top_country_share = top_countries[0].get("Value") if top_countries else None

    return {
        "domain": domain,
        "brand": brand,
        "monthlyVisits": visits,
        "bounceRate": bounce,
        "pagesPerVisit": pages,
        "avgVisitDuration": duration,
        "globalRank": global_rank,
        "countryRank": country_rank,
        "category": category,
        "categoryRank": cat_rank,
        "trafficSourceSearch": search,
        "trafficSourceDirect": direct,
        "trafficSourceSocial": social,
        "trafficSourceReferral": referral,
        "trafficSourceMail": mail,
        "trafficSourcePaid": paid,
        "visits_month1": v1,
        "visits_month2": v2,
        "visits_month3": v3,
        "visits_month1_date": v1_date,
        "visits_month2_date": v2_date,
        "visits_month3_date": v3_date,
        "topCountry": top_country,
        "topCountryShare": top_country_share,
    }


def save_results(results):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def main():
    domains = get_dtc_domains()
    existing = load_existing()

    # Only re-query domains that don't have traffic data
    remaining = {}
    for d, b in domains.items():
        ex = existing.get(d, {})
        if not ex.get("monthlyVisits") or ex.get("monthlyVisits") in ("", "None"):
            remaining[d] = b

    print(f"Total DTC domains: {len(domains)}")
    print(f"Already have traffic: {len(domains) - len(remaining)}")
    print(f"To query: {len(remaining)}")

    if not remaining:
        print("All done!")
        return

    results = [v for v in existing.values() if v.get("monthlyVisits") and v["monthlyVisits"] not in ("", "None")]
    success = 0
    failed = 0

    for i, (domain, brand) in enumerate(remaining.items()):
        print(f"  [{i+1}/{len(remaining)}] {brand} ({domain})...", end=" ", flush=True)

        try:
            data = query_zyla(domain)
            if data:
                parsed = parse_response(data, brand, domain)
                if parsed and parsed.get("monthlyVisits"):
                    results.append(parsed)
                    print(f"{parsed['monthlyVisits']:,} visits/mo")
                    success += 1
                else:
                    # Still save the row with brand/domain
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


if __name__ == "__main__":
    main()
