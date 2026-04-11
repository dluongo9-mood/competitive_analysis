"""
Google Trends Scraper — Supplement Use Cases + THC Terms

Pulls weekly Google Trends data for supplement category keywords and
THC-related terms over the past 5 years. Uses an anchor keyword to
normalize across batches (Google Trends limits to 5 keywords per request).

Outputs: google_trends.csv

Run:
    python3 scrape_google_trends.py [--resume]
"""

import argparse
import csv
import random
import time
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq

OUTPUT_CSV = "google_trends.csv"
TIMEFRAME = "today 5-y"
GEO = "US"
ANCHOR = "THC gummies"  # stable, high-volume THC term for cross-batch normalization

# ── Keyword map: THC + functional use case searches ──────────────────────────
# We're a THC brand exploring the functional supplement marketplace.
# These keywords capture consumer intent at the intersection of THC/hemp and
# specific functional benefits.
CATEGORY_KEYWORDS = {
    "Sleep":              ["THC gummies for sleep", "CBD for sleep"],
    "Stress & Calm":      ["THC for anxiety", "CBD for stress"],
    "Energy":             ["THC for energy", "sativa gummies energy"],
    "Focus & Brain":      ["THC for focus", "CBD for focus"],
    "Immunity":           ["CBD for immunity", "hemp gummies immunity"],
    "Pain Relief":        ["THC for pain", "CBD for pain relief"],
    "Mood":               ["THC for mood", "delta 8 for mood"],
    "Intimacy":           ["THC for sex", "CBD for libido"],
    "Women's Health":     ["CBD for PMS", "THC for menopause"],
    "Men's Health":       ["CBD for testosterone", "THC for libido"],
    "Weight & Metabolism": ["THC for weight loss", "CBD for appetite"],
    "Digestion":          ["CBD for gut health", "THC for nausea"],
    "Beauty":             ["CBD for skin", "hemp for hair"],
}

# General THC/hemp brand terms (non-functional) for baseline comparison
THC_BASELINE_KEYWORDS = [
    "THC gummies",
    "delta 8 gummies",
    "delta 9 gummies",
    "CBD gummies",
    "hemp gummies",
]

# ── Build keyword → metadata lookup ─────────────────────────────────────────
def _build_keyword_meta():
    """Return dict: keyword → {category, type}."""
    meta = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            meta[kw] = {"category": cat, "type": "functional"}
    for kw in THC_BASELINE_KEYWORDS:
        meta[kw] = {"category": "THC Baseline", "type": "baseline"}
    return meta


def build_keyword_batches():
    """Split all keywords into batches of 5 (4 target + 1 anchor).
    The anchor is included in every batch for cross-batch normalization."""
    all_kws = []
    for kws in CATEGORY_KEYWORDS.values():
        for kw in kws:
            if kw != ANCHOR:
                all_kws.append(kw)
    for kw in THC_BASELINE_KEYWORDS:
        if kw != ANCHOR:
            all_kws.append(kw)

    batches = []
    for i in range(0, len(all_kws), 4):
        batch = all_kws[i:i + 4]
        if ANCHOR not in batch:
            batch.append(ANCHOR)
        batches.append(batch)
    return batches


