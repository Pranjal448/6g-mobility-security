# atk05c_e2e

End-to-end simulation of Finding 1 (corrupted early timing advance), closing the
gap between "the relay captures the preamble" (atk05a, real srsRAN PRACH detector)
and "therefore the uplink transport block fails to decode" (sim_rebuild, real OAI
nr_ulschsim LDPC+CRC decoder) -- previously evaluated only as two separate
standalone campaigns, never chained as one pipeline. Also chains a Finding-1
decode failure into Finding 2's already-validated clause 5.4.4 state machine
(atk16c_statemachine/deadlock_sim.py) to simulate the full capture -> TA
corruption -> decode failure -> SR deadlock handoff.

## Data sources (no fabricated or hand-tuned probabilities)

- **Stage A, capture**: `../atk05a/results/A_surface_rayleigh.csv`, column
  `p_attacker` at `delta_units=7` (confirmed delta-independent: the 7/16/32-unit
  columns overlay to within simulation noise). This is the identical curve
  plotted in the report's own Figure 3.1 (`figsrc/fig_atk05a_capture.py`).
- **Stage B, decode**: `../../08_final_factcheck/sim_rebuild/results/SUMMARY_composed.csv`,
  filtered to `direction=="EARLY_arrival_attack_dir"`, aggregated as the fraction
  of all 96 real measured configurations (4 MCS x 2 window offsets x 3
  numerologies x 2 delay profiles x 2 delay spreads) with `bler >= 0.99` at each
  `ta_units`. Computed directly from the CSV:
  ```
  awk -F, '$10=="EARLY_arrival_attack_dir"{n[$8]++; if($15+0>=0.99) f[$8]++}
           END{for(k in n) printf "%s %d/%d %.4f\n", k, f[k], n[k], f[k]/n[k]}' \
      SUMMARY_composed.csv | sort -k1,1n
  ```
  Result: 0% at 1-4 units, 1.0% at 5, 41.7% at 6, 98.96% at 7, 100% at >=8 --
  consistent with the report's existing "6-8 units, median 7" boundary claim.
  Leg 1 of that composed table is a real srsRAN-based EVM/SNR sweep; Leg 2 is
  OpenAirInterface's real `nr_ulschsim` binary (1000 trials/SNR point) -- an
  actual LDPC encode/decode/CRC-check chain, not a modeled curve.
- **Zero-error baseline**: the same `SUMMARY_composed.csv`, `direction=="aligned"`
  (the only `ta_units` value present there is 0), gives 2/96 = 2.08% real
  configs with `bler >= 0.99` even with perfect timing. `p_decode_fail(0)` uses
  this real noise floor rather than an assumed zero -- an earlier version of
  this script forced the zero-error case to read exactly 0% by construction;
  that was a genuine negative-control weakness (caught in review) and is fixed
  here.
- **Stage C, deadlock handoff**: reuses `../atk16c_statemachine/deadlock_sim.py`'s
  `P_SR` table (1-port) verbatim, itself sourced from
  `../atk16b_sr/results/ALL_sr_pucch.csv`. TA errors beyond the table's largest
  tested entry (8 units) are clamped to that entry (documented in code): the
  report's own PUCCH coherence analysis shows the Dirichlet metric is already at
  its floor by 8 units, so this is a physically justified clamp, not an assumed
  value.

## Negative controls

Two, using the exact same capture/decode code path:

1. **No induced delay** (`delta_units=0`, any relay power): the relay can "win"
   the capture contest with probability up to 96%, but with no delay injected,
   the gNB reports the correct timing regardless. Decode failures track only the
   real 2.08% channel-noise floor (not zero), and 0 of 200,000 trials deadlock
   (consistent with the honest-UE rate of ~3e-12 reported elsewhere, below what
   200,000 trials can resolve).
2. **Weak relay + sub-damaging delay** (`rel_db=-12`, `delta_units=4`, which is
   below the 5-6 unit failure boundary measured in Stage B): capture succeeds in
   only 6.2% of trials, and even then the real composed BLER at 4 units is 0% --
   decode failures again track only the ~1.9% noise floor (since 93.8% of trials
   aren't captured at all and fall back to the same baseline), 0 deadlocks.

Both controls run through the identical `run_once()` path used by the attack
rows; nothing is special-cased to report success or failure. Neither control
reads exactly zero, which is the point: a control that is tautologically
guaranteed to read zero regardless of input is not actually testing anything.

## Sanity cross-check against the existing report figure

At `rel_db=+10 dB`, `delta_units=7`: simulated `p_captured=0.9025`, matching the
report's existing Figure 3.1 "+9.9 dB for 90%" annotation (linear interpolation
of the real capture table crosses 0.90 at rel_db ~= 9.86 dB). Simulated
`p_decode_fail(e2e)=0.8953` is within Monte Carlo noise of
`0.9025*0.9896 + (1-0.9025)*0.0208 = 0.8953` (capture-weighted mix of Stage B's
attack-direction curve and the real zero-error baseline), confirming the two
real datasets compose correctly when actually chained as sequential Bernoulli
draws per trial (not evaluated as a single closed-form product).

Run: `python3 e2e_sim.py` (stdlib only). Output: `results/summary.csv`.
