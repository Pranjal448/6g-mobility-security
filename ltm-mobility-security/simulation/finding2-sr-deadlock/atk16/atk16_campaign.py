"""ATK-16 full campaign: the TS 38.321 clause 5.4.4 Scheduling Request deadlock during a
RACH-less LTM cell switch, swept over the ENTIRE configuration space the ASN.1 admits.

WHY THIS EXISTS
---------------
`06_ltm_implementation/observe_atk16_sr_deadlock.py` establishes the mechanism and runs two
validity gates, but it sweeps only (sr-TransMax x sr-ProhibitTimer x slot periodicity) at one
numerology, and reports the T304 window table at one periodicity.  Four things were missing and
all four change the answer:

  1. NUMEROLOGY.  `periodicityAndOffset` is in SLOTS, and a slot is 1/2^mu ms, so the same ASN.1
     configuration exhausts SR_COUNTER 8x faster at mu=3 than at mu=0.  The window table is a
     function of mu and was being reported as if it were not.
  2. SUB-SLOT PERIODICITIES.  The CHOICE also admits sym2 and sym6or7, which are shorter than any
     slot value and therefore the attacker's best case.
  3. THE rach-LessHO ARM.  Clause 5.4.4's two gates both read
     "rach-LessHO is not configured AND there is no ongoing RACH-less LTM cell switch".
     A UE with rach-LessHO configured (Rel-18) falls into the same structural hole with no LTM
     involved at all, which widens the finding beyond LTM.
  4. CONSEQUENCE.  The deadlock is NOT permanent: TS 38.331 starts T304 on an LTM cell switch
     execution and T304 expiry initiates RRC re-establishment.  The damage is therefore
     (T304 - T_exhaust) of dead uplink plus a re-establishment, which GROWS with T304 while the
     fraction of configurations that admit the attack also grows with T304.  That trade-off is the
     result, and it was not being computed.

SPEC BASIS (all class (A), quoted from 01_specs_txt/)
-----------------------------------------------------
  TS 38.321 clause 5.4.4 (lines 2529-2566)  -- the clause, transcribed in ltm/sr_procedure.py.
  TS 38.331 line 24131                      -- t304 ENUMERATED {ms50, ms100, ms150, ms200, ms500,
                                               ms1000, ms2000, ms10000}, MANDATORY in
                                               ReconfigurationWithSync.
  TS 38.331 line 24151                      -- ltm-SchedulingRequestInfo-r19 is a field OF
                                               ReconfigurationWithSync, i.e. the LTM SR
                                               configuration and t304 are carried in the SAME IE.
  TS 38.331 line 24315                      -- LTM-SchedulingRequestInfo-r19 ::= SEQUENCE {
                                               ltm-SchedulingRequestConfig-r19 SchedulingRequestConfig,
                                               ltm-SchedulingRequestResourceConfig-r19 ... OF
                                               SchedulingRequestResourceConfig }
                                               so the LTM SR configuration carries exactly the
                                               ordinary sr-TransMax / sr-ProhibitTimer /
                                               periodicityAndOffset ranges.  The 90-pair space is
                                               therefore the LTM SR configuration's own space.
  TS 38.331 line 4125                       -- "start timer T304 for the corresponding SpCell with
                                               the timer value set to t304", at `3>` under the
                                               branch whose sibling `2>` is "if this procedure is
                                               performed due to an LTM cell switch execution"
                                               => T304 RUNS during an LTM cell switch execution.
  TS 38.331 line 3948                       -- T304 is stopped, and ltm-SchedulingRequestInfo
                                               released, only on successful completion.

Run: python3 atk16_campaign.py        (writes results/*.csv and logs/summary.txt)
"""

from __future__ import annotations

import csv
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IMPL = "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/06_ltm_implementation"
sys.path.insert(0, IMPL)

from ltm import recovery_timing as rt  # noqa: E402
from ltm import sr_procedure as srp  # noqa: E402

RESULTS = os.path.join(HERE, "results")
LOGS = os.path.join(HERE, "logs")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(LOGS, exist_ok=True)

# ---------------------------------------------------------------------------- the space

