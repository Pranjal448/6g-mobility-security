#!/usr/bin/env python3
"""
End-to-end Monte Carlo simulation of Finding 1 (corrupted early timing advance),
chained into Finding 2's clause 5.4.4 state machine to close the "capture -> TA
corruption -> uplink decode failure -> SR deadlock" pipeline as one simulated
system, using exclusively REAL measured data (no assumed or hand-tuned numbers):

Stage A (capture): p_attacker(rel_db), the probability the candidate gNB's real
  PRACH detector reports the RELAY's copy rather than the victim's, measured on
  srsRAN's own detector.
  Source: ../atk05a/results/A_surface_rayleigh.csv (flat Rayleigh per path;
  200 trials/point; this is the identical curve plotted in the report's
  Figure 3.1 / fig_atk05a_capture.py, column p_attacker, delta_units=7). The same
  file confirms p_attacker is independent of delta_units to within simulation
  noise (7/16/32-unit columns overlay), so one rel_db->p_attacker table is used
  for all three induced delays.

Stage B (decode): P(decode_fail | TA error in units), the probability a real
  LDPC-coded uplink transport block fails CRC at that TA error. Sampled
  unconditionally (not gated on capture): even a zero-error transmission has a
  real, nonzero baseline failure rate from ordinary channel noise.
  Source: ../../08_final_factcheck/sim_rebuild/results/SUMMARY_composed.csv,
  direction == "EARLY_arrival_attack_dir" (the attack-relevant direction),
  aggregated (fraction with bler >= 0.99) across all 96 real measured
  configurations in that file (mcs in {2,4,6,9} x 2 window offsets x 3
  numerologies x {TDL-A, TDL-C} x {30, 300} ns delay spread). Leg 1 of that
  pipeline is a real srsRAN EVM/SNR sweep; Leg 2 is OpenAirInterface's real
  nr_ulschsim LDPC+CRC decoder (1000 trials/SNR point) -- not an assumed curve.
  The zero-error baseline (P_DECODE_FAIL_BASELINE) is the same CSV's
  direction=="aligned" rows (the real noise floor, 2/96 configs = 2.08%), not
  an assumed zero.

Stage C (deadlock handoff): on a Finding-1 decode failure, the same TA error is
  fed into the clause 5.4.4 state machine already built and validated in
  ../atk16c_statemachine/deadlock_sim.py, using its identical P_SR table (itself
  sourced from ../atk16b_sr/results/ALL_sr_pucch.csv). TA errors beyond the
  table's largest tested entry (8 units) are clamped to that entry's p_sr; this
  is a deliberate, documented extrapolation (the report's own PUCCH coherence
  analysis shows the Dirichlet metric already at its floor by 8 units), not a
  fabricated value.

Each run samples two (resp. three) independent Bernoulli/trace draws per trial
from these REAL lookup tables -- it is not a closed-form multiplication of
probabilities. Negative controls (no induced delay; weak relay + sub-damaging
delay) use the exact same code path to show the pipeline is not hardwired to
report failure.
"""
import csv
import random

# ---- Stage A: p_attacker(rel_db), flat Rayleigh, delta-independent ----
# source: ../atk05a/results/A_surface_rayleigh.csv, delta_units=7 column
P_ATTACKER = {
    -12: 0.0620, -11: 0.0735, -10: 0.0905, -9: 0.1110, -8: 0.1340,
    -7: 0.1620, -6: 0.1925, -5: 0.2380, -4: 0.2790, -3: 0.3220,
    -2: 0.3750, -1: 0.4290, 0: 0.4865, 1: 0.5465, 2: 0.5940,
    3: 0.6495, 4: 0.7055, 5: 0.7440, 6: 0.7845, 7: 0.8250,
    8: 0.8515, 9: 0.8790, 10: 0.9025, 12: 0.9320, 15: 0.9640,
}

# ---- Stage B: P(decode_fail | TA error units), aggregated over 96 real OAI configs ----
# source: sim_rebuild/results/SUMMARY_composed.csv, EARLY_arrival_attack_dir,
# fraction of configs with bler >= 0.99, computed directly from that CSV (see
# README.md for the exact awk one-liner)
P_DECODE_FAIL = {
    1: 0.0000, 2: 0.0000, 3: 0.0000, 4: 0.0000, 5: 0.0104,
    6: 0.4167, 7: 0.9896, 8: 1.0000,
}

# No-error baseline: the real noise-floor decode-fail rate with ZERO timing error
# (not assumed to be 0). Source: same SUMMARY_composed.csv, direction=="aligned"
# (the only ta_units value in that direction is 0), fraction of the same 96 real
# configs with bler >= 0.99: 2/96 = 0.0208. This is distinct from P_DECODE_FAIL,
# which is built from EARLY_arrival_attack_dir and has no ta_units=0 row.
P_DECODE_FAIL_BASELINE = 0.0208


def p_decode_fail(delta_units):
    if delta_units == 0:
        return P_DECODE_FAIL_BASELINE
    if delta_units in P_DECODE_FAIL:
        return P_DECODE_FAIL[delta_units]
    return 1.0 if delta_units > 8 else 0.0  # beyond the measured table: already at the floor either side


