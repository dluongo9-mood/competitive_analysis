#!/usr/bin/env python3
"""
Consolidate individual dashboards into a single tabbed HTML page.

Reads the standalone dashboard HTML files, extracts their body content,
namespaces element IDs and JS globals to avoid collisions, and assembles
a combined page with tab navigation.

Output: docs/index.html (for GitHub Pages deployment)
"""

import re
import sys
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

DASHBOARDS = [
    {
        "key": "supplements",
        "label": "Supplements",
        "file": "supplement_dashboard.html",
        "prefix": "supp",
        "ids": [
            "dt-search", "dt-filter", "dt-ff-filter", "dt-count",
            "explorer-table", "explorer-body",
        ],
        "bg": "#f0f4f8",
        "max_width": "1280px",
    },
    {
        "key": "mushrooms",
        "label": "Mushrooms",
        "file": "mushroom_dashboard.html",
        "prefix": "mush",
        "ids": [
            "dt-search", "dt-source", "dt-ff", "dt-mt", "dt-sort",
            "dt-count", "dt-table", "dt-body", "dt-more",
            "cd-search", "cd-count", "cd-table", "cd-body",
            "ai-status", "ai-remaining", "ai-question", "ai-btn", "ai-response",
        ],
        "bg": "#f5f6fa",
        "max_width": "1600px",
        "inline_onclick_fns": [
            "showMore", "exportCSV", "askAI", "exportMarketMapCSV",
            "exportKeepaBrandCSV", "exportKeepaFFCSV",
            "exportCompetitorCSV", "sortCompetitors",
        ],
    },
    # Uncomment when ready:
    # {
    #     "key": "thc",
    #     "label": "THC Gummies",
    #     "file": "thc_gummies_dashboard.html",
    #     "prefix": "thc",
    #     "ids": ["dt-search", "dt-body", "dt-count", ...],
    #     "bg": "#f7fafc",
    #     "max_width": "1400px",
    # },
]

OUTPUT_PATH = Path("docs/index.html")


# ── Extraction helpers ───────────────────────────────────────────────────────

def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    return p.read_text(encoding="utf-8")


def extract_body(html: str) -> str:
    """Return content between <body> and </body> tags."""
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL)
    if not m:
        # No body tags — some dashboards are just div content after <style>
        # Try extracting everything after closing </style>...</head> up to </html>
        m = re.search(r"</style>\s*</head>\s*(.*?)\s*</html>", html, re.DOTALL)
        if not m:
            # Last resort: everything after </head>
            m = re.search(r"</head>\s*(.*?)\s*</html>", html, re.DOTALL)
    return m.group(1).strip() if m else html


def namespace_ids(html: str, prefix: str, ids: list[str]) -> str:
    """Replace element IDs and their getElementById references with prefixed versions."""
    for eid in ids:
        prefixed = f"{prefix}-{eid}"
        # id="..." in HTML
        html = html.replace(f'id="{eid}"', f'id="{prefixed}"')
        # getElementById('...') and getElementById("...") in JS
        html = html.replace(f"getElementById('{eid}')", f"getElementById('{prefixed}')")
        html = html.replace(f'getElementById("{eid}")', f'getElementById("{prefixed}")')
        # Bare string references in JS arrays/objects like ['dt-search', ...]
        html = html.replace(f"'{eid}'", f"'{prefixed}'")
        html = html.replace(f'"{eid}"', f'"{prefixed}"')
    # Undo double-prefixing on id= attributes (already replaced above, then hit again by bare string)
    for eid in ids:
        prefixed = f"{prefix}-{eid}"
        double = f"{prefix}-{prefixed}"
        html = html.replace(f'id="{double}"', f'id="{prefixed}"')
        html = html.replace(f"getElementById('{double}')", f"getElementById('{prefixed}')")
        html = html.replace(f'getElementById("{double}")', f'getElementById("{prefixed}")')
        html = html.replace(f"'{double}'", f"'{prefixed}'")
        html = html.replace(f'"{double}"', f'"{prefixed}"')
    return html


def wrap_scripts_in_iife(html: str, prefix: str, inline_onclick_fns: list[str] | None = None) -> str:
    """Wrap user-defined <script> blocks in IIFEs to isolate globals.

    Skips Plotly-generated scripts (they contain Plotly.newPlot and are self-contained).
    For inline onclick handlers, exposes namespaced globals on window.
    """
    inline_fns = inline_onclick_fns or []

    def wrap_match(m):
        script_content = m.group(1)
        # Skip Plotly auto-generated chart scripts
        if "Plotly.newPlot" in script_content or "Plotly.react" in script_content:
            return m.group(0)

        # Build window assignments for inline onclick functions
        exports = ""
        if inline_fns:
            assignments = []
            for fn in inline_fns:
                namespaced = f"__{prefix}_{fn}"
                if f"function {fn}" in script_content or f"{fn} =" in script_content:
                    assignments.append(f"window.{namespaced} = {fn};")
            if assignments:
                exports = "\n" + "\n".join(assignments) + "\n"

        return f"<script>\n(function() {{\n{script_content}{exports}\n}})();\n</script>"

    result = re.sub(r"<script>\s*(.*?)\s*</script>", wrap_match, html, flags=re.DOTALL)

    # Update ALL inline event handler references (onclick, onkeydown, etc.)
    for fn in inline_fns:
        namespaced = f"__{prefix}_{fn}"
        # Replace fn() calls in any inline handler attribute value
        # This catches onclick="fn()", onkeydown="if(...) fn()", etc.
        # Use word boundary to avoid partial matches
        result = re.sub(
            rf'(?<=\s)(on\w+=")([^"]*?)\b{fn}\b([^"]*?")',
            lambda m: f'{m.group(1)}{m.group(2)}{namespaced}{m.group(3)}',
            result,
        )
        result = re.sub(
            rf"(?<=\s)(on\w+=')([^']*?)\b{fn}\b([^']*?')",
            lambda m: f'{m.group(1)}{m.group(2)}{namespaced}{m.group(3)}',
            result,
        )

    return result


