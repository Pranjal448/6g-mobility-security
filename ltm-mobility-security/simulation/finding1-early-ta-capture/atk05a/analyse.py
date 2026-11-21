"""ATK-05a campaign analysis: turns results/*.csv into the tables the report quotes.

Three things happen here that are not in the raw CSVs.

1.  CAPTURE THRESHOLDS.  Each (delay, relative power) cell gives a win probability; the report
    needs the inverse -- the relative power at which the relayed copy wins 50% and 90% of the
    time -- so the curves are inverted by linear interpolation between the two bracketing
    sweep points rather than reported at the sweep's own 1 dB granularity.

2.  THE CONFIGURATION CAP.  The detector's reported `time_advance_max` is a hard ceiling: a
    timing advance beyond it cannot be reported at all, whatever the attacker does.  Expressed in
    T_A units it becomes directly comparable with the decodability boundary measured in the
    05b leg, which is what decides whether a given zeroCorrelationZoneConfig leaves the attacker
    any damaging range.

3.  THE LINK BUDGET.  A power threshold is not a result until it is turned into a place the
    relay can stand.  The received-power difference at the candidate cell is

        Delta[dB] = (P_relay - P_UE) - (PL(r) - PL(d))

    for a UE at d and a relay at r from the candidate cell, with PL from TR 38.901 Table
    7.4.1-1 as transcribed in 06_ltm_implementation/pathloss_38901.py (primary source, checked
    by test_pathloss_against_spec.py).  Solving for r at a given EIRP advantage gives the
    radius inside which the relay satisfies the threshold.

Run: python3 -I analyse.py            (writes results/SUMMARY_*.csv, prints the tables)
"""

from __future__ import annotations

import csv
import glob
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/06_ltm_implementation")

import pathloss_38901 as pl  # noqa: E402

R = os.path.join(HERE, "results")

# The 05b leg's measured decodability boundary, in T_A units, at the deployed srsRAN receiver.
# Open loop (FFT window held fixed) and closed loop (window re-positioned from the DM-RS
# time-alignment estimate).  Both are quoted so the cap table can be read either way.
BOUNDARY_OPEN_LOOP = 7.0
BOUNDARY_CLOSED_LOOP = 9.0


def load(tag):
    path = os.path.join(R, tag + ".csv")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [r for r in csv.DictReader(l for l in fh if not l.startswith("#"))]


def interp_threshold(points, target):
    """points = [(rel_db, p)] sorted by rel_db.  Return the rel_db at which p crosses target,
    linearly interpolated, or None if it never does."""
    prev = None
    for rel, p in points:
        if p >= target:
            if prev is None or p == target:
                return rel
            r0, p0 = prev
            if p == p0:
                return rel
            return r0 + (target - p0) * (rel - r0) / (p - p0)
        prev = (rel, p)
    return None


def table_capture(rows, label, out):
    by = defaultdict(list)
    for r in rows:
        by[float(r["delta_units"])].append((float(r["rel_db"]), float(r["p_attacker"]),
                                            float(r["p_damaging"]), float(r["p_detect"])))
    out("")
    out(f"### Capture thresholds -- {label}")
    out(f"{'delay (T_A units)':>18} {'rel. power for 50% capture':>27} "
        f"{'for 90%':>9} {'P(detect) at 0 dB':>18}")
    recs = []
    for k in sorted(by):
        s = sorted(by[k])
        t50 = interp_threshold([(a, b) for a, b, _, _ in s], 0.5)
        t90 = interp_threshold([(a, b) for a, b, _, _ in s], 0.9)
        pdet = next((d for a, _, _, d in s if abs(a) < 1e-9), float("nan"))
        recs.append((k, t50, t90, pdet))
        out(f"{k:>18.0f} {('%.2f dB' % t50) if t50 is not None else 'never':>27} "
            f"{('%.2f dB' % t90) if t90 is not None else 'never':>9} {pdet:>18.3f}")
    return recs


