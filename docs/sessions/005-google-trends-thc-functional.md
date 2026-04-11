---
date: 2026-04-11
time: "14:00"
tags: [google-trends, search-volume, thc, functional, dashboard]
status: complete
related_sessions: [004-supplement-dashboard-v2.md]
---

# Google Trends: THC × Functional Use Case Search Interest

## Goal
Add search volume monitoring to the supplement competitive analysis — specifically tracking how consumers search for THC/CBD combined with functional benefits (sleep, pain, anxiety, etc.), since Mood is a THC brand exploring the functional supplement marketplace.

## Summary
Built a Google Trends scraper and two new dashboard charts that track consumer search interest at the intersection of THC/hemp and functional use cases. The scraper pulls 5 years of weekly data for 31 keywords across 13 functional categories (e.g., "THC gummies for sleep", "CBD for pain relief") plus 5 generic THC baseline terms. Data is normalized across batches using "THC gummies" as an anchor keyword. Two Plotly charts were added to the supplement dashboard: one showing search interest by functional use case, another comparing functional THC searches vs generic THC searches over time.

## Changes

| File | Action | Description |
|------|--------|-------------|
| `scrape_google_trends.py` | created | Google Trends scraper — 31 keywords, 8 batches, cross-batch normalization, `--resume` support |
| `google_trends.csv` | created | Output data: 8,091 rows (261 weeks × 31 keywords) |
| `build_supplement_dashboard.py` | modified | Added `load_google_trends()`, `chart_trends_by_usecase()`, `chart_trends_functional_vs_baseline()`, `_no_trends_fig()` + HTML section |

## Decisions

- **THC-functional keywords, not supplement keywords**: Initially built with supplement category terms (e.g., "melatonin gummies", "ashwagandha supplement"). User clarified Mood is a THC brand — the relevant signal is consumers searching for THC + functional benefits, not generic supplement terms.
  - *Why*: The competitive question isn't "how big is the sleep supplement market" (already answered by Amazon data) — it's "are consumers looking for THC as a functional solution?"

- **"THC gummies" as anchor keyword**: Used as the normalization anchor across all batches.
  - *Why*: Google Trends limits to 5 keywords per request, so cross-batch normalization needs a common reference. "THC gummies" is the highest-volume term in our space and directly relevant as the baseline.

- **Relative interest scoring (0–100)**: Google Trends returns relative interest, not absolute search volume. A score of 100 = the peak popularity for that keyword set within the time range. Scores are proportional to total Google searches. Cross-batch normalization scales each batch so the anchor aligns, making values comparable across batches but still relative, not absolute.
  - *Why*: This is a Google Trends limitation. The data is directional — good for identifying which use cases are growing — but won't give raw search counts.

## Keyword Map

| Category | Keywords |
|---|---|
| Sleep | THC gummies for sleep, CBD for sleep |
| Stress & Calm | THC for anxiety, CBD for stress |
| Energy | THC for energy, sativa gummies energy |
| Focus & Brain | THC for focus, CBD for focus |
| Immunity | CBD for immunity, hemp gummies immunity |
| Pain Relief | THC for pain, CBD for pain relief |
| Mood | THC for mood, delta 8 for mood |
| Intimacy | THC for sex, CBD for libido |
| Women's Health | CBD for PMS, THC for menopause |
| Men's Health | CBD for testosterone, THC for libido |
| Weight & Metabolism | THC for weight loss, CBD for appetite |
| Digestion | CBD for gut health, THC for nausea |
| Beauty | CBD for skin, hemp for hair |
| **Baseline** | THC gummies, delta 8 gummies, delta 9 gummies, CBD gummies, hemp gummies |

## Context for Future Sessions
- Scraper at `scrape_google_trends.py` — rerun anytime to refresh data (`python3 scrape_google_trends.py`). Use `--resume` to skip already-completed batches.
- Keywords are easily editable in `CATEGORY_KEYWORDS` and `THC_BASELINE_KEYWORDS` dicts at the top of the scraper.
- Dashboard integration follows the same pattern as Keepa: `load_google_trends()` → chart functions → HTML section in `build_html()`. Graceful degradation if CSV is missing.
- Charts are placed between the Brightfield THC demand overlay and the Review Count Analysis section.
- `pytrends` is an unofficial Google Trends API — can break if Google changes their interface. Rate limiting (15-30s between batches, exponential backoff on 429s) is built in.
- Cross-batch normalization introduces ~5-10% variance due to Google's rounding of relative interest values.
