"""Three-point calibration of the DTC revenue model."""

# Actual revenue data points
# ─────────────────────────────────────────────────────
# Mood: confirmed ~$3M/mo in gummy revenue, $100 AOV
mood_actual = 3_000_000

# Charlotte's Web: $49.9M/yr total, DTC = 67%, gummies = largest category
# Gummies are 75% of their catalog. Estimate 50-75% of DTC revenue.
cweb_dtc = 49.9e6 * 0.67 / 12  # $2.78M/mo total DTC
cweb_gummy_lo = cweb_dtc * 0.50  # $1.39M
cweb_gummy_hi = cweb_dtc * 0.75  # $2.09M
cweb_gummy_mid = (cweb_gummy_lo + cweb_gummy_hi) / 2  # $1.74M

# cbdMD: $19.19M/yr total, DTC = 72%. More tinctures/topicals/pet.
# Estimate gummies = 30-50% of DTC.
cbdmd_dtc = 19.19e6 * 0.72 / 12  # $1.15M/mo total DTC
cbdmd_gummy_lo = cbdmd_dtc * 0.30  # $345K
cbdmd_gummy_hi = cbdmd_dtc * 0.50  # $575K
cbdmd_gummy_mid = (cbdmd_gummy_lo + cbdmd_gummy_hi) / 2  # $460K

# Our model estimates (from last dashboard build)
model = {
    "Mood":             {"low": 486_133, "high": 2_589_132, "visits": 1_605_734},
    "Charlotte's Web":  {"low": 281_193, "high": 1_499_360, "visits": 174_158},
    "cbdMD":            {"low": 89_734,  "high": 478_580,   "visits": 183_802},
}

actuals = {
    "Mood":             mood_actual,
    "Charlotte's Web":  cweb_gummy_mid,
    "cbdMD":            cbdmd_gummy_mid,
}

print("=" * 90)
print(f"{'Brand':<20} {'Actual Gummy/mo':>15} {'Model Low':>12} {'Model High':>12} {'Lo/Act':>8} {'Hi/Act':>8}")
print("=" * 90)

ratios_lo = []
ratios_hi = []

for brand in ["Mood", "Charlotte's Web", "cbdMD"]:
    actual = actuals[brand]
    m = model[brand]
    r_lo = m["low"] / actual
    r_hi = m["high"] / actual
    ratios_lo.append(r_lo)
    ratios_hi.append(r_hi)

    if brand == "Mood":
        act_str = f"${actual:,.0f}"
    else:
        lo = cweb_gummy_lo if brand == "Charlotte's Web" else cbdmd_gummy_lo
        hi = cweb_gummy_hi if brand == "Charlotte's Web" else cbdmd_gummy_hi
        act_str = f"${lo/1e3:.0f}K-${hi/1e3:.0f}K"

    print(f"{brand:<20} {act_str:>15} ${m['low']:>11,} ${m['high']:>11,} {r_lo:>7.0%} {r_hi:>7.0%}")

print()
avg_lo = sum(ratios_lo) / len(ratios_lo)
avg_hi = sum(ratios_hi) / len(ratios_hi)

print(f"Average conservative / actual:  {avg_lo:.0%}  (underpredicts by {1/avg_lo:.1f}x)")
print(f"Average calibrated / actual:    {avg_hi:.0%}  (underpredicts by {1/avg_hi:.1f}x)")

print()
print("=== Interpretation ===")
print(f"Conservative model captures ~{avg_lo:.0%} of actual gummy revenue on average")
print(f"Calibrated model captures ~{avg_hi:.0%} of actual gummy revenue on average")
print()
print(f"To get true revenue from model estimates:")
print(f"  Conservative × {1/avg_lo:.1f} = actual")
print(f"  Calibrated   × {1/avg_hi:.1f} = actual")
print()

# What would applying these multipliers give us for total DTC?
dtc_total_low = 2_666_234   # from dashboard
dtc_total_high = 12_697_556  # from dashboard

print(f"Current DTC totals: ${dtc_total_low/1e6:.1f}M (low) – ${dtc_total_high/1e6:.1f}M (high)")
print(f"Adjusted totals:    ${dtc_total_low/avg_lo/1e6:.1f}M (low×{1/avg_lo:.1f}) – ${dtc_total_high/avg_hi/1e6:.1f}M (high×{1/avg_hi:.1f})")