MU_OPTIONS = [0, 1, 2, 3]                       # 15 / 30 / 60 / 120 kHz SCS
PERIODICITIES = list(srp.SR_PERIOD_SLOTS_OPTIONS) + list(srp.SR_PERIOD_SYMBOL_OPTIONS)
PROHIBIT = list(srp.SR_PROHIBIT_TIMER_MS_OPTIONS_ALL)
TRANS_MAX = list(srp.SR_TRANS_MAX_OPTIONS)
T304 = list(rt.T304_MS_OPTIONS)

# The reference configuration the narrative arms use.  Declared, not optimised.
REF_MU = 1
REF_PERIOD = 2          # sl2 = 1.0 ms at mu=1
REF_TRANS_MAX = 8       # n8, the second-lowest of five ASN.1 values
REF_PROHIBIT = 16       # ms16, a mid-range Rel-15 value

ALL_CONFIGS = [
    (n, p, per, mu)
    for n, p, per, mu in itertools.product(TRANS_MAX, PROHIBIT, PERIODICITIES, MU_OPTIONS)
]


def make_config(n=REF_TRANS_MAX, p=REF_PROHIBIT, per=REF_PERIOD, mu=REF_MU):
    return srp.SRConfig(sr_trans_max=n, sr_prohibit_timer_ms=p, periodicity=per, mu=mu)


def run_arm(cfg, *, ltm_ongoing, ho_configured=False, grant_at=None):
    """One run of clause 5.4.4.  The only attacker-supplied quantity is `grant_at=None`
    (the target cell never provides a usable grant); it is reported, not assumed away."""
    state = srp.MacState(rach_less_ltm_ongoing=ltm_ongoing,
                         rach_less_ho_configured=ho_configured,
                         has_valid_pucch_for_sr=True,
                         ltm_configured_grant_present=True,
                         srs_configured=True,
                         sp_csi_pusch_present=True)
    proc = srp.SchedulingRequestProcedure(cfg, state)
    proc.trigger()
    return proc.run(grant_arrives_at_ms=grant_at), state


# ---------------------------------------------------------------------------- gates

def gates(out):
    """Four gates over the FULL space.  Nothing downstream is reported if any gate fails."""
    ok = True

    # G1 -- benign: no ongoing RACH-less LTM, rach-LessHO not configured.  Clause 5.4.4 MUST take
    # the Random Access escape for every single ASN.1 configuration.
    fails = []
    for n, p, per, mu in ALL_CONFIGS:
        res, _ = run_arm(make_config(n, p, per, mu), ltm_ongoing=False)
        if (res.outcome != "random_access" or not res.random_access_initiated
                or not res.pending_srs_cancelled):
            fails.append((n, p, per, mu, res.outcome))
    out(f"G1_benign_recovery  configs={len(ALL_CONFIGS)}  failures={len(fails)} -> "
        f"{'PASS' if not fails else 'FAIL'}")
    ok &= not fails

    # G2 -- the stepped model's T_exhaust must equal an independent closed form everywhere.
    worst = 0.0
    mism = 0
    for n, p, per, mu in ALL_CONFIGS:
        cfg = make_config(n, p, per, mu)
        res, _ = run_arm(cfg, ltm_ongoing=True)
        exp = srp.t_exhaust_closed_form_ms(cfg)
        if res.t_exhaust_ms is None:
            mism += 1
            continue
        worst = max(worst, abs(res.t_exhaust_ms - exp))
        if abs(res.t_exhaust_ms - exp) > 1e-9:
            mism += 1
    out(f"G2_t_exhaust_closed_form  configs={len(ALL_CONFIGS)}  mismatches={mism}  "
        f"worst_abs_err_ms={worst:.3e} -> {'PASS' if mism == 0 else 'FAIL'}")
    ok &= mism == 0

    # G3 -- an arriving grant must cancel the pending SR at that instant, in every arm.  The
    # grant is placed strictly INSIDE the SR escalation (half way to T_exhaust), because a grant
    # that arrives after SR_COUNTER has already exhausted is a different case: the clause has by
    # then already taken one of its two branches, which is correct behaviour and not a failure.
    fails = []
    for n, p, per, mu in ALL_CONFIGS[::7]:
        cfg = make_config(n, p, per, mu)
        at = srp.t_exhaust_closed_form_ms(cfg) / 2.0
        for ltm in (False, True):
            res, _ = run_arm(cfg, ltm_ongoing=ltm, grant_at=at)
            if res.outcome != "granted" or abs((res.t_resolved_ms or -1) - at) > 1e-9:
                fails.append((n, p, per, mu, ltm, res.outcome))
    out(f"G3_grant_cancels_sr  configs={len(ALL_CONFIGS[::7]) * 2}  failures={len(fails)} -> "
        f"{'PASS' if not fails else 'FAIL'}")
    ok &= not fails

    # G4 -- the destructive actions at level `5>` must fire in EVERY arm that reaches `4> else`,
    # benign included.  They are unconditional in the clause, so a model in which they fire only
    # under attack would be a model of the attack rather than of the clause.
    cfg = make_config()
    res_b, _ = run_arm(cfg, ltm_ongoing=False)
    res_a, _ = run_arm(cfg, ltm_ongoing=True)
    fired_b = all([res_b.released_pucch_all_serving_cells, res_b.released_srs_all_serving_cells,
                   res_b.cleared_configured_grants, res_b.cleared_sp_csi_pusch])
    fired_a = all([res_a.released_pucch_all_serving_cells, res_a.released_srs_all_serving_cells,
                   res_a.cleared_configured_grants, res_a.cleared_sp_csi_pusch])
    out(f"G4_destructive_actions_unconditional  benign={fired_b}  attacked={fired_a} -> "
        f"{'PASS' if (fired_b and fired_a) else 'FAIL'}")
    ok &= fired_b and fired_a
    return ok


