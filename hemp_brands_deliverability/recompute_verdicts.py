#!/usr/bin/env python3
"""Re-compute deliverability verdicts on an existing CSV using updated logic."""

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime

from scraper import determine_deliverability

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def recompute(input_path):
    with open(input_path) as f:
        rows = list(csv.DictReader(f))

    # Group by brand+state
    grouped = defaultdict(list)
    for r in rows:
        key = (r["brand"], r["state"])
        grouped[key].append(r)

    # Recompute verdicts
    for key, group in grouped.items():
        verdict = determine_deliverability(group)
        for r in group:
            r["deliverable"] = verdict

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"deliverability_{ts}_recomputed.csv")

    fieldnames = rows[0].keys()
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Recomputed {len(rows)} rows -> {out_path}")

    # Print summary
    for key, group in sorted(grouped.items()):
        brand, state = key
        print(f"  {brand:20} -> {state}: {group[0]['deliverable']}")

    return out_path


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else max(
        [os.path.join(RESULTS_DIR, f) for f in os.listdir(RESULTS_DIR) if f.startswith("deliverability_")],
        key=os.path.getmtime,
    )
    recompute(path)
