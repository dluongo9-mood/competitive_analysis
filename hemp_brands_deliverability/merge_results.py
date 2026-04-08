#!/usr/bin/env python3
"""Merge multiple deliverability CSVs into one, keeping latest per brand."""

import csv
import glob
import os
import sys
from datetime import datetime

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def merge():
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "deliverability_*.csv")))
    if len(files) < 2:
        print("Need at least 2 CSV files to merge")
        return

    # Take the two most recent
    file1, file2 = files[-2], files[-1]
    print(f"Merging:\n  {file1}\n  {file2}")

    all_rows = []
    seen = set()
    fieldnames = None

    # Read newest first so it takes priority
    for f in [file2, file1]:
        with open(f) as fh:
            reader = csv.DictReader(fh)
            if not fieldnames:
                fieldnames = reader.fieldnames
            for row in reader:
                key = (row["brand"], row["state"], row["method"])
                if key not in seen:
                    seen.add(key)
                    all_rows.append(row)

    # Sort by brightfield_rank, then state
    all_rows.sort(key=lambda r: (int(r.get("brightfield_rank", 99)), r["state"], r["method"]))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"deliverability_{ts}_merged.csv")

    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Merged {len(all_rows)} rows -> {out_path}")
    return out_path


if __name__ == "__main__":
    merge()
