"""ATK-05b campaign analysis -- Leg R: the decodability boundary with and without re-tracking.

WHAT A BOUNDARY MEANS HERE
--------------------------
For each run the sweep gives post-equalisation EVM against the uplink timing error, in both
directions.  The boundary is the smallest |error| at which the mean EVM crosses a threshold.
Two thresholds are reported:

  EVM 0.3162 (-10 dB)   a generous "the slot is still carryable" line.  It sits below every one
                        of the sixteen LDPC+CRC waterfall thresholds the 2026-11-11 rebuild
                        measured with OAI's real coded chain, so a slot that fails this fails
                        the code as well, at any of the measured MCS values.
  EVM 1.0    (0 dB)     error power equal to signal power: unambiguously dead.

Reported for both receiver models:

  open loop     the FFT window stays where the receiver put it.  This is what srsRAN actually
                does: the uplink window offset comes from `static constexpr float
                dft_window_offset = 0.5F` in lib/phy/lower/processors/uplink/
                uplink_processor_factories.cpp, is converted to samples once at factory
                construction (puxch_processor_factories.cpp), and the resulting
                `nof_samples_window_offset` member is never written again -- there is no runtime
                path to move it.  The DM-RS time-alignment estimate is used to generate Timing
                Advance Commands for the UE, not to move the gNB's own window.
  closed loop   the window is moved by the DM-RS time-alignment reading, rounded to a whole T_A
                unit, and the SAME received samples are demodulated again.  No deployed receiver
                in either open-source stack does this; it is included because the 2026-11-11
                rebuild named it as its largest untested item and as attacker-favourable, so it
                has to be bounded rather than assumed away.  Both correction signs are applied
                and the better taken, so this is the most generous possible reading.

The baseline matters: at TA = 0 the aligned slot already fails the -10 dB EVM criterion on some
trials (TDL-C 300 ns, ZF, one receive antenna), so the recovered fraction is also reported
NORMALISED to its own TA = 0 value.

Run: python3 -I analyse.py
"""

from __future__ import annotations

import csv
import glob
import os

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")

EVM_CARRYABLE = 0.3162   # -10 dB
EVM_DEAD = 1.0           # 0 dB


def load(path):
    with open(path) as fh:
        return [r for r in csv.DictReader(l for l in fh if not l.startswith("#"))]


def boundary(rows, col, thr, sign):
    """Smallest |ta_units| of the given sign at which `col` crosses `thr`, by linear
    interpolation between the bracketing sweep points.  None if it never crosses."""
    pts = sorted((int(r["ta_units"]), float(r[col])) for r in rows
                 if r[col] not in ("", "nan") and (int(r["ta_units"]) * sign > 0
                                                   or int(r["ta_units"]) == 0))
    pts = [(abs(t), v) for t, v in pts if t * sign >= 0]
    pts.sort()
    prev = None
    for t, v in pts:
        if v >= thr:
            if prev is None:
                return float(t)
            t0, v0 = prev
            if v == v0:
                return float(t)
            return t0 + (thr - v0) * (t - t0) / (v - v0)
        prev = (t, v)
    return None


def estimator_range(rows):
    """The DM-RS estimator's unambiguous range: the largest |ta| up to which the reading tracks
    the truth monotonically, and the |ta| at which its magnitude peaks before folding back."""
    pts = sorted((int(r["ta_units"]), float(r["ta_est_units_mean"])) for r in rows)
    pos = [(t, v) for t, v in pts if t > 0]
    best_t, best_v = 0, 0.0
    for t, v in pos:
        if abs(v) > abs(best_v):
            best_t, best_v = t, v
    return best_t, best_v


