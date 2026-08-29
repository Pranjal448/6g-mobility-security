# Attack-model spec, extracted from /home/pranjal/6g_new_thesis.pdf

Source thesis: "Detecting Forged Handovers — a measured attack on the 6G L2 cell-switch
command, and a non-cryptographic RAN-side detection-and-localization defence."

**SCOPE OF THIS IMPLEMENTATION: ATTACK MODEL ONLY (thesis Chapters 3, 4, 5).**
The detection/localization defence (thesis Chapters 6 and 7 — adaptive-threshold per-UE
detector, ML attacker-localiser) is explicitly OUT OF SCOPE for now. Do not implement it.
Only build the attack + its measurement in ns-3.

## 1. The vulnerability (why the attack works)

In 5G-Advanced/6G, **Lower-layer Triggered Mobility (LTM)** delivers the cell-switch command
as a MAC Control Element (MAC CE) — a Layer-2 frame below PDCP, so it carries **no integrity
protection and no ciphering** (classical RRC-commanded handover is PDCP-integrity-stamped;
LTM trades that protection for latency). The UE applies the switch **before HARQ
confirmation** (no round trip). It is unicast (no quorum to break), below PDCP (nothing to
decrypt), unverified (nothing to fail).

## 2. Threat model

- **Attacker capability**: a commodity SDR (srsRAN/Amarisoft-class) that can decode the
  downlink control channel in real time and inject a symbol-synchronised,
  cyclic-prefix-aligned frame a few dB above the legitimate signal (capture effect, not a
  power race). No keys, no core access, no node compromise.
- **Position**: co-located with the victim UE (angularly identical, defeats beam separation)
  or on a wider control-channel beam.
- **Goal**: targeted, stealthy, single-UE denial-of-service — force one UE to mis-switch to a
  wrong/non-existent cell, causing radio-link failure (RLF) and RRC re-establishment, an
  interruption far above the ~0 ms intra-BS LTM budget — without the mass-RACH-failure
  footprint that aggregate detectors would catch.

## 3. Attack, stage by stage

1. **Reconnaissance** — survey the target route; place the SDR at a handover region (cell
   edges follow AP/gNB placement).
2. **Target lock** — re-identify the victim's current C-RNTI.
3. **Reactive monitoring** — continuously blind-decode the PDCCH for that RNTI; react to a
   real grant rather than precomputing timing.
4. **Trigger (optional, strongest variant)** — degrade/spoof the serving beam so the network
   itself issues a real LTM command on cue (a known moment to overshadow).
5. **Inject** — within the same subframe, overshadow the legitimate LTM cell-switch MAC CE
   with a forged or replayed one carrying a **spoofed Target Configuration ID** (wrong or
   non-existent target cell). No keys, no decryption needed. The UE, acting before HARQ
   confirmation, applies the switch.

**Outcome to quantify**: mis-switch → radio-link failure → RRC re-establishment → DoS
interruption, throughput collapse and packet loss on the victim bearer.

## 4. Two-tier simulation design (as specified by the thesis)