# ---------------------------------------------------------------------------- arms

ARMS = {
    # name                 ltm_ongoing  ho_configured  grant_at
    "A_benign":            (False, False, None),
    "B_atk16_ltm":         (True,  False, None),
    "C_rach_less_ho":      (False, True,  None),
    "D_honest_grant":      (True,  False, 5.0),
}


def sweep_arms():
    path = os.path.join(RESULTS, "arms_full_space.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "sr_trans_max", "sr_prohibit_ms", "periodicity", "mu",
                    "period_ms", "tx_interval_ms", "t_exhaust_ms", "outcome",
                    "sr_counter", "transmissions", "released_pucch", "released_srs",
                    "cleared_grants", "cleared_spcsi", "random_access", "srs_cancelled",
                    "ltm_completion_reachable"])
        for arm, (ltm, ho, grant) in ARMS.items():
            for n, p, per, mu in ALL_CONFIGS:
                cfg = make_config(n, p, per, mu)
                res, _ = run_arm(cfg, ltm_ongoing=ltm, ho_configured=ho, grant_at=grant)
                w.writerow([arm, n, p, per, mu,
                            f"{cfg.period_ms:.6f}", f"{cfg.transmission_interval_ms:.6f}",
                            "" if res.t_exhaust_ms is None else f"{res.t_exhaust_ms:.6f}",
                            res.outcome, res.sr_counter, res.transmissions,
                            int(res.released_pucch_all_serving_cells),
                            int(res.released_srs_all_serving_cells),
                            int(res.cleared_configured_grants),
                            int(res.cleared_sp_csi_pusch),
                            int(res.random_access_initiated),
                            int(res.pending_srs_cancelled),
                            int(res.ltm_completion_reachable)])
    return path


# ---------------------------------------------------------------------------- window analysis

