#!/usr/bin/env python3
"""
Generate an interactive Plotly HTML report from scraper results.
Usage: python3 report.py [path/to/deliverability.csv]
       If no path given, uses the most recent CSV in results/
"""

import csv
import glob
import os
import sys
from collections import defaultdict
from datetime import datetime

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import BRANDS


RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

BRAND_META = {b["name"]: b for b in BRANDS}

VERDICT_COLORS = {
    "yes": "#2ecc71", "likely_yes": "#82e0aa", "unclear": "#f9e79f",
    "likely_no": "#f5b041", "no": "#e74c3c", "n/a": "#d5d8dc",
}
VERDICT_NUM = {"yes": 4, "likely_yes": 3, "unclear": 2, "likely_no": 1, "no": 0, "n/a": -1}

VERDICT_EVIDENCE = {
    "yes": "Checkout confirmed shipping available",
    "likely_yes": "Policy has no restriction for this state; checkout not confirmed",
    "unclear": "Insufficient data from both methods",
    "likely_no": "Policy mentions state near restriction language",
    "no": "Checkout or policy explicitly blocks this state",
    "n/a": "Brand does not sell THCA products on their DTC website",
}

RESULT_COLORS = {
    "restricted": "#e74c3c", "restricted_on_page": "#c0392b",
    "possibly_restricted": "#f5b041", "has_restrictions_other_states": "#82e0aa",
    "no_restriction_found": "#2ecc71", "no_policy_found": "#95a5a6",
    "deliverable": "#27ae60", "no_thca_product_found": "#bdc3c7",
    "could_not_add_to_cart": "#e67e22", "could_not_reach_checkout": "#d35400",
    "could_not_enter_zip": "#f39c12", "unclear": "#f9e79f",
    "cart_empty_at_checkout": "#aab7b8", "error": "#7f8c8d",
}


def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def find_latest_csv():
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "deliverability_*.csv")))
    if not files:
        print("No CSV files found in results/")
        sys.exit(1)
    return files[-1]


def get_brand_funnel(name):
    return BRAND_META.get(name, {}).get("brightfield_funnel_pct", 0)


def get_brand_rank(name):
    return BRAND_META.get(name, {}).get("brightfield_rank", 99)


# ── Chart builders (accept a state filter) ──────────────────────────