- **Link tier** (MATLAB in the thesis — *not required for this implementation*; instead,
  use the thesis's own precomputed link-tier output as an input table, see §6 below): models
  the overshadow/capture step and produces **forgery-decode success probability vs
  attacker-to-legitimate power margin (dB)**.
- **System tier — this is what you build, in ns-3 with the 5G-LENA `nr` module.** Models the
  multi-cell mobility scenario, an LTM-style fast intra-frequency cell switch (**approximate
  it as a MAC-triggered handover**, since ns-3 has no native LTM/6G — this proxy is explicitly
  sanctioned by the thesis as long as you state it as a modelling boundary). The attack is
  injected at the MAC/RRC level as a spurious/forged cell-switch command whose *success* is
  drawn probabilistically from the link-tier margin→probability table (§6). ns-3 injects the
  *consequence* (a forged command that lands with that probability) — it does not simulate
  the RF capture effect itself.

**State these two modelling boundaries explicitly in your own docs/README, mirroring the
thesis:**
1. 6G is not in ns-3 — NR (5G-LENA) with a fast MAC-triggered handover approximates the LTM
   cell-switch MAC CE trigger, which is the actual attack surface.
2. The RF capture effect is not simulated — it enters ns-3 only as a per-attempt success
   probability (from the table below); ns-3 models the mobility/DoS consequence, not the RF.

## 5. Scenario and parameters (baseline values; sweep where noted)

| Parameter | Value |
|---|---|
| Deployment | Urban grid, 250 m inter-site distance, 4 GHz |
| Cells | 7–19 gNBs (sweep) |
| UEs | 50–300 (traffic-density sweep) |
| UE mobility | 3 / 30 / 60 / 120 km/h |
| Attackers | 1 → 10 overshadowing sources (attacker-density sweep) |
| Overshadow margin | 0 → 8 dB (link-level sweep, see table below) |
| Time-to-trigger | 320 ms |
| Runs | ≥ 100 seeds per operating point; report mean ± 95% CI (reduce if computationally infeasible, but document the reduction and why) |

## 6. Link-tier input table (use directly — do not re-derive via MATLAB)

Capture-effect forgery success probability vs attacker power margin (from thesis's
seed-fixed Monte-Carlo model, 200k trials, Rayleigh fading + 4 dB log-normal shadowing, 3 dB
decode threshold). Use this as a lookup/interpolation table to decide, per attack attempt, at
a given configured margin, whether the forged command "lands":

| margin (dB) | 0 | 1 | 2 | 3 | 4 | 6 | 8 |
|---|---|---|---|---|---|---|---|
| P(forge decode) | 0.37 | 0.42 | 0.46 | 0.50 | 0.54 | 0.63 | 0.71 |

**Important — sweep design**: run these as **one-factor-at-a-time sweeps around a single
baseline operating point**, not a full factorial cross-product (which would be
computationally infeasible: 19 cells x 300 UEs x 10 attackers x 7 margins x 4 speeds x 100
seeds is not tractable and is not what the thesis does). Baseline operating point: 60 km/h,
1 attacker, ~12 cells, ~150 UEs, margin swept 0-8dB for the headline result. Then vary one
axis at a time (attacker count 1-10 at fixed margin/speed/density; margin 0-8dB at fixed
speed/density; speed 3/30/60/120 at fixed margin/density; density low/medium/high at fixed
margin/speed) holding the others at baseline. This mirrors how the thesis itself reports
separate tables per axis.

## 7. Metrics to measure (attack side — this is the full metric set required)

- **Mobility interruption time (ms)** — primary KPI. Compare against the intra-BS ~0 ms LTM
  target (baseline, no attack) vs the forged-switch case.
- **Radio-link-failure (RLF) rate** and **handover-failure rate** — victim and neighbourhood.
- **Downlink/uplink throughput (Mbps)** on the victim bearer, and **packet-loss %**.
- **Ping-pong rate** and **short-time-of-stay rate** — separates attack-induced churn from
  benign mobility churn.
- **Attack success probability vs overshadow margin** (should reproduce/track the input
  table in §6 through the sweep).

## 8. Sanity targets from the thesis's own (pre-ns-3) analytical/Monte-Carlo model

These are NOT ground truth to force-fit, but the qualitative shape your ns-3 results should
resemble (thesis explicitly says these are to be *validated*, i.e. reproduced independently,
in ns-3 — exact numbers will differ because ns-3 is a different, more detailed model):

At 60 km/h, 1 attacker:

| Metric | No attack (intra-BS) | Forged switch | Change |
|---|---|---|---|
| Mean interruption (ms) | 1.3 | 294.9 | ~221x |
| Median interruption (ms) | 1.3 | 177.1 | ~136x |
| 95th-percentile (ms) | 2.5 | 1052.7 | ~421x |

The qualitative result you're reproducing: LTM's near-zero intra-BS interruption collapses
into a two-to-three-order-of-magnitude DoS outage under a single forged switch. Getting the
exact numbers is not required; showing this qualitative, large, statistically clear
inflation (with mean ± 95% CI across seeds) is the actual deliverable.

## 9. Explicitly out of scope for this implementation

- Ch. 6 (RAN-side per-UE detection layer / adaptive-threshold detector)
- Ch. 7 (ML attacker-localiser, kNN/DT/RF/LR/NB + stacking, defence evaluation)
- MATLAB 5G Toolbox link-tier simulation (use the precomputed table in §6 instead)
- SDR bench validation
- Any cryptographic defence

## 10. Tooling

- ns-3 (recent release, e.g. ns-3.40+) + the 5G-LENA `nr` contrib module (CTTC,
  https://gitlab.com/cttc-lena/nr — check its README for the ns-3 version it targets and
  match versions).
- Python 3 for sweep orchestration / results aggregation / plotting (matplotlib, pandas,
  numpy — fine to pip install).
- All work lives under /run/media/pranjal/hdd/mtp/ (this is a 1TB HDD, disk space is not a
  concern).