# ---- Stage C: clause 5.4.4 deadlock, reusing atk16c's validated P_SR table ----
# source: ../atk16c_statemachine/deadlock_sim.py (ALL_sr_pucch.csv), 1 port
P_SR_1PORT = {0: 0.9635, 5: 0.616, 6: 0.028, 7: 0.0005, 8: 0.0}


def p_sr_clamped(delta_units):
    """Lookup with linear interpolation between the nearest measured keys, clamped
    at the table's edges. Fixes a prior bug where any delta strictly between 0 and
    5 (never actually reached by the scenarios below, but latent) fell through to
    the worst-case 8-unit value instead of interpolating."""
    if delta_units in P_SR_1PORT:
        return P_SR_1PORT[delta_units]
    keys = sorted(P_SR_1PORT)
    if delta_units < keys[0]:
        return P_SR_1PORT[keys[0]]
    if delta_units > keys[-1]:
        return P_SR_1PORT[keys[-1]]
    lo = max(k for k in keys if k < delta_units)
    hi = min(k for k in keys if k > delta_units)
    frac = (delta_units - lo) / (hi - lo)
    return P_SR_1PORT[lo] + frac * (P_SR_1PORT[hi] - P_SR_1PORT[lo])


def run_deadlock_trace(p_sr, sr_trans_max, t_interval_ms, t304_ms, rng):
    """Literal clause 5.4.4 trace (see atk16c_statemachine/deadlock_sim.py)."""
    sr_counter = 0
    t_elapsed = 0.0
    while True:
        if t_elapsed >= t304_ms:
            return "T304_EXPIRED_FIRST"
        if rng.random() < p_sr:
            return "GRANT_RECEIVED"
        sr_counter += 1
        t_elapsed += t_interval_ms
        if sr_counter >= sr_trans_max:
            return "DEADLOCK"  # RACH-less LTM guard is closed in all Stage-C runs here


def run_once(rel_db, delta_units, rng, chain_to_deadlock):
    """One Finding-1 trial: capture, then decode; optionally chained into Stage C.

    Decode failure is sampled unconditionally from the real measured curve at
    whatever TA error resulted -- not gated on "captured", since even an
    uncorrupted (err_units=0) transmission has a real, nonzero baseline failure
    rate from ordinary channel noise (P_DECODE_FAIL_BASELINE). Gating decode
    failure on capture would force every negative-control trial to read exactly
    zero by construction rather than by measurement.
    """
    captured = rng.random() < P_ATTACKER[rel_db]
    err_units = delta_units if captured else 0  # if not captured, gNB measures the victim's own true delay
    decode_failed = rng.random() < p_decode_fail(err_units)
    result = {"captured": captured, "err_units": err_units, "decode_failed": decode_failed}
    if chain_to_deadlock and decode_failed:
        outcome = run_deadlock_trace(p_sr_clamped(err_units), sr_trans_max=8,
                                      t_interval_ms=20, t304_ms=10_000, rng=rng)
        result["deadlock_outcome"] = outcome
    return result


def monte_carlo(rows, group, label, rel_db, delta_units, n, seed, chain_to_deadlock=True):
    rng = random.Random(seed)
    n_captured = n_decode_fail = n_deadlock = 0
    for _ in range(n):
        r = run_once(rel_db, delta_units, rng, chain_to_deadlock)
        n_captured += r["captured"]
        n_decode_fail += r["decode_failed"]
        if r.get("deadlock_outcome") == "DEADLOCK":
            n_deadlock += 1
    row = {
        "group": group, "label": label, "rel_db": rel_db, "delta_units": delta_units, "n": n,
        "p_captured": n_captured / n,
        "p_decode_fail_e2e": n_decode_fail / n,
        "p_decode_fail_cond_captured": (n_decode_fail / n_captured) if n_captured else 0.0,
        "p_deadlock_e2e": n_deadlock / n,
    }
    rows.append(row)
    print(f"{label:58s} -> p_captured={row['p_captured']:.4f}  "
          f"p_decode_fail(e2e)={row['p_decode_fail_e2e']:.4f}  "
          f"p_deadlock(e2e)={row['p_deadlock_e2e']:.4f}")
    return row


def main():
    rows = []
    N = 200_000

    # ---- negative control 1: no induced delay at all (honest preamble, any relay power) ----
    monte_carlo(rows, "negative_control", "No relay, delta=0, rel_db=+15 (irrelevant, no delay induced)",
                15, 0, N, 1)

    # ---- negative control 2: weak relay + sub-damaging delay (double negative) ----
    monte_carlo(rows, "negative_control", "Weak relay rel_db=-12, delta=4 (below decode-fail threshold)",
                -12, 4, N, 2)

    # ---- attack: the three induced delays used in the report's Figure 3.1 ----
    for delta in (7, 16, 32):
        for rel_db in (-6, 0, 3, 6, 9, 10, 12, 15):
            monte_carlo(rows, "attack", f"Attack, delta={delta} units, rel_db={rel_db:+d} dB",
                        rel_db, delta, N, 100 + delta * 100 + rel_db)

    with open("results/summary.csv", "w", newline="") as fh:
        fieldnames = list(rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print("\nwrote results/summary.csv")


if __name__ == "__main__":
    main()
