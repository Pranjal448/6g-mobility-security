#!/usr/bin/env python3
"""
End-to-end state-machine simulation of TS 38.321 clause 5.4.4 (Scheduling Request
procedure), driven by REAL per-attempt SR detection probabilities measured against
srsRAN's own PUCCH Format 0 detector in ../atk16b_sr (not assumed, not hand-tuned).

p_sr source (2000 trials/point, D_ports_1/2/4 sets, flat Rayleigh fading, 10 dB SNR):
  ../atk16b_sr/results/ALL_sr_pucch.csv

The clause logic below is a literal transcription of Figure 4.1 / Section 4.2-4.4 of
chapters/dead_state.tex. It does not special-case "the attack succeeds": the only two
inputs that decide the outcome of a run are (a) the per-attempt success probability
p_sr, taken from the measured CSV, and (b) the two boolean guard conditions
(rach_lessHO_configured, ongoing_racHless_ltm_switch) exactly as clause 5.4.4 states
them. The negative-control block flips those booleans with the SAME bad channel data
to confirm the code is not hardwired to report "deadlock" -- see results/summary.csv.
"""
import csv
import random

# ---- measured p_sr (SR correctly detected this attempt) ----
# keyed by (ports, TA error in units); source: ALL_sr_pucch.csv, D_ports_1/2/4 rows
P_SR = {
    (1, 0): 0.9635, (1, 5): 0.616, (1, 6): 0.028, (1, 7): 0.0005, (1, 8): 0.0,
    (2, 0): 0.998,  (2, 5): 0.9675, (2, 6): 0.432, (2, 7): 0.001, (2, 8): 0.0,
    (4, 0): 1.0,    (4, 5): 1.0,   (4, 6): 0.9545, (4, 7): 0.0205, (4, 8): 0.0,
}

TABLE41 = {6: 0.800, 7: 0.996}  # chapters/dead_state.tex tab:determinism, 1 port


def run_once(p_sr, sr_trans_max, t_interval_ms, t304_ms,
             rach_lessHO_configured, ongoing_racHless_ltm_switch, rng):
    """One literal trace of clause 5.4.4's state machine."""
    sr_counter = 0
    t_elapsed = 0.0
    while True:
        if t_elapsed >= t304_ms:
            return "T304_EXPIRED_FIRST"
        if rng.random() < p_sr:                       # 1> else: SR occasion
            return "GRANT_RECEIVED"
        sr_counter += 1
        t_elapsed += t_interval_ms
        if sr_counter >= sr_trans_max:                 # 4> else: counter exhausted
            if (not rach_lessHO_configured) and (not ongoing_racHless_ltm_switch):
                return "RECOVERED_VIA_RA"               # depth-6> guard open
            return "DEADLOCK"                           # depth-6> guard closed


def monte_carlo(rows, group, label, p_sr, sr_trans_max, t_interval_ms, t304_ms,
                 rach_lessHO_configured, ongoing_racHless_ltm_switch, n, seed):
    rng = random.Random(seed)
    counts = {}
    for _ in range(n):
        outcome = run_once(p_sr, sr_trans_max, t_interval_ms, t304_ms,
                            rach_lessHO_configured, ongoing_racHless_ltm_switch, rng)
        counts[outcome] = counts.get(outcome, 0) + 1
    row = {
        "group": group, "label": label, "p_sr": p_sr, "sr_trans_max": sr_trans_max,
        "t_interval_ms": t_interval_ms, "t304_ms": t304_ms,
        "rach_lessHO_configured": rach_lessHO_configured,
        "ongoing_racHless_ltm_switch": ongoing_racHless_ltm_switch, "n": n,
        "p_deadlock": counts.get("DEADLOCK", 0) / n,
        "p_grant": counts.get("GRANT_RECEIVED", 0) / n,
        "p_recovered_ra": counts.get("RECOVERED_VIA_RA", 0) / n,
        "p_t304_first": counts.get("T304_EXPIRED_FIRST", 0) / n,
    }
    rows.append(row)
    print(f"{label:52s} -> " + ", ".join(
        f"{k}={row[k]:.4f}" for k in ("p_deadlock", "p_grant", "p_recovered_ra", "p_t304_first")
        if row[k] > 0))
    return row


def main():
    rows = []
    N = 200_000

    # ---- negative control: same bad channel, legacy (non-LTM) context ----
    monte_carlo(rows, "negative_control", "Legacy handover, p_sr=0.028 (as bad as 6-unit attack)",
                0.028, 8, 20, 10_000, False, False, N, 1)
    monte_carlo(rows, "negative_control", "Legacy handover, p_sr=0.0 (worse than any attack case)",
                0.0, 8, 20, 10_000, False, False, N, 2)

    # ---- honest UE, RACH-less LTM ongoing, no attacker ----
    for ports in (1, 2, 4):
        monte_carlo(rows, "honest", f"Honest, {ports} port(s), TA error=0",
                    P_SR[(ports, 0)], 8, 20, 10_000, True, True, N, 10 + ports)

    # ---- attack: RACH-less LTM ongoing, corrupted TA ----
    for ports in (1, 2, 4):
        for err in (6, 7, 8):
            r = monte_carlo(rows, "attack", f"Attack, {ports} port(s), TA error={err} units",
                             P_SR[(ports, err)], 8, 20, 10_000, True, True, N,
                             30 + ports * 10 + err)
            if ports == 1 and err in TABLE41:
                r["crosscheck_table41"] = TABLE41[err]

    # ---- T304 race, real deployed Amarisoft config (sr-TransMax=64, SR period 20ms) ----
    for t304 in (1000, 2000):
        monte_carlo(rows, "t304_race", f"Amarisoft config, full corruption, t304={t304}ms",
                    0.0, 64, 20, t304, True, True, 20_000, 40 + t304)

    with open("results/summary.csv", "w", newline="") as fh:
        fieldnames = list(rows[0].keys())
        for r in rows:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print("\nwrote results/summary.csv")


if __name__ == "__main__":
    main()