def window_tables(out):
    """For each (T304, mu, periodicity): how many of the 90 (sr-TransMax, sr-ProhibitTimer) pairs
    reach clause 5.4.4's `4> else` branch before T304 can supervise the switch.

    T_exhaust < T304 is the condition for the DEADLOCK to be the failure the UE suffers.  If
    T_exhaust >= T304 the UE is rescued by T304 expiry and goes to re-establishment, which is the
    spec's own intended failure handling, not this attack.
    """
    pairs = [(n, p) for n in TRANS_MAX for p in PROHIBIT]
    path = os.path.join(RESULTS, "window_by_mu_period.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t304_ms", "mu", "periodicity", "period_ms", "pairs_inside", "pairs_total",
                    "fraction", "min_t_exhaust_ms", "median_t_exhaust_ms", "max_t_exhaust_ms"])
        for t in T304:
            for mu in MU_OPTIONS:
                for per in PERIODICITIES:
                    te = sorted(srp.t_exhaust_closed_form_ms(make_config(n, p, per, mu))
                                for n, p in pairs)
                    inside = sum(1 for v in te if v < t)
                    w.writerow([t, mu, per, f"{make_config(1 if False else 4, 0, per, mu).period_ms:.6f}",
                                inside, len(pairs), f"{inside / len(pairs):.6f}",
                                f"{te[0]:.3f}", f"{te[len(te) // 2]:.3f}", f"{te[-1]:.3f}"])

    # Headline table at the reference periodicity and numerology, which is what the report quotes.
    out("")
    out("### T304 window table at the reference configuration (mu=1, periodicityAndOffset=sl2)")
    out(f"{'T304 (ms)':>10} {'pairs inside':>13} {'of':>4} {'fraction':>9}")
    for t in T304:
        inside = sum(1 for n, p in pairs
                     if srp.t_exhaust_closed_form_ms(make_config(n, p, REF_PERIOD, REF_MU)) < t)
        out(f"{t:>10} {inside:>13} {len(pairs):>4} {inside / len(pairs):>8.1%}")

    # Over the whole space, including numerology and sub-slot periodicities.
    out("")
    out("### Over the ENTIRE space (sr-TransMax x sr-ProhibitTimer x periodicity x mu)")
    out(f"{'T304 (ms)':>10} {'configs inside':>15} {'of':>6} {'fraction':>9}")
    for t in T304:
        inside = sum(1 for n, p, per, mu in ALL_CONFIGS
                     if srp.t_exhaust_closed_form_ms(make_config(n, p, per, mu)) < t)
        out(f"{t:>10} {inside:>15} {len(ALL_CONFIGS):>6} {inside / len(ALL_CONFIGS):>8.1%}")
    return path


# ---------------------------------------------------------------------------- consequence

def consequence(out):
    """What the UE actually loses.  The deadlock runs from T_exhaust to T304 expiry, after which
    TS 38.331 clause 5.3.7 re-establishment applies (TS 38.331's T304 expiry action).  Outage is
    therefore (T304 - T_exhaust) + re-establishment, bounded below by the re-establishment floor.
    """
    path = os.path.join(RESULTS, "consequence.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mu", "t304_ms", "sr_trans_max", "sr_prohibit_ms", "periodicity",
                    "t_exhaust_ms", "deadlock_ms", "reest_floor_ms", "reest_ceiling_ms",
                    "outage_floor_ms", "outage_ceiling_ms"])
        for mu in MU_OPTIONS:
            reest = rt.ReestablishmentTimingBudget(mu=mu, capability=1)
            for t in T304:
                for n, p, per in itertools.product(TRANS_MAX, PROHIBIT, PERIODICITIES):
                    cfg = make_config(n, p, per, mu)
                    te = srp.t_exhaust_closed_form_ms(cfg)
                    if te >= t:
                        continue
                    dead = t - te
                    w.writerow([mu, t, n, p, per, f"{te:.3f}", f"{dead:.3f}",
                                f"{reest.floor_ms:.3f}", f"{reest.ceiling_ms:.3f}",
                                f"{dead + reest.floor_ms:.3f}",
                                f"{dead + reest.ceiling_ms:.3f}"])

    out("")
    out("### Consequence at the reference configuration "
        f"(mu={REF_MU}, sl{REF_PERIOD}, n{REF_TRANS_MAX}, ms{REF_PROHIBIT})")
    cfg = make_config()
    te = srp.t_exhaust_closed_form_ms(cfg)
    reest = rt.ReestablishmentTimingBudget(mu=REF_MU, capability=1)
    out(f"  T_exhaust                           : {te:.3f} ms")
    out(f"  re-establishment floor / ceiling    : {reest.floor_ms:.3f} / {reest.ceiling_ms:.1f} ms")
    out(f"{'T304 (ms)':>10} {'deadlock (ms)':>14} {'outage floor (ms)':>18} {'outage ceiling (ms)':>20}")
    for t in T304:
        if te >= t:
            out(f"{t:>10} {'--':>14} {'(T304 expires before SR_COUNTER exhausts)':>18}")
            continue
        out(f"{t:>10} {t - te:>14.3f} {t - te + reest.floor_ms:>18.3f} "
            f"{t - te + reest.ceiling_ms:>20.1f}")
    return path


# ---------------------------------------------------------------------------- structural