# ── HTML assembly ────────────────────────────────────────────────────────────

def build_tab_nav(dashboards: list[dict]) -> str:
    buttons = []
    for i, d in enumerate(dashboards):
        active = ' class="active"' if i == 0 else ""
        buttons.append(f'<button{active} data-tab="{d["key"]}">{d["label"]}</button>')
    return "\n        ".join(buttons)


def build_combined_html(dashboards: list[dict], bodies: list[str]) -> str:
    tab_nav = build_tab_nav(dashboards)

    panels = []
    for i, (d, body) in enumerate(zip(dashboards, bodies)):
        active = " active" if i == 0 else ""
        panels.append(
            f'<div id="tab-{d["key"]}" class="tab-panel{active}"'
            f' style="background:{d["bg"]};">\n{body}\n</div>'
        )
    panels_html = "\n\n".join(panels)

    # Tab-scoped CSS overrides
    tab_overrides = []
    for d in dashboards:
        tab_overrides.append(f"#tab-{d['key']} .grid {{ max-width: {d['max_width']}; }}")
    tab_css = "\n    ".join(tab_overrides)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Competitive Intelligence</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  /* ── Reset & base ── */
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f0f4f8; color: #1a202c; }}

  /* ── Tab navigation ── */
  .tab-nav {{
    position: sticky; top: 0; z-index: 1000;
    background: #0f172a;
    display: flex; align-items: center;
    padding: 0 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }}
  .tab-nav .brand {{
    font-size: 15px; font-weight: 700; color: rgba(255,255,255,0.9);
    margin-right: 32px; white-space: nowrap;
    letter-spacing: 0.3px;
  }}
  .tab-nav button {{
    background: none; border: none; color: rgba(255,255,255,0.6);
    font-size: 14px; font-weight: 500; padding: 14px 20px;
    cursor: pointer; position: relative; transition: color 0.15s;
  }}
  .tab-nav button:hover {{ color: rgba(255,255,255,0.9); }}
  .tab-nav button.active {{
    color: white;
  }}
  .tab-nav button.active::after {{
    content: ''; position: absolute; bottom: 0; left: 12px; right: 12px;
    height: 3px; background: #3b82f6; border-radius: 3px 3px 0 0;
  }}

  /* ── Tab panels ── */
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}

  /* ── Shared dashboard styles ── */
  .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2563EB 100%);
             color: white; padding: 28px 40px; }}
  .header h1 {{ font-size: 26px; font-weight: 700; margin-bottom: 6px; }}
  .header p {{ font-size: 14px; opacity: 0.85; }}
  .stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-top: 16px; }}
  .stat {{ background: rgba(255,255,255,0.15); border-radius: 8px; padding: 12px 20px;
           min-width: 100px; text-align: center; }}
  .stat .num {{ font-size: 22px; font-weight: 800; }}
  .stat .label {{ font-size: 11px; opacity: 0.8; margin-top: 2px;
                  text-transform: uppercase; letter-spacing: 0.5px; }}
  .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;
           padding: 24px 40px; margin: 0 auto; }}
  .card {{ background: white; border-radius: 10px; padding: 8px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow: hidden; }}
  .full-width {{ grid-column: 1 / -1; }}
  .section-header {{ grid-column: 1 / -1; margin-top: 16px; padding: 12px 0 4px; }}
  .section-header h2 {{ font-size: 20px; color: #1e293b; }}
  .section-header p {{ font-size: 13px; color: #718096; margin-top: 2px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ text-align: left; padding: 8px 12px; font-size: 12px; font-weight: 700;
       color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;
       border-bottom: 2px solid #e2e8f0; }}
  td {{ border-bottom: 1px solid #f0f0f0; font-size: 13px; }}
  a {{ color: #2563EB; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  details summary {{ cursor: pointer; }}
  .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #999; }}

  @media (max-width: 1000px) {{ .grid {{ grid-template-columns: 1fr; }} }}

  /* ── Per-tab overrides ── */
  {tab_css}
</style>
</head>
<body>

<nav class="tab-nav">
  <div class="brand">Competitive Intelligence</div>
  {tab_nav}
</nav>

{panels_html}

<script>
// ── Tab switching with Plotly resize ──
document.querySelectorAll('.tab-nav button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    // Deactivate all
    document.querySelectorAll('.tab-nav button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

    // Activate clicked tab
    btn.classList.add('active');
    const panel = document.getElementById('tab-' + btn.dataset.tab);
    panel.classList.add('active');

    // Resize Plotly charts that were hidden (rendered at zero width)
    setTimeout(() => {{
      panel.querySelectorAll('.js-plotly-plot').forEach(plot => {{
        Plotly.Plots.resize(plot);
      }});
    }}, 50);
  }});
}});
</script>

</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Building combined dashboard...")

    bodies = []
    for d in DASHBOARDS:
        print(f"  Processing {d['file']}...")
        html = read_file(d["file"])
        body = extract_body(html)
        body = namespace_ids(body, d["prefix"], d["ids"])
        body = wrap_scripts_in_iife(body, d["prefix"], d.get("inline_onclick_fns"))
        bodies.append(body)

    combined = build_combined_html(DASHBOARDS, bodies)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(combined, encoding="utf-8")

    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"  Wrote {OUTPUT_PATH} ({size_mb:.1f} MB)")
    print("Done.")


if __name__ == "__main__":
    main()
