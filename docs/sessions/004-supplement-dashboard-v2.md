---
date: 2026-04-07
time: "14:00"
tags: [supplement, dashboard, scraping, keepa, market-research, ceo-feedback]
status: in-progress
related_sessions: [002-ceo-critique-fixes.md, 003-supplement-dashboard.md]
---

# Supplement Dashboard v2 — CEO Feedback, Data Quality, Keepa Integration

## Goal

Iterate on the supplement market dashboard based on Fabian (CEO) and Caroline (strategy lead) feedback. Fix data trust issues, add granularity, integrate historical trend data from Keepa, and eliminate gummy bias in the scraping methodology.

## Summary

Extensive iteration on the supplement dashboard after CEO/strategy team review identified 7 systemic issues: data trust, broad categories, missing velocity data, form factor bias, misleading review metrics, and need for THC-relevance filtering. Key wins: re-scraped with generic-first query ordering (gummy share 55% → 46%), added Keepa historical data (308K+ data points), sub-categorized all use cases, added THC relevance scores, added revenue-weighted form factor view, converted Brightfield demand to same $ scale, and added review CAGR to summary table.

Dashboard hosted at: https://dluongo9-mood.github.io/supplement-market-dashboard/

## Changes

| File | Action | Description |
|------|--------|-------------|
| `build_supplement_dashboard.py` | modified | Major overhaul: sub-categories, THC relevance, review CAGR, revenue form factor view, $ demand overlay, brand hover detail, methodology note, category defs, Mood products from catalog |
| `scrape_amazon_supplements.py` | modified | Generic-first query ordering, expanded to 102 queries, best-seller sort, 20 pages/query, balanced form factors |
| `scrape_supplement_brands.py` | created | PDP brand scraper v1 — visited 906 product pages, found 202 brands |
| `scrape_supplement_brands_v2.py` | created | PDP brand scraper v2 — improved JS extraction with 6 methods, CAPTCHA detection |
| `scrape_supplement_brands_v3.py` | created | PDP brand scraper v3 — revenue-prioritized, fresh session, 10/10 hit rate on test |
| `scrape_keepa_supplements.py` | created | Keepa API scraper for top products by sold volume, batch processing with token management |
| `scrape_keepa_supplement_search.py` | created | Keepa search API approach (abandoned — token-limited) |
| `amazon_supplements.csv` | recreated | Fresh scrape: 9,081 products with generic-first ordering |
| `keepa_supplements.csv` | created | 308K+ data points from Keepa for top-selling products |
| `supplement_dashboard.html` | rebuilt | Multiple iterations, hosted on GitHub Pages |

## Decisions

- **Separate dashboard (not integrated into THC dashboard)**: Per David's preference. Keeps the THC market analysis clean and the supplement analysis focused on Fabian's product line questions.
  - *Why*: Different audiences and questions. THC dashboard is for market sizing; supplement dashboard is for product line prioritization.

- **Generic-first query ordering**: Run capsule/tablet/powder Amazon queries before gummy queries to reduce ASIN dedup bias.
  - *Why*: When gummy queries ran first, they grabbed 81% of ASINs. Generic queries second only found 5% gummies. By reversing order, final mix is 46% gummy (was 55%), much more representative.

- **Use Amazon PDP brand as fallback (not BAD_BRANDS filtered)**: Accept Amazon's official brand field even when it looks like an ingredient name ("Magnesium Glycinate Gummies").
  - *Why*: 1,242 products had CSV brands rejected by BAD_BRANDS. These are legitimate white-label products where the seller registered the ingredient as the brand. Showing them is more honest than "Unknown Brand."