def table_cap(out):
    """The zeroCorrelationZoneConfig ceiling, read off the gates log, against the 05b boundary."""
    gates = os.path.join(HERE, "logs", "gates.log")
    if not os.path.exists(gates):
        return []
    recs = []
    for line in open(gates):
        if line.startswith("G3_window"):
            parts = dict(p.split("=") for p in line.split()[1:])
            recs.append((int(parts["zcz"]), float(parts["window_us"]),
                         float(parts["window_ta_units"])))
    out("")
    out("### Configuration ceiling: srsRAN's reported detection window versus the 05b boundary")
    out("    The detector cannot report a timing advance beyond `time_advance_max`, so a")
    out("    zeroCorrelationZoneConfig whose window is below the decodability boundary leaves the")
    out("    attacker no damaging range at ANY power or distance.")
    out(f"{'ZCZ':>4} {'window (us)':>12} {'window (T_A units)':>19} "
        f"{'damaging, open loop':>20} {'damaging, closed loop':>22}")
    with open(os.path.join(R, "SUMMARY_zcz_cap.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["zcz", "window_us", "window_ta_units", "damaging_open_loop",
                    "damaging_closed_loop"])
        for z, us, units in recs:
            a = units > BOUNDARY_OPEN_LOOP
            b = units > BOUNDARY_CLOSED_LOOP
            w.writerow([z, f"{us:.6f}", f"{units:.4f}", int(a), int(b)])
            out(f"{z:>4} {us:>12.4f} {units:>19.3f} {('yes' if a else 'NO'):>20} "
                f"{('yes' if b else 'NO'):>22}")
    return recs


def table_sensitivity(out, delta=10.0):
    """One-factor-at-a-time: how much each dimension moves the threshold.

    Scored on p_damaging, NOT on p_attacker: under a power-delay profile the "which path won"
    label is unreliable (about 45% of reported peaks land on one of the relayed cluster's later
    taps), and the delivered error is the quantity of interest in any case.
    """
    sets = {
        "fading model": sorted(glob.glob(os.path.join(R, "B_fading_*.csv"))),
        "SNR": [os.path.join(R, "C_snr.csv")],
        "preamble format": sorted(glob.glob(os.path.join(R, "G_fmt_*.csv"))),
        "numerology": sorted(glob.glob(os.path.join(R, "F_mu*.csv"))),
        "victim geometric delay": sorted(glob.glob(os.path.join(R, "H_tauv_*.csv"))),
    }
    out("")
    out(f"### Sensitivity of the damaging-error threshold, at an induced delay of "
        f"{delta:.0f} T_A units")
    out("    'never' means the threshold lies outside the swept power range for that set.")
    rowsout = []
    for name, files in sets.items():
        for f in files:
            if not os.path.exists(f):
                continue
            with open(f) as fh:
                rows = [r for r in csv.DictReader(l for l in fh if not l.startswith("#"))]
            # group by every column that varies inside this file
            groups = defaultdict(list)
            for r in rows:
                if abs(float(r["delta_units"]) - delta) > 1e-6:
                    continue
                key = (r["fading"], r["ds_ns"], r["snr_db"], r["fmt"], r["mu"], r["tau_v_us"])
                groups[key].append((float(r["rel_db"]), float(r["p_damaging"])))
            for key, pts in sorted(groups.items()):
                t50 = interp_threshold(sorted(pts), 0.5)
                t90 = interp_threshold(sorted(pts), 0.9)
                rowsout.append((name, os.path.basename(f)[:-4], *key, t50, t90))
    with open(os.path.join(R, "SUMMARY_sensitivity.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["dimension", "set", "fading", "ds_ns", "snr_db", "fmt", "mu", "tau_v_us",
                    "rel_db_50pct", "rel_db_90pct"])
        for rec in rowsout:
            w.writerow([*rec[:8],
                        "" if rec[8] is None else f"{rec[8]:.3f}",
                        "" if rec[9] is None else f"{rec[9]:.3f}"])
    out(f"{'dimension':>23} {'fading':>9} {'DS ns':>7} {'SNR':>6} {'fmt':>4} {'mu':>3} "
        f"{'tau_v us':>9} {'50%':>8} {'90%':>8}")
    for name, _set, fading, ds, snr, fmt, mu, tv, t50, t90 in rowsout:
        out(f"{name:>23} {fading:>9} {float(ds):>7.0f} {float(snr):>6.1f} {fmt:>4} {mu:>3} "
            f"{float(tv):>9.4f} {('%.2f' % t50) if t50 is not None else 'never':>8} "
            f"{('%.2f' % t90) if t90 is not None else 'never':>8}")
    return rowsout


