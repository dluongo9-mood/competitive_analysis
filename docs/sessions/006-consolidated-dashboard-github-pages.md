---
date: 2026-04-11
time: 15:00
tags: [dashboard, consolidation, github-pages, deployment, mushroom]
status: complete
related_sessions: [003-supplement-dashboard.md, 004-supplement-dashboard-v2.md]
---

# Consolidated Dashboard with Tab Navigation on GitHub Pages

## Goal
Combine the standalone Supplements and Mushrooms dashboards into a single tabbed HTML page and deploy it on GitHub Pages.

## Summary
Created `build_combined_dashboard.py` — a consolidation script that reads standalone dashboard HTML files, extracts body content, namespaces element IDs and JS globals to avoid collisions, wraps scripts in IIFEs, and assembles a tabbed page at `docs/index.html`. Deployed to GitHub Pages from the `docs/` folder on `main`. Updated the mushroom dashboard to the latest version from `amazon-paapi` repo and fixed legend overlap issues on Keepa review charts by switching from horizontal to vertical legends. THC Gummies tab is stubbed out in the config for future addition (it's still a WIP).

## Changes

| File | Action | Description |
|------|--------|-------------|
| `build_combined_dashboard.py` | created | Consolidation script: extracts body from HTML files, namespaces IDs/JS, wraps in IIFEs, assembles tabbed page |
| `docs/index.html` | created | Combined dashboard output (7.1 MB) with Supplements and Mushrooms tabs |
| `mushroom_dashboard.html` | modified | Updated to latest version from `/Users/davidluongo/amazon-paapi/mushroom_dashboard.html`; fixed Keepa chart legends (horizontal → vertical right-side) |

## Decisions
- **Post-hoc extraction approach**: The consolidation script reads already-generated standalone HTML files rather than modifying the Python builders to emit fragments.
  - *Why*: Zero changes to existing builders, simpler architecture, standalone dashboards remain functional independently.
- **THC Gummies excluded for now**: User indicated the THC dashboard is still a work in progress.
  - *Why*: Not ready to merge. Config has a commented-out block to add it later trivially.
- **Vertical legends on Keepa charts**: Switched from horizontal legends (overlapping chart area) to vertical legends positioned at `x=1.02` with `margin.r=280`.
  - *Why*: 15 traces made horizontal legends unreadable and they overlapped the x-axis "Date" label.
- **GitHub Pages from `docs/` on `main`**: No CI/CD needed since HTML is pre-built and committed.

## Problems & Solutions
- **Element ID collisions**: Both dashboards used `dt-search`, `dt-count`, etc.
  - *Fix*: Namespace IDs with prefixes (`supp-`, `mush-`) in HTML and all JS references.
- **JS global collisions**: Both dashboards defined `ALL_PRODUCTS`, `renderTable`, etc.
  - *Fix*: Wrap dashboard-level scripts in IIFEs; expose inline onclick functions as namespaced window globals (`window.__mush_showMore`).
- **Bare string ID arrays not caught**: Mushroom dashboard had `['dt-search','dt-source',...].forEach(id => getElementById(id))` which wasn't caught by `getElementById()` replacement.
  - *Fix*: Extended `namespace_ids()` to also replace bare string literals matching configured IDs, with double-prefix protection.
- **Plotly charts in hidden tabs render at zero width**: Charts in `display:none` tab panels get zero dimensions.
  - *Fix*: Tab switching JS calls `Plotly.Plots.resize()` on all `.js-plotly-plot` elements in the newly visible panel.
- **Inline event handlers beyond onclick**: `onkeydown="if(event.key==='Enter') askAI()"` wasn't caught by onclick-specific replacement.
  - *Fix*: Generalized to regex matching all `on*=` event handler attributes.

## Context for Future Sessions
- **To add THC Gummies tab**: Uncomment the config block in `build_combined_dashboard.py` DASHBOARDS list. Will need to populate the `ids` and `inline_onclick_fns` lists based on the THC dashboard's element IDs and onclick handlers.
- **Rebuild workflow**: Run individual dashboard builders first (e.g., `python3 build_supplement_dashboard.py`), then `python3 build_combined_dashboard.py`, then commit `docs/index.html` and push to main.
- **GitHub Pages config**: Deploys from `docs/` folder on `main` branch. Site URL: `https://dluongo9-mood.github.io/competitive_analysis/`
- **Mushroom dashboard source of truth**: Latest version lives in `/Users/davidluongo/amazon-paapi/mushroom_dashboard.html` — copy it over when updating.
- **Known limitation**: Browser automation tools can't capture screenshots of the large Plotly pages (renders blank), but DOM inspection confirms charts render correctly.