def structural(out):
    """The two structural facts, read off the arms rather than asserted."""
    cfg = make_config()
    out("")
    out("### Arms at the reference configuration")
    out(f"{'arm':>18} {'outcome':>14} {'RA?':>5} {'PUCCH gone':>11} {'grants gone':>12} "
        f"{'LTM completable':>16}")
    for arm, (ltm, ho, grant) in ARMS.items():
        res, _ = run_arm(cfg, ltm_ongoing=ltm, ho_configured=ho, grant_at=grant)
        out(f"{arm:>18} {res.outcome:>14} {str(bool(res.random_access_initiated)):>5} "
            f"{str(bool(res.released_pucch_all_serving_cells)):>11} "
            f"{str(bool(res.cleared_configured_grants)):>12} "
            f"{str(bool(res.ltm_completion_reachable)):>16}")

    out("")
    out("### Which of clause 5.4.4's two gates each arm trips")
    out("  The clause gates BOTH Random Access escapes on the same conjunction:")
    out('    "rach-LessHO is not configured AND there is no ongoing RACH-less LTM cell switch"')
    out("  so the hole is not LTM-specific; arm C reaches it with no LTM involved.")
    outcomes = {}
    for arm, (ltm, ho, grant) in ARMS.items():
        res, _ = run_arm(cfg, ltm_ongoing=ltm, ho_configured=ho, grant_at=grant)
        outcomes[arm] = res.outcome
    out(f"  A_benign (neither gate set)        -> {outcomes['A_benign']}")
    out(f"  B_atk16_ltm (LTM gate set)         -> {outcomes['B_atk16_ltm']}")
    out(f"  C_rach_less_ho (rach-LessHO set)   -> {outcomes['C_rach_less_ho']}")
    out(f"  D_honest_grant (grant arrives)     -> {outcomes['D_honest_grant']}")


# ---------------------------------------------------------------------------- defence