def table_absent(out):
    rows = load("E_absent")
    if not rows:
        return
    out("")
    out("### Victim absent: the attacker alone on the ordered contention-free preamble")
    out("    TS 38.300 clause 9.2.3.5.2 step 4b uses CFRA with a network-assigned preamble index,")
    out("    so a detection of that index is attributed to that UE whether or not it transmitted.")
    by = defaultdict(list)
    for r in rows:
        by[float(r["snr_db"])].append((float(r["delta_units"]), float(r["p_detect"]),
                                       float(r["mean_err_units"]), float(r["sd_err_units"])))
    out(f"{'SNR (dB)':>9} {'P(detected), min over delays':>29} "
        f"{'worst |mean error - delay| (units)':>35}")
    for snr in sorted(by):
        s = by[snr]
        pmin = min(p for _, p, _, _ in s)
        werr = max(abs(m - d) for d, _, m, _ in s)
        out(f"{snr:>9.1f} {pmin:>29.3f} {werr:>35.4f}")


def table_link_budget(out, thresholds=(0.22, 5.3, 9.9)):
    """Where the relay has to stand.  For a UE at d from the candidate cell and a relay at r,
    the relay meets a threshold Delta when (P_relay - P_UE) - (PL(r) - PL(d)) >= Delta."""
    out("")
    out("### Link budget: relay placement, TR 38.901 Table 7.4.1-1 (primary-source transcription)")
    out("    r_max = the largest relay-to-candidate distance at which the threshold is met, for a")
    out("    relay whose EIRP exceeds the UE's by the stated amount.  UE at d from the candidate.")
    fc = 3.5
    with open(os.path.join(R, "SUMMARY_link_budget.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "fc_ghz", "threshold_db", "eirp_advantage_db", "ue_distance_m",
                    "relay_r_max_m", "relay_r_max_over_d"])
        for scen, fn in (("UMa NLOS", pl.uma_nlos), ("UMi NLOS", pl.umi_nlos)):
            out("")
            out(f"  {scen}, fc = {fc} GHz")
            out(f"{'threshold':>10} {'EIRP adv.':>10} " +
                "".join(f"{('d=' + str(d) + ' m'):>13}" for d in (200, 500, 1000, 2000)))
            for thr in thresholds:
                for adv in (0.0, 10.0, 20.0, 30.0):
                    cells = []
                    for d in (200, 500, 1000, 2000):
                        pld = fn(float(d), fc)
                        rmax = None
                        r = 10.0
                        while r <= 5000.0:
                            if (adv - (fn(r, fc) - pld)) >= thr:
                                rmax = r
                            else:
                                break
                            r += 5.0
                        cells.append(rmax)
                        w.writerow([scen, fc, thr, adv, d,
                                    "" if rmax is None else f"{rmax:.0f}",
                                    "" if rmax is None else f"{rmax / d:.3f}"])
                    out(f"{thr:>9.1f}dB {adv:>9.0f}dB " +
                        "".join(f"{('%.0f m' % c) if c else 'nowhere':>13}" for c in cells))


def main():
    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("=" * 100)
    out("ATK-05a FULL CAMPAIGN -- analysis")
    out("=" * 100)
    gates = os.path.join(HERE, "logs", "gates.log")
    if os.path.exists(gates):
        out("")
        out("### validation gates (verbatim)")
        for line in open(gates):
            out("  " + line.rstrip())

    for tag, label in (("A_surface_rayleigh", "flat Rayleigh per path, SNR 10 dB, ZCZ 15"),
                       ("A_surface_pdp300", "20-tap exponential PDP, DS 300 ns, SNR 10 dB, ZCZ 15"),
                       ("A_surface_none", "no fading (derivation check), SNR 10 dB, ZCZ 15")):
        rows = load(tag)
        if rows:
            recs = table_capture(rows, label, out)
            with open(os.path.join(R, f"SUMMARY_capture_{tag}.csv"), "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["delta_units", "rel_db_50pct", "rel_db_90pct", "p_detect_at_0db"])
                for k, t50, t90, pdet in recs:
                    w.writerow([k, "" if t50 is None else f"{t50:.3f}",
                                "" if t90 is None else f"{t90:.3f}", f"{pdet:.4f}"])

    table_cap(out)
    table_sensitivity(out)
    table_absent(out)
    table_link_budget(out)

    with open(os.path.join(HERE, "logs", "analysis_tables.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    out("")
    out("written: logs/analysis_tables.txt and results/SUMMARY_*.csv")


if __name__ == "__main__":
    main()