def build_ranked_chart(unique_brands, brand_verdicts, grouped, states_to_show, funnel_pcts):
    subtitle = f"THCA Deliverability to {' & '.join(s[:2] for s in states_to_show)}"
    fig = make_subplots(
        rows=1, cols=2, column_widths=[0.45, 0.55], shared_yaxes=True,
        horizontal_spacing=0.02,
        subplot_titles=("Brightfield Brand Funnel %", subtitle),
    )
    fig.add_trace(go.Bar(
        y=unique_brands, x=funnel_pcts, orientation="h", marker_color="#9b59b6",
        text=[f"{p}%" for p in funnel_pcts], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Funnel: %{x}%<br>Rank: #%{customdata}<extra></extra>",
        customdata=[get_brand_rank(b) for b in unique_brands],
        name="Brand Funnel %", showlegend=False,
    ), row=1, col=1)

    for state in states_to_show:
        x_vals, colors, hover_data = [], [], []
        for brand in unique_brands:
            v = brand_verdicts.get(brand, {}).get(state, "unclear")
            x_vals.append(VERDICT_NUM.get(v, 2))
            colors.append(VERDICT_COLORS.get(v, "#f9e79f"))
            p = grouped.get((brand, state), {}).get("shipping_policy", {})
            c = grouped.get((brand, state), {}).get("cart_checkout", {})
            hover_data.append(
                f"<b>{brand}</b> -> {state}<br>"
                f"<b>{v.replace('_',' ').title()}</b>: {VERDICT_EVIDENCE.get(v,'')}<br>"
                f"---------<br>"
                f"Policy: {p.get('result','n/a').replace('_',' ')}<br>"
                f"Cart: {c.get('result','n/a').replace('_',' ')}"
            )
        fig.add_trace(go.Scatter(
            y=unique_brands, x=x_vals, mode="markers+text",
            marker=dict(size=22, color=colors, line=dict(width=1.5, color="#2c3e50")),
            text=[state[:2] for _ in unique_brands],
            textfont=dict(size=9, color="#2c3e50"), textposition="middle center",
            hovertemplate="%{customdata}<extra></extra>", customdata=hover_data, name=state,
        ), row=1, col=2)

    fig.update_layout(
        height=max(400, 55 * len(unique_brands) + 100),
        title=dict(text="Top Hemp Brands: Brightfield Ranking vs. THCA Deliverability", font=dict(size=20)),
        margin=dict(l=140, r=40, t=80, b=60),
        legend=dict(orientation="h", yanchor="bottom", y=-0.12, xanchor="center", x=0.75),
    )
    fig.update_yaxes(autorange="reversed", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    fig.update_xaxes(title_text="Funnel %", range=[0, max(funnel_pcts) * 1.25], row=1, col=1)
    fig.update_xaxes(
        tickvals=[-1, 0, 1, 2, 3, 4],
        ticktext=["N/A", "No", "Likely No", "Unclear", "Likely Yes", "Yes"],
        range=[-1.5, 4.5], row=1, col=2,
    )
    return fig


def build_heatmap(unique_brands, grouped, states_to_show):
    z_values, hover_texts = [], []
    for state in states_to_show:
        row_z, row_h = [], []
        for brand in unique_brands:
            key = (brand, state)
            if key in grouped:
                methods = grouped[key]
                v = list(methods.values())[0].get("deliverable", "unclear")
                row_z.append(VERDICT_NUM.get(v, 2))
                p = methods.get("shipping_policy", {})
                c = methods.get("cart_checkout", {})
                row_h.append(
                    f"<b>#{get_brand_rank(brand)} {brand}</b> ({get_brand_funnel(brand)}%) -> {state}<br>"
                    f"<b>{v.replace('_',' ').title()}</b>: {VERDICT_EVIDENCE.get(v,'')}<br>"
                    f"---------<br>"
                    f"Policy: {p.get('result','n/a').replace('_',' ')}<br>"
                    f"Cart: {c.get('result','n/a').replace('_',' ')}"
                )
            else:
                row_z.append(2)
                row_h.append(f"{brand} -> {state}<br>No data")
        z_values.append(row_z)
        hover_texts.append(row_h)

    labels = [f"#{get_brand_rank(b)} {b}" for b in unique_brands]
    fig = go.Figure(data=go.Heatmap(
        z=z_values, x=labels, y=states_to_show,
        hovertext=hover_texts, hoverinfo="text",
        colorscale=[
            [0.0, "#d5d8dc"], [0.2, "#e74c3c"], [0.4, "#f5b041"],
            [0.6, "#f9e79f"], [0.8, "#82e0aa"], [1.0, "#2ecc71"],
        ],
        showscale=True,
        colorbar=dict(title="Deliverability",
                      tickvals=[-1, 0, 1, 2, 3, 4],
                      ticktext=["N/A", "No", "Likely No", "Unclear", "Likely Yes", "Yes"]),
        zmin=-1, zmax=4,
    ))
    h = 250 if len(states_to_show) == 1 else 300
    fig.update_layout(
        title=dict(text="Deliverability Heatmap (Ranked by Brightfield)", font=dict(size=18)),
        xaxis_title="Brand (Brightfield Rank)", yaxis_title="State",
        height=h, margin=dict(l=80, r=40, t=80, b=120), xaxis=dict(tickangle=-45),
    )
    return fig


def build_pies(rows, states_to_show):
    filtered = [r for r in rows if r["state"] in states_to_show]
    method_counts = defaultdict(lambda: defaultdict(int))
    for row in filtered:
        method_counts[row["method"]][row["result"]] += 1

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Shipping Policy Results", "Cart/Checkout Results"),
        specs=[[{"type": "pie"}, {"type": "pie"}]],
    )
    for i, method in enumerate(["shipping_policy", "cart_checkout"]):
        counts = method_counts[method]
        labels = list(counts.keys())
        values = list(counts.values())
        colors = [RESULT_COLORS.get(l, "#95a5a6") for l in labels]
        display = [l.replace("_", " ").title() for l in labels]
        fig.add_trace(
            go.Pie(labels=display, values=values, marker_colors=colors,
                   textinfo="label+value", hoverinfo="label+value+percent"),
            row=1, col=i + 1,
        )
    state_label = " & ".join(states_to_show)
    fig.update_layout(
        title=dict(text=f"Scraping Method Results ({state_label})", font=dict(size=18)),
        height=400, margin=dict(l=40, r=40, t=80, b=40),
    )
    return fig