- **Mood product mapping from actual catalog**: Used `/Mood/Voice AI Agents/products.csv` (the cube data model's product catalog) instead of scraping mood.com.
  - *Why*: Website showed categories that don't have actual products. Catalog confirms: Sleep, Stress & Calm, Energy, Immunity, Pain Relief, Intimacy, Men's Health, Women's Health (PMS + Menopause).
  - *Rejected*: Focus & Brain, Mood/Happy, Beauty — these were on the website but not real products.

- **"Pain Relief" instead of "Joint & Bone"**: Renamed to match Brightfield's "Physical relief (joint pain/inflammation)" at 42% consumer demand.
  - *Why*: "Joint & Bone" was too narrow. THC consumers want pain relief broadly, not just joint-specific.

- **THC relevance scoring**: Added 0-100% score per use case. Sleep/Stress/Pain ≥85%, Beauty/General Wellness <10%.
  - *Why*: Not all supplement categories map to THC opportunities. Caroline and Fabian need to filter for actionable categories.

- **Keepa batch size 10 at 3 tokens/min**: Upgraded from base plan (1 token/min) to get 3x throughput.
  - *Why*: 200 products at 1 token/min = 7 hours. At 3 tokens/min with batch 10 = ~2 hours.

## Problems & Solutions

- **Curly apostrophe mismatch**: Amazon titles use U+2019 (') but KNOWN_BRANDS dict used U+0027 ('). Products like "Nature's Way" didn't match.
  - *Fix*: Added `_normalize()` function to convert curly quotes to straight before matching.

- **Form factor "Other" at 15%**: Products like "One A Day Multivitamin" classified as "Other" because they don't say "tablet" or "capsule" in the title.
  - *Fix*: Added `FORM_RULES` with fallback heuristics (e.g., "X count supplement" → Capsule/Tablet). Merged Capsule + Tablet + Capsule/Tablet into one "Capsule/Tablet" category. Eliminated "Other" entirely.

- **Gummy bias in scraping**: 34/41 original queries included "gummies", producing 78% gummy products.
  - *Fix*: Restructured queries to run generic terms first (102 queries total, ~60% generic). Re-scraped from scratch. Final gummy share: 46%.

- **Amazon rate limiting / CAPTCHA**: After multiple scraping sessions, Amazon blocked the headless browser.
  - *Fix*: Fresh browser context + different user agent string. Confirmed working with test query before full scrape.

- **Keepa token exhaustion**: Base plan (1 token/min) was too slow for 200+ products.
  - *Fix*: David upgraded Keepa plan. Refill rate went from 1 → 3 tokens/min.

- **Revenue vs count mismatch in charts**: Marimekko showed $785M (double-counted across categories) while hero stat showed $349M (true total).
  - *Fix*: Removed inflated total from Marimekko title. Added "Products can appear in multiple categories" note. Summary table shows deduplicated total.

## CEO/Strategy Feedback (Fabian + Caroline)

Seven systemic issues raised after v1 review:

1. **Data trust**: Sample felt too small, methodology outclassed by Jungle Scout/Helium 10 → Added methodology transparency, acknowledged limitations
2. **Categories too broad**: "Women's Health" = PMS + Prenatal + Menopause → Added SUB_CATEGORIES with granular breakdown per use case
3. **No velocity/trends**: Static snapshots not actionable → Added Keepa time series charts + review CAGR column in summary table
4. **Form factor penetration lacks trends**: → Added revenue-weighted form factor view alongside count
5. **THC demand gap confounding**: Two hypotheses (zen factor vs market gap) → Converted to same $ scale for direct comparison
6. **Review count misleading**: Brand manipulation, review purges → Use satisfaction score (reviews × rating) in future; noted as limitation
7. **THC product mapping too broad**: Beauty/metabolic health aren't real THC plays → Added THC relevance score per category

Caroline-specific feedback on v2:
- Add % and monthly market size to x-axis labels ✓
- Show more brands (top 10 vs 6) to reduce "Other" ✓
- Add revenue-weighted form factor view ✓
- Make THC demand relative to market size in $ ✓
- Fix review count by form factor discrepancy ✓
- Add review CAGR to summary table ✓
- Check gummy query bias in methodology ✓ (re-scraped)

## Key Files

| File | Purpose |
|------|---------|
| `build_supplement_dashboard.py` | Dashboard generator — the main file to modify |
| `scrape_amazon_supplements.py` | Amazon product scraper — 102 queries, generic-first |
| `amazon_supplements.csv` | 9,081 scraped products |
| `keepa_supplements.csv` | Keepa historical data (growing as scraper runs) |
| `supplement_dashboard.html` | Generated dashboard HTML |
| `amazon_supplements_backup.csv` | Backup of pre-rebalance scrape (10,970 products) |

## GitHub Pages

- Repo: https://github.com/dluongo9-mood/supplement-market-dashboard
- Live: https://dluongo9-mood.github.io/supplement-market-dashboard/
- Push command: `cd /tmp/supplement-deploy && cp /Users/davidluongo/thc-gummies-market/supplement_dashboard.html index.html && git add index.html && git commit -m "message" && git push origin main`
- Git credentials: token-based auth configured in the deploy repo

## Next Steps

- [ ] Address remaining Fabian feedback: consumer satisfaction score (reviews × rating) instead of raw review count
- [ ] Add velocity arrows/annotations to Marimekko charts based on Keepa CAGR
- [ ] Strengthen methodology section with per-category sample sizes and coverage estimates
- [ ] Add THC demand gap interpretation card below Brightfield overlay
- [ ] Run PDP brand scraper on new CSV to fill missing brands
- [ ] Continue Keepa scraper for more product coverage (currently ~50 ASINs, target 200)
- [ ] Consider Jungle Scout/Helium 10 benchmark for methodology credibility

## Context for Future Sessions

- **Dashboard builder**: `build_supplement_dashboard.py` is ~1,300 lines. Key sections: KNOWN_BRANDS dict (~100 brands), SUB_CATEGORIES dict, MOOD_PRODUCTS dict (from actual product catalog), THC_RELEVANCE scores, form factor reclassification, Keepa chart functions, summary table builder.
- **Scraper**: `scrape_amazon_supplements.py` — 102 queries, generic-first ordering is critical for form factor balance. Best-seller sorted. 20 pages/query.
- **Keepa**: API key is `v52qpv55p41ia2cis7rql3jaaokmev1ils4ckklut1fgqe24qoepf0ftq1ii6qoi`, upgraded plan (3 tokens/min). Scraper at `scrape_keepa_supplements.py` prioritizes by sold volume.
- **GitHub deploy**: Push from `/tmp/supplement-deploy/` (separate git repo from project). Token auth hardcoded in remote URL.
- **Mood product catalog**: Verified from `/Users/davidluongo/Library/CloudStorage/GoogleDrive-dluongo9@gmail.com/My Drive/Mood/Voice AI Agents/products.csv`. 17 gummy products across 8 use cases.
- **Key stakeholder patterns**: Fabian (CEO, former consultant) challenges methodology and wants granular data. Caroline (strategy) wants actionable cuts and velocity metrics. Both care deeply about data trust.