def main():
    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("=" * 112)
    out("ATK-05b FULL CAMPAIGN -- Leg R: decodability boundary, open loop versus re-tracking")
    out("=" * 112)

    files = sorted(glob.glob(os.path.join(R, "*.csv")))
    files = [f for f in files
         if not os.path.basename(f).startswith(("ALL_", "SUMMARY_"))]

    # ------------------------------------------------------------------ gates
    out("")
    out("### Gates")
    for f in files:
        tag = os.path.basename(f)[:-4]
        if not tag.startswith("GATE"):
            continue
        rows = load(f)
        aligned = [r for r in rows if int(r["ta_units"]) == 0]
        if not aligned:
            continue
        a = aligned[0]
        evm = float(a["evm_mean"])
        est = float(a["ta_est_units_mean"])
        cl = float(a["cl_evm_mean"]) if a["cl_evm_mean"] not in ("", "nan") else float("nan")
        ok_evm = evm < EVM_CARRYABLE
        ok_est = abs(est) < 1.0
        out(f"  {tag:<22} aligned EVM={evm:.4f} ({'PASS' if ok_evm else 'FAIL'})  "
            f"estimator reading={est:+.3f} T_A units ({'PASS' if ok_est else 'FAIL'})  "
            f"closed-loop EVM={cl:.4f}")

    # ------------------------------------------------------------------ boundaries
    out("")
    out("### Boundaries, in T_A units.  E = early arrival (the relay/ATK-05 direction), "
        "L = late.")
    out("    'n/a' means the aligned slot already fails the criterion, so no boundary exists "
        "for that configuration.")
    out(f"{'set':<24} {'open E':>7} {'open L':>7} {'closed E':>9} {'closed L':>9} "
        f"{'dead E':>7} {'est range':>10} {'est peak':>9} {'recov@0':>8} {'EVM@0':>8}")
    summary = []
    for f in files:
        tag = os.path.basename(f)[:-4]
        if tag.startswith("GATE"):
            continue
        rows = load(f)
        if not rows:
            continue
        oe = boundary(rows, "evm_mean", EVM_CARRYABLE, +1)
        ol = boundary(rows, "evm_mean", EVM_CARRYABLE, -1)
        ce = boundary(rows, "cl_evm_mean", EVM_CARRYABLE, +1)
        cl_ = boundary(rows, "cl_evm_mean", EVM_CARRYABLE, -1)
        de = boundary(rows, "evm_mean", EVM_DEAD, +1)
        rng, pk = estimator_range(rows)
        base = next((float(r["cl_recovered_fraction"]) for r in rows
                     if int(r["ta_units"]) == 0
                     and r["cl_recovered_fraction"] not in ("", "nan")), float("nan"))
        # If the ALIGNED slot already fails the criterion, the boundary for that criterion is
        # not defined for this configuration: the link is broken before the attack starts, and
        # reporting 0.00 would read as "the attack succeeds at zero error", which is wrong.
        evm0 = next((float(r["evm_mean"]) for r in rows if int(r["ta_units"]) == 0),
                    float("nan"))
        if evm0 >= EVM_CARRYABLE:
            oe = ol = ce = cl_ = None
        if evm0 >= EVM_DEAD:
            de = None
        summary.append((tag, oe, ol, ce, cl_, de, rng, pk, base))

        def fmt(v):
            return ("n/a" if evm0 >= EVM_CARRYABLE else "never") if v is None else f"{v:.2f}"

        out(f"{tag:<24} {fmt(oe):>7} {fmt(ol):>7} {fmt(ce):>9} {fmt(cl_):>9} "
            f"{fmt(de):>7} {rng:>10} {pk:>9.2f} {base:>8.2f} {evm0:>8.3f}")

    with open(os.path.join(R, "SUMMARY_boundaries.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["set", "open_loop_early", "open_loop_late", "closed_loop_early",
                    "closed_loop_late", "dead_early", "estimator_peak_ta_units",
                    "estimator_peak_reading", "recovered_fraction_at_ta0"])
        for rec in summary:
            w.writerow([rec[0]] + ["" if v is None else (f"{v:.4f}" if isinstance(v, float)
                                                        else v) for v in rec[1:]])

    # ------------------------------------------------------------------ what re-tracking buys
    out("")
    out("### What re-tracking buys the receiver, in T_A units (closed loop minus open loop)")
    gains = [(t, ce - oe) for t, oe, ol, ce, *_ in summary
             if oe is not None and ce is not None and oe > 0.0]
    if gains:
        vals = sorted(g for _, g in gains)
        out(f"  sets compared : {len(gains)}")
        out(f"  minimum gain  : {vals[0]:+.2f} T_A units")
        out(f"  median gain   : {vals[len(vals) // 2]:+.2f} T_A units")
        out(f"  maximum gain  : {vals[-1]:+.2f} T_A units")
        out("")
        out("  The gain is bounded by the DM-RS estimator's own unambiguous range: beyond it the")
        out("  reading folds back towards zero, so the correction the receiver computes is")
        out("  smaller than the error it is trying to remove, and at large errors it points the")
        out("  wrong way entirely.")

    # ------------------------------------------------------------------ the deployed case
    out("")
    out("### Which boundary applies to the first PUSCH of a RACH-less LTM cell switch")
    out("  srsRAN's uplink FFT window offset is `static constexpr float dft_window_offset = 0.5F`")
    out("  (lib/phy/lower/processors/uplink/uplink_processor_factories.cpp), converted to samples")
    out("  once at factory construction and never written again -- there is no runtime path to")
    out("  move the gNB's own window.  The DM-RS time-alignment estimate is used to generate a")
    out("  Timing Advance Command for the UE instead, so the loop runs through the UE and needs")
    out("  a PDCCH to carry the command.  For the FIRST PUSCH transmission of a RACH-less LTM")
    out("  cell switch no such command has been sent for the target cell yet, so the OPEN-LOOP")
    out("  boundary is the operative one; the closed-loop figure bounds what a receiver that")
    out("  buffered and re-demodulated its own samples would gain, which neither open-source")
    out("  stack does.")

    with open(os.path.join(HERE, "logs", "analysis_tables.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    out("")
    out("written: logs/analysis_tables.txt, results/SUMMARY_boundaries.csv")


if __name__ == "__main__":
    main()