def fetch_trends_batch(pytrends, keywords, timeframe, geo, max_retries=3):
    """Fetch Google Trends interest_over_time for a batch of keywords.
    Returns a pandas DataFrame or None on failure."""
    for attempt in range(max_retries):
        try:
            pytrends.build_payload(keywords, timeframe=timeframe, geo=geo)
            df = pytrends.interest_over_time()
            if df.empty:
                print(f"    Empty response for {keywords}")
                return None
            return df.drop(columns=["isPartial"], errors="ignore")
        except Exception as e:
            wait = 60 * (2 ** attempt) + random.uniform(0, 10)
            print(f"    Error: {e}. Retrying in {wait:.0f}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
    print(f"    FAILED after {max_retries} retries: {keywords}")
    return None


def normalize_across_batches(batch_results):
    """Normalize all batches using the anchor keyword so values are comparable.
    Returns a single DataFrame with all keywords, scaled relative to the
    anchor's values in the first batch."""
    if not batch_results:
        return pd.DataFrame()

    # Use the first batch's anchor values as the reference
    ref_anchor = batch_results[0][ANCHOR].copy()
    # Avoid division by zero — replace 0 with 1
    ref_anchor_safe = ref_anchor.replace(0, 1)

    normalized = []
    for df in batch_results:
        if ANCHOR not in df.columns:
            normalized.append(df)
            continue
        batch_anchor = df[ANCHOR].replace(0, 1)
        scale = ref_anchor_safe / batch_anchor
        scaled = df.multiply(scale, axis=0)
        # Drop the anchor column (we only need it for scaling)
        kw_cols = [c for c in scaled.columns if c != ANCHOR]
        normalized.append(scaled[kw_cols])

    # Also include anchor from reference batch
    anchor_df = batch_results[0][[ANCHOR]]
    all_frames = [anchor_df] + normalized
    combined = pd.concat(all_frames, axis=1)
    # Cap at 100
    combined = combined.clip(upper=100)
    return combined


def save_to_csv(df, keyword_meta, output_path):
    """Save long-format CSV: date, keyword, category, type, interest."""
    rows = []
    for date_idx in df.index:
        date_str = date_idx.strftime("%Y-%m-%d")
        for kw in df.columns:
            meta = keyword_meta.get(kw, {"category": "", "type": "unknown"})
            rows.append({
                "date": date_str,
                "keyword": kw,
                "category": meta["category"],
                "type": meta["type"],
                "interest": int(round(df.loc[date_idx, kw])),
            })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "keyword", "category", "type", "interest"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows):,} rows to {output_path}")


def load_existing_keywords(output_path):
    """Load keywords already scraped (for --resume)."""
    if not Path(output_path).exists():
        return set()
    seen = set()
    with open(output_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            seen.add(r["keyword"])
    return seen


def main():
    parser = argparse.ArgumentParser(description="Scrape Google Trends for supplement keywords")
    parser.add_argument("--resume", action="store_true", help="Skip batches with already-scraped keywords")
    args = parser.parse_args()

    keyword_meta = _build_keyword_meta()
    batches = build_keyword_batches()
    print(f"Built {len(batches)} batches ({sum(len(b) for b in batches)} total keyword slots)")
    print(f"Anchor keyword: '{ANCHOR}'")
    print(f"Timeframe: {TIMEFRAME}, Geo: {GEO}\n")

    existing_kws = load_existing_keywords(OUTPUT_CSV) if args.resume else set()

    pytrends = TrendReq(hl="en-US", tz=360)
    batch_results = []

    for i, batch in enumerate(batches):
        # Check if all non-anchor keywords in this batch are already scraped
        target_kws = [kw for kw in batch if kw != ANCHOR]
        if args.resume and all(kw in existing_kws for kw in target_kws):
            print(f"Batch {i + 1}/{len(batches)}: SKIPPED (already scraped)")
            continue

        print(f"Batch {i + 1}/{len(batches)}: {target_kws}")
        df = fetch_trends_batch(pytrends, batch, TIMEFRAME, GEO)
        if df is not None:
            batch_results.append(df)
            print(f"    Got {len(df)} weekly data points")
        else:
            print(f"    No data returned")

        # Rate limit: 15-30s between requests
        if i < len(batches) - 1:
            wait = random.uniform(15, 30)
            print(f"    Waiting {wait:.0f}s...")
            time.sleep(wait)

    if not batch_results:
        print("No data collected!")
        return

    print(f"\nNormalizing {len(batch_results)} batches...")
    combined = normalize_across_batches(batch_results)
    print(f"Combined: {len(combined)} weeks x {len(combined.columns)} keywords")

    save_to_csv(combined, keyword_meta, OUTPUT_CSV)


if __name__ == "__main__":
    main()