# ── Main report builder ─────────────────────────────────────────────

def build_report(rows, csv_path):
    grouped = defaultdict(dict)
    for row in rows:
        grouped[(row["brand"], row["state"])][row["method"]] = row

    brand_verdicts = defaultdict(dict)
    for (brand, state), methods in grouped.items():
        brand_verdicts[brand][state] = list(methods.values())[0].get("deliverable", "unclear")

    unique_brands = sorted(set(r["brand"] for r in rows), key=get_brand_rank)
    unique_states = sorted(set(r["state"] for r in rows))
    funnel_pcts = [get_brand_funnel(b) for b in unique_brands]

    # Build charts for each state filter
    state_views = [
        ("all", unique_states),
        ("Ohio", ["Ohio"]),
        ("Texas", ["Texas"]),
    ]

    chart_sections = {}
    for view_key, states in state_views:
        chart_sections[view_key] = {
            "ranked": build_ranked_chart(unique_brands, brand_verdicts, grouped, states, funnel_pcts),
            "heatmap": build_heatmap(unique_brands, grouped, states),
            "pies": build_pies(rows, states),
        }

    # Build HTML for chart sections with data-state-view wrappers
    def chart_divs(view_key, include_plotlyjs):
        display = "block" if view_key == "all" else "none"
        charts = chart_sections[view_key]
        pjs = "cdn" if include_plotlyjs else False
        return (
            f'<div class="state-view" data-state-view="{view_key}" style="display:{display}">'
            f'<div class="section">{charts["ranked"].to_html(full_html=False, include_plotlyjs=pjs)}</div>'
            f'<div class="section">{charts["heatmap"].to_html(full_html=False, include_plotlyjs=False)}</div>'
            f'<div class="section">{charts["pies"].to_html(full_html=False, include_plotlyjs=False)}</div>'
            f'</div>'
        )

    # Detail table (same HTML, filtered by JS)
    table_rows_html = []
    for brand in unique_brands:
        for state in unique_states:
            key = (brand, state)
            if key not in grouped:
                continue
            methods = grouped[key]
            p = methods.get("shipping_policy", {})
            c = methods.get("cart_checkout", {})
            v = p.get("deliverable", c.get("deliverable", "unclear"))

            rank = get_brand_rank(brand)
            funnel = get_brand_funnel(brand)
            policy_result = p.get("result", "n/a").replace("_", " ").title()
            cart_result = c.get("result", "n/a").replace("_", " ").title()
            verdict_label = v.upper().replace("_", " ")
            verdict_color = VERDICT_COLORS.get(v, "#f9e79f")
            evidence = VERDICT_EVIDENCE.get(v, "")

            policy_url = p.get("policy_url", "")
            link_cell = (f'<a href="{policy_url}" target="_blank">View Policy &rarr;</a>'
                         if policy_url else '<span style="color:#95a5a6;">Not found</span>')

            na_class = ' class="na-row"' if v == "n/a" else ""
            row_opacity = "opacity:0.5;" if v == "n/a" else ""
            table_rows_html.append(f"""
                <tr data-verdict="{v}" data-state="{state}"{na_class} style="{row_opacity}">
                    <td style="font-weight:600; color:#9b59b6;">#{rank}</td>
                    <td style="font-weight:600;">{brand}</td>
                    <td style="background:#f4ecf7; text-align:center;">{funnel}%</td>
                    <td>{state}</td>
                    <td>{policy_result}</td>
                    <td>{link_cell}</td>
                    <td>{cart_result}</td>
                    <td style="background:{verdict_color}; font-weight:600; text-align:center;"
                        title="{evidence}">{verdict_label}</td>
                </tr>""")

    # Assemble HTML
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>THCA Deliverability Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 1200px; margin: 0 auto; padding: 20px; background: #fafafa; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #2c3e50; padding-bottom: 10px; }}
        .meta {{ color: #7f8c8d; margin-bottom: 20px; }}
        .section {{ background: white; border-radius: 8px; padding: 20px; margin: 20px 0;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1); position: relative; overflow: hidden; }}
        .note {{ font-size: 13px; color: #7f8c8d; margin-top: 10px; font-style: italic; }}
        .legend-dot {{ width: 16px; height: 16px; border-radius: 3px; display: inline-block; }}
        .detail-table tbody tr {{ border-bottom: 1px solid #ecf0f1; }}
        .detail-table tbody tr:hover {{ background: #f8f9fa; }}
        .detail-table td {{ padding: 8px; }}
        .detail-table a {{ color: #2980b9; text-decoration: none; cursor: pointer; }}
        .detail-table a:hover {{ text-decoration: underline; color: #1a5276; }}
        .section-table {{ position: relative; z-index: 10; overflow: visible; }}

        /* Global filter bar */
        .global-filter {{ background: white; border-radius: 8px; padding: 14px 20px;
                          margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                          display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
                          position: sticky; top: 0; z-index: 100; }}
        .filter-label {{ font-size: 14px; font-weight: 600; color: #2c3e50; }}
        .state-btn {{ padding: 6px 16px; border: 1px solid #bdc3c7; border-radius: 4px;
                      background: white; cursor: pointer; font-size: 13px; color: #555;
                      transition: all 0.15s; }}
        .state-btn:hover {{ background: #ecf0f1; }}
        .state-btn-active {{ background: #2c3e50; color: white; border-color: #2c3e50; }}
        .filter-sep {{ width: 1px; height: 24px; background: #ddd; }}
    </style>
</head>
<body>
    <h1>THCA Deliverability Report</h1>
    <div class="meta">
        Generated: {ts} | Source: {os.path.basename(csv_path)} | Brands: {len(unique_brands)} | States: {', '.join(unique_states)}
    </div>
    <div class="note">Brands ranked by Brightfield Group Brand Funnel % (consumer awareness/consideration metric).</div>

    <!-- Global filter bar -->
    <div class="global-filter">
        <span class="filter-label">Filter by State:</span>
        <button onclick="setStateFilter('all')" id="gf-all" class="state-btn state-btn-active">All States</button>
        <button onclick="setStateFilter('Ohio')" id="gf-Ohio" class="state-btn">Ohio</button>
        <button onclick="setStateFilter('Texas')" id="gf-Texas" class="state-btn">Texas</button>
        <div class="filter-sep"></div>
        <label style="font-size:13px; color:#555; cursor:pointer; user-select:none;">
            <input type="checkbox" id="hideNaToggle" onchange="applyTableFilter()" style="cursor:pointer;">
            Hide brands without THCA
        </label>
    </div>

    <!-- Ratings explainer -->
    <div class="section" style="margin-top: 10px;">
        <h2 style="margin-top:0; font-size:16px; color:#2c3e50;">Availability Ratings Explained</h2>
        <p style="font-size:13px; color:#555; margin-bottom:14px;">
            Each brand is tested using two methods: <b>(1)</b> scraping the shipping policy page for state restriction
            language, and <b>(2)</b> adding a THCA product to cart and attempting checkout with an OH or TX zip code.
            The final verdict combines both signals.
        </p>
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px 12px; width:20px;"><div class="legend-dot" style="background:#2ecc71;"></div></td>
                <td style="padding:8px 4px; font-weight:600; white-space:nowrap; color:#2c3e50;">Yes</td>
                <td style="padding:8px 12px; color:#555;"><b>Confirmed deliverable.</b> Checkout accepted the zip code and displayed shipping rates.</td>
            </tr>
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px 12px;"><div class="legend-dot" style="background:#82e0aa;"></div></td>
                <td style="padding:8px 4px; font-weight:600; white-space:nowrap; color:#2c3e50;">Likely Yes</td>
                <td style="padding:8px 12px; color:#555;"><b>Probably deliverable.</b> Shipping policy doesn&rsquo;t restrict this state, but checkout couldn&rsquo;t be fully completed.</td>
            </tr>
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px 12px;"><div class="legend-dot" style="background:#f9e79f;"></div></td>
                <td style="padding:8px 4px; font-weight:600; white-space:nowrap; color:#2c3e50;">Unclear</td>
                <td style="padding:8px 12px; color:#555;"><b>Insufficient data.</b> Neither method produced a clear signal. Manual verification recommended.</td>
            </tr>
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px 12px;"><div class="legend-dot" style="background:#f5b041;"></div></td>
                <td style="padding:8px 4px; font-weight:600; white-space:nowrap; color:#2c3e50;">Likely No</td>
                <td style="padding:8px 12px; color:#555;"><b>Probably restricted.</b> Policy mentions this state with restriction language but context is ambiguous.</td>
            </tr>
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px 12px;"><div class="legend-dot" style="background:#e74c3c;"></div></td>
                <td style="padding:8px 4px; font-weight:600; white-space:nowrap; color:#2c3e50;">No</td>
                <td style="padding:8px 12px; color:#555;"><b>Confirmed restricted.</b> Checkout explicitly blocked the order for this state.</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;"><div class="legend-dot" style="background:#d5d8dc;"></div></td>
                <td style="padding:8px 4px; font-weight:600; white-space:nowrap; color:#2c3e50;">N/A</td>
                <td style="padding:8px 12px; color:#555;"><b>No THCA sold DTC.</b> Brand does not offer THCA products on their direct-to-consumer website.</td>
            </tr>
        </table>
    </div>

    <!-- Charts: 3 versions (all, Ohio, Texas) toggled by JS -->
    {chart_divs("all", True)}
    {chart_divs("Ohio", False)}
    {chart_divs("Texas", False)}

    <!-- Detail table -->
    <div class="section section-table">
        <h2 style="margin:0 0 12px 0; font-size:18px; color:#2c3e50;">Detailed Results (Ranked by Brightfield Brand Funnel)</h2>
        <table class="detail-table" id="detailTable" style="width:100%; border-collapse:collapse; font-size:12px;">
            <thead>
                <tr style="background:#2c3e50; color:white;">
                    <th style="padding:10px 8px; text-align:left;">Rank</th>
                    <th style="padding:10px 8px; text-align:left;">Brand</th>
                    <th style="padding:10px 8px; text-align:center;">Funnel %</th>
                    <th style="padding:10px 8px; text-align:left;">State</th>
                    <th style="padding:10px 8px; text-align:left;">Policy Result</th>
                    <th style="padding:10px 8px; text-align:left;">Shipping Policy</th>
                    <th style="padding:10px 8px; text-align:left;">Cart Result</th>
                    <th style="padding:10px 8px; text-align:center;">Verdict</th>
                </tr>
            </thead>
            <tbody>
                {"".join(table_rows_html)}
            </tbody>
        </table>
        <p style="font-size:11px; color:#95a5a6; margin-top:8px;">Hover over verdict cells for evidence summary.</p>
    </div>

    <script>
    let currentState = 'all';

    function setStateFilter(state) {{
        currentState = state;
        // Update buttons
        document.querySelectorAll('.global-filter .state-btn').forEach(b => b.classList.remove('state-btn-active'));
        document.getElementById('gf-' + state).classList.add('state-btn-active');
        // Toggle chart views
        document.querySelectorAll('.state-view').forEach(el => {{
            el.style.display = el.getAttribute('data-state-view') === state ? 'block' : 'none';
        }});
        // Filter table
        applyTableFilter();
    }}

    function applyTableFilter() {{
        const hideNa = document.getElementById('hideNaToggle').checked;
        document.querySelectorAll('#detailTable tbody tr').forEach(row => {{
            const state = row.getAttribute('data-state');
            const verdict = row.getAttribute('data-verdict');
            let show = true;
            if (currentState !== 'all' && state !== currentState) show = false;
            if (hideNa && verdict === 'n/a') show = false;
            row.style.display = show ? '' : 'none';
        }});
    }}
    </script>
</body>
</html>"""

    report_path = os.path.join(RESULTS_DIR, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    with open(report_path, "w") as f:
        f.write(html)

    print(f"Report saved to: {report_path}")
    return report_path


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else find_latest_csv()
    print(f"Loading: {csv_path}")
    rows = load_csv(csv_path)
    print(f"Loaded {len(rows)} rows")
    build_report(rows, csv_path)