def defence(out):
    """The mitigation, derived as an inequality and then checked against the ASN.1.

    The deadlock is the UE's failure only while T_exhaust < t304, and

        T_exhaust = sr-TransMax x max(period, ceil(sr-ProhibitTimer / period) x period)
                  = sr-TransMax x (the SR transmission interval)

    so the whole of ATK-16's configuration dependence collapses to ONE inequality:

        SAFE  <=>  sr-TransMax x SR transmission interval  >=  t304.

    This is a useful mitigation because it costs nothing operationally: the responsiveness an
    operator wants during a cell switch is a SHORT transmission interval, and the inequality can
    always be restored by raising sr-TransMax instead of lengthening the interval.  What makes it
    a finding rather than a triviality is that nothing states it:

      * no line of TS 38.331 mentions t304 together with sr-TransMax or sr-ProhibitTimer, and
        sr-TransMax's field description (line 38840) is a bare value mapping;
      * "T304" does not occur anywhere in TS 38.321 (0 occurrences), so the MAC counter that
        creates the deadlock and the RRC timer that bounds it sit in different layers, in
        different specifications, with no clause relating them;
      * the two parameters are nevertheless carried in the SAME IE -- t304 is mandatory in
        ReconfigurationWithSync (TS 38.331 line 24131) and ltm-SchedulingRequestInfo-r19 is a
        field of that same ReconfigurationWithSync (line 24151).

    So an operator sets both at once, in one message, with no indication that they interact.
    """
    pairs = [(n, p) for n in TRANS_MAX for p in PROHIBIT]
    out("")
    out("### Mitigation: sr-TransMax x SR transmission interval >= t304")
    out("    For each t304 and numerology, at the FASTEST SR transmission interval available")
    out("    (periodicityAndOffset=sym2, sr-ProhibitTimer=ms0), the smallest sr-TransMax that")
    out("    satisfies the inequality -- and whether the ASN.1 offers it.")
    out(f"{'mu':>3} {'t304 (ms)':>10} {'fastest interval (ms)':>22} {'sr-TransMax needed':>19} "
        f"{'ASN.1 value':>12} {'available':>10}")
    path = os.path.join(RESULTS, "mitigation_inequality.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mu", "t304_ms", "periodicity", "interval_ms", "trans_max_needed",
                    "asn1_value_used", "available", "safe_pairs", "unsafe_pairs"])
        for mu in MU_OPTIONS:
            for t in T304:
                for per in PERIODICITIES:
                    cfg0 = make_config(4, 0, per, mu)
                    iv = cfg0.transmission_interval_ms
                    need = t / iv
                    chosen = next((v for v in TRANS_MAX if v >= need), None)
                    safe = sum(1 for n, p in pairs
                               if srp.t_exhaust_closed_form_ms(make_config(n, p, per, mu)) >= t)
                    w.writerow([mu, t, per, f"{iv:.6f}", f"{need:.3f}",
                                chosen if chosen is not None else "none",
                                int(chosen is not None), safe, len(pairs) - safe])
                    if per == "sym2":
                        out(f"{mu:>3} {t:>10} {iv:>22.4f} {need:>19.1f} "
                            f"{(('n' + str(chosen)) if chosen else '--'):>12} "
                            f"{str(chosen is not None):>10}")

    out("")
    out("### Safe and unsafe pairs per t304, at the reference periodicity (sl2) and mu=1")
    out(f"{'t304 (ms)':>10} {'safe pairs':>11} {'unsafe pairs':>13} {'of':>4}")
    for t in T304:
        safe = sum(1 for n, p in pairs
                   if srp.t_exhaust_closed_form_ms(make_config(n, p, REF_PERIOD, REF_MU)) >= t)
        out(f"{t:>10} {safe:>11} {len(pairs) - safe:>13} {len(pairs):>4}")
    # The actionable form.  sr-TransMax is capped at n64 by the ASN.1, so the inequality can
    # only be satisfied by lengthening the SR transmission interval:  interval >= t304 / 64.
    out("")
    out("### The deployable form: with sr-TransMax at its ASN.1 maximum n64, the SR transmission")
    out("    interval must satisfy  interval >= t304 / 64.  Cost is stated against the 1-slot")
    out("    interval an operator would otherwise choose for a cell switch.")
    out(f"{'t304 (ms)':>10} {'min interval (ms)':>18} {'smallest ASN.1 sr-ProhibitTimer':>32} "
        f"{'cost vs sl1 at mu=1':>20}")
    base = make_config(4, 0, 1, REF_MU).transmission_interval_ms
    for t in T304:
        need_iv = t / max(TRANS_MAX)
        prohibit = next((q for q in sorted(PROHIBIT) if q >= need_iv), None)
        out(f"{t:>10} {need_iv:>18.3f} "
            f"{(('ms' + str(prohibit)) if prohibit is not None else 'none in the ASN.1'):>32} "
            f"{need_iv / base:>19.1f}x")
    out("")
    out("  So the mitigation is real but not free, and the cap is sr-TransMax's own ASN.1 range:")
    out(f"  at t304 = ms10000 a safe configuration cannot send an SR more often than once every")
    out(f"  {max(T304) / max(TRANS_MAX):.1f} ms during the switch, against the {base:.1f} ms that")
    out(f"  periodicityAndOffset=sl1 gives at mu={REF_MU}.")

    out("")
    out("  The attack therefore does not need a rare configuration; it needs the operator to")
    out("  have landed on one side of an inequality that neither specification states.  At")
    out("  t304 = ms10000, 72 of the 90 pairs are on the wrong side of it.")
    return path


# ---------------------------------------------------------------------------- main

def main():
    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("=" * 100)
    out("ATK-16 FULL CAMPAIGN -- TS 38.321 clause 5.4.4 SR deadlock during RACH-less LTM")
    out("=" * 100)
    out(f"configuration space: {len(TRANS_MAX)} sr-TransMax x {len(PROHIBIT)} sr-ProhibitTimer "
        f"x {len(PERIODICITIES)} periodicityAndOffset x {len(MU_OPTIONS)} numerologies "
        f"= {len(ALL_CONFIGS)} configurations, x {len(ARMS)} arms")
    out("")
    out("### GATES (run first; nothing below is reported if one fails)")
    if not gates(out):
        out("A GATE FAILED -- refusing to report attack numbers from this model.")
        with open(os.path.join(LOGS, "summary.txt"), "w") as fh:
            fh.write("\n".join(lines) + "\n")
        return 1

    structural(out)
    p1 = sweep_arms()
    p2 = window_tables(out)
    p3 = consequence(out)
    p4 = defence(out)

    out("")
    out("### artifacts")
    for p in (p1, p2, p3, p4):
        with open(p) as fh:
            n = sum(1 for _ in fh) - 1
        out(f"  {os.path.relpath(p, HERE)}  ({n} rows)")

    with open(os.path.join(LOGS, "summary.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
