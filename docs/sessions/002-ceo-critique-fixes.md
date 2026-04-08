# Session 002: CEO-Level Critique & Dashboard Fixes

**Date:** 2026-04-06
**Status:** Complete (8 fixes implemented across 2 rounds of critique)

## Summary

CEO asked team to review the market sizing analysis for the Tuesday Leads meeting. Applied a critical eye to the dashboard and identified 9 issues. Implemented 5 priority fixes, then did a second round of critique and implemented 3 more.

## What Changed

### 1. Tracked Revenue Range (was fake-precise single number)
- Added `total_tracked_low` / `total_tracked_high` to `compute_market_size()`
- "What We Measure" card now shows **$4.0M – $14.0M/mo** range instead of single $9M number
- Reflects conservative vs calibrated DTC model spread

### 2. Confidence Badges on Channel Rows
- Each channel in "What We Measure" table now has a color-coded confidence badge:
  - **Measured** (green) — Amazon with "bought" badges
  - **Estimated** (yellow) — Amazon long-tail extrapolation
  - **Modeled** (red) — DTC traffic model
  - **Rough** (red) — Dispensary estimate
- Explanatory notes below each badge in smaller gray text

### 3. Growth & Position Hero Card
- Added third hero box in TAM card: **+7.3% YoY** (Brightfield 2024→2025)
- Includes Mood market share ~1.5% (currently hardcoded from Brightfield data)

### 4. Regulatory Impact on TAM (collapsible)
- Added "Impact on TAM" expandable section inside regulatory alert
- Models two scenarios: 0.4mg rule (hemp channel → zero, TAM shrinks) vs CSRA (TAM intact)

### 5. Supplement Gummies Context
- Added "Broader Context: Supplement Gummies Compete for the Same Consumer" section
- Comparison table: Sleep ($950M), Stress ($500M-$2.2B), Focus ($530M-$710M), Energy ($1.6B-$2.5B)
- Total functional overlap: $3.6B-$6.7B
- Combined addressable market: $8B-$14B
- Sources: GM Insights, Fortune Business Insights, Grand View Research

### Other Changes
- Reordered Market Size section: Regulatory alert → TAM → What We Measure → Market Growth
- Cleaned up dead `channel_rows` variable (~30 lines removed)
- Fixed table layout (fixed column widths, wrapped badge notes) to prevent clipping in 50% card width

### Round 2 fixes (second CEO critique)

### 6. Executive Summary at top of Market Size
- 2-sentence "Bottom line" card directly answers the CEO's question
- Includes TAM, functional TAM, supplement comparison, tracked revenue, and regulatory warning in one block

### 7. Tightened Hemp TAM High Estimate
- Changed from BDSA-derived $3.9B (via $21.8B × 27% × 67%) to 2× Brightfield ($2.7B)
- BDSA's $21.8B total hemp figure would imply hemp is 4× the regulated dispensary market — flagged as suspect
- Total TAM tightened from $4.5B–$7.1B to **$4.5B–$5.8B**
- Added data quality caveat to supplement comparison (scanner-measured vs modeled)

### 8. DTC "95% accuracy" reframed
- Changed "Average calibrated accuracy: 95%" to "Average calibrated fit: 95%"
- Added caveat: "In-sample fit only — model was tuned to these 3 points. Out-of-sample accuracy unknown."

### 9. Mood share ~1.5% clarified
- Separated from growth rate line
- Now reads: "Mood = ~1.5% of total hemp THC market (Brightfield company rankings)"

### Round 3 fixes (backlog items)

### 10. Chart count reduced from 15 → 9
Removed 6 redundant/low-value charts:
- Functional vs General pie (already shown in hero stat "50%")
- Revenue by Functional Category (Amazon-only, redundant with category breakdown)
- Functional Category Market Map treemap (same data as category breakdown)
- Price Distribution by Channel (nice-to-have, not strategic)
- Top 25 Brands by Product Count (product count ≠ market importance)
- Top 20 Brands by Revenue (Amazon) (redundant with brand revenue share Marimekko)

### 11. Amazon visual weight reduced
- Amazon revenue chart subtitle changed from "Amazon only" to "Amazon only (<1% of TAM) — shown because it's our only measured channel"
- Demand & Revenue section description updated to balance Amazon + DTC

### 12. Brightfield company market share moved adjacent to TAM
- Chart pulled out of Industry Data section
- Now appears immediately after the Market Size cards (TAM, What We Measure) before the Brightfield section
- CEO sees competitive landscape right after market sizing

## Still Unfixed
- Functional share percentages (30% dispensary, 54% DTC, 88% Amazon) lack independent validation
- Growth rate (+7.3%) and Mood share (~1.5%) are hardcoded — should be pulled dynamically from Brightfield data

## Key Files Modified
- `build_dashboard.py` — market_context_html section (~lines 1835-2200)

## Context for Future Sessions
- Dashboard is ready for Tuesday Leads meeting review
- CEO + Caroline + Joe are reviewing async before Tuesday
- Caroline was asked to pull supplement market size from Statista — our supplement context section may overlap/complement her work
- Growth rate (+7.3%) and Mood share (~1.5%) are hardcoded — should be pulled dynamically from Brightfield data
