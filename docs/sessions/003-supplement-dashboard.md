# Session 003: Supplement Market Dashboard

**Date:** 2026-04-06
**Status:** Complete — continued in [004-supplement-dashboard-v2.md](004-supplement-dashboard-v2.md)

## Summary

Built a standalone supplement market dashboard from an Amazon scrape of 6,146 products across 13 use cases and 7 form factors. This directly answers CEO Fabian's question about which supplement categories are real markets and where Mood has whitespace opportunities.

## Context

From the Caroline/David sync (2026-04-06): Fabian wants to know:
1. What supplement use cases exist and how big are they?
2. Are we missing large/growing categories?
3. Are current Mood categories (PMS, testosterone) real markets or tiny niches?
4. Where are gummies underrepresented vs other form factors?

## What Was Built

### scrape_amazon_supplements.py (new file)
- Cloned from scrape_amazon_plp.py, modified for supplements
- 41 search queries covering 13 use case categories
- Captures all form factors (gummies, capsules, tablets, powders, liquids)
- Classifies products by use case (regex-based, multi-label) and form factor
- Output: amazon_supplements.csv — 6,146 products, 2,935 brands

### build_supplement_dashboard.py (new file)
- Standalone dashboard generator (no changes to THC dashboard)
- Two Marimekko charts:
  - **Use Case × Brand Share** — who dominates each category, column width ∝ revenue
  - **Use Case × Form Factor** — gummy penetration per category, blue % annotation
- Summary table with Products, Est. Rev, Brands, Top Brand, Gummy %, Mood Plays

### Key Findings (from 6,075 loaded products)

| Use Case | Est. Rev/mo | Mood Plays | Opportunity |
|---|---|---|---|
| General Wellness | $86M | No | Huge category, generic |
| Women's Health | $85M | Yes (PMS) | Validated — real market |
| Immunity | $59M | No | Large whitespace |
| Beauty | $51M | No | Large whitespace |
| Energy | $49M | Yes | Validated |
| Digestion | $47M | No | Large whitespace |
| Joint & Bone | $39M | No | Whitespace |
| Focus & Brain | $33M | Yes | Validated |
| Stress & Calm | $31M | Yes | Validated |
| Sleep | $23M | Yes | Validated |
| Weight & Metabolism | $12M | No | Medium |
| Mood | $6M | Yes | Small but real |
| **Men's Health** | **$4.5M** | **No** | **Tiny — testosterone is niche** |

## Also in This Session

### THC Dashboard Improvements (earlier in conversation)
- Tightened hemp TAM from $4.5B–$7.1B to $4.5B–$5.8B (capped BDSA estimate)
- Added executive summary "bottom line" card
- Made regulatory alert collapsible
- Reduced charts from 15 → 9
- Moved Brightfield company chart adjacent to TAM
- Fixed chart title: "market share" → "brand awareness"
- Added data quality caveat to supplement comparison
- Restructured "Market Growth & Sources" → "TAM Sources & How They Add Up"

## Files Created
- `scrape_amazon_supplements.py` — Amazon supplement scraper
- `amazon_supplements.csv` — 6,146 scraped products
- `build_supplement_dashboard.py` — Dashboard generator
- `supplement_dashboard.html` — Generated dashboard

## Context for Future Sessions
- Dashboard uses Amazon-only data (per David's preference — single marketplace, no dedup issues)
- Brand extraction needs improvement — many products show "Unknown" as top brand
- Could add: product explorer table, Brightfield THC demand overlay
- The "Mood Plays" column in summary table is hardcoded to current product lines — update if Mood launches new categories
- Caroline wants two specific Marimekko cuts: use case × brand share AND use case × form factor — both are built
