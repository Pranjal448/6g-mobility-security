# Implementation Plan — 6G LTM Forged-Handover ATTACK MODEL in ns-3 + 5G-LENA `nr`

Authoritative requirements: `THESIS_ATTACK_SPEC.md` (this repo).
**Scope: attack model + its measurement only (thesis Ch. 3–5). The detection/localization
defence (Ch. 6–7) is explicitly OUT OF SCOPE and will NOT be implemented.**

This is a living document. Steps are executed ONE AT A TIME under reviewer direction.
Deviations discovered during execution are recorded here (see "Deviations / decisions log"
at the bottom) and in `changes.txt`.

## Two modelling boundaries (stated up front, mirrored from the thesis, to be repeated in README)
- **B1 — 6G is not in ns-3.** NR (5G-LENA) with a *fast MAC-triggered handover* approximates
  the LTM cell-switch MAC CE trigger, which is the real attack surface. Sanctioned proxy.
- **B2 — RF capture effect is not simulated.** It enters ns-3 only as a per-attempt success
  probability drawn from the §6 margin→P(forge-decode) table. ns-3 models the mobility/DoS
  *consequence*, not the RF overshadow itself.

## Chosen versions (Step 1 outcome, may be revised if build fails)
- ns-3.48 + 5G-LENA `nr` v5.1 (README pairs v5.1 ↔ ns-3.48). Toolchain: g++ 15, cmake 4.2,
  Python 3.14, 8 cores / 14 GB RAM. All under `/run/media/pranjal/hdd/mtp/`.

---

## Steps

1. **Toolchain + environment setup.** Install apt build deps (build-essential, cmake,
   ninja-build, g++, python3/-dev, pkg-config, libc6-dev, sqlite3+libsqlite3-dev,
   libeigen3-dev, libgsl-dev, ccache). Confirm compiler/cmake/python versions. Create a
   Python venv under `mtp/venv` with numpy/pandas/matplotlib/scipy for later orchestration.

2. **Clone + build ns-3 + nr; verify against a stock nr example.** Clone `ns-3-dev` at tag
   ns-3.48 into `mtp/ns-3-dev`, clone `nr` v5.1 into `mtp/ns-3-dev/contrib/nr`. Configure
   (`ns3 configure` with examples+tests enabled) and build. Run a stock nr example
   (`cttc-nr-demo`) to prove the module works end-to-end. **This is the first execution step.**

3. **Scenario skeleton.** Create `contrib/nr/examples/` (or a `mtp/scenario/` scratch dir) a
   new C++ program `ltm-forged-handover.cc`: urban hex/grid gNB layout, 250 m ISD, 4 GHz,
   configurable `--numCells`, `--numUes`, `--ueSpeedKmph`, `--simTime`, `--rngSeed`,
   `--rngRun`. UEs on a constant-velocity mobility model traversing cell edges. DL+UL UDP
   bearers. Wire it into the nr CMake example list; build clean.

4. **Baseline LTM-style fast cell switch (no attack) + validate ~0 ms interruption.**
   Approximate LTM as a fast MAC-triggered intra-frequency handover between gNBs (proxy B1).
   Drive handovers from measurement/geometry as the UE crosses edges. Instrument the
   legitimate handover interruption time; confirm the no-attack baseline interruption is
   near-zero (target ~1–2 ms, matching the spec's intra-BS LTM budget).

5. **RLF / RRC re-establishment tracing.** Hook ns-3 LTE/NR RRC traces
   (`RadioLinkFailure`, connection-reconfiguration, `HandoverEndOk/HandoverEndError`,
   re-establishment start/end) to timestamp outage windows per UE. Define
   "mobility interruption time" precisely (last good DL/UL → first restored) and record it.

6. **Per-bearer throughput + packet-loss measurement.** Attach FlowMonitor and/or bearer-level
   Rx/Tx counters to the victim UE bearer. Emit DL/UL throughput (Mbps) and packet-loss %
   over the run, plus a during-outage window slice.

7. **Ping-pong + short-time-of-stay detection.** Track per-UE cell-association history; compute
   ping-pong rate (A→B→A within TTT window) and short-time-of-stay rate (residence < threshold).
   These separate attack-induced churn from benign mobility churn.

8. **Link-tier lookup table (§6).** Implement a margin→P(forge-decode) table with linear
   interpolation for margins between tabulated points {0:.37,1:.42,2:.46,3:.50,4:.54,6:.63,
   8:.71}. Unit-check the interpolation. This is the ONLY place RF capture enters (B2).

9. **Attacker injection logic.** Add `--numAttackers`, `--overshadowMarginDb`, and attack
   enable flag. On each legitimate/opportune cell-switch trigger for a targeted victim UE,
   draw a per-attempt Bernoulli with p from Step-8 table (seeded RNG). On success, inject a
   *forged* cell-switch to a wrong/non-existent target Configuration ID → force RLF →
   RRC re-establishment (the DoS consequence). Multiple attackers = more injection
   opportunities/targets. On failure, legitimate switch proceeds.

10. **Full CLI parameterisation + deterministic seeding.** Expose every sweep axis as a
    command-line arg; make results fully reproducible from `(--rngRun)`. Emit a single-line
    machine-readable results record (CSV/JSON) per run: all params + all metrics.

11. **Baseline operating point definition + smoke sweep.** Fix baseline = 60 km/h, 1 attacker,
    ~12 cells, ~150 UEs, margin swept 0–8 dB. Run a handful of seeds to confirm the attack
    vs no-attack contrast appears (large interruption inflation) before scaling seeds.

12. **Python sweep-orchestration harness.** `mtp/sweep/run_sweep.py`: one-factor-at-a-time
    around baseline — (a) margin 0–8 dB (headline), (b) attacker count 1–10, (c) speed
    3/30/60/120 km/h, (d) density low/med/high (UEs and/or cells). Target ≥100 seeds/point;
    parallelise across 8 cores; document any reduction and its justification. Each run writes
    its CSV record; harness collates into per-axis raw CSVs.

13. **Aggregation into tables (mean ± 95% CI).** `mtp/sweep/aggregate.py`: group by operating
    point, compute mean and 95% CI (t-based) for every metric, output per-axis summary tables
    mirroring the spec's §7/§8 structure (incl. no-attack vs forged-switch interruption:
    mean/median/95th).

14. **Plot generation.** `mtp/sweep/plots.py`: interruption-time vs margin, attack-success vs
    margin (overlaid with §6 input table), interruption vs attacker count / speed / density,
    throughput collapse + packet-loss bars, ping-pong/short-stay. Save PNGs under `mtp/results/`.

15. **Attack-success-vs-margin validation.** Confirm measured forged-switch success rate through
    the sweep reproduces/tracks the §6 input table (sanity on the injection pipeline).

16. **Full validation pass vs §8 sanity targets.** Run the full seed count. Check the
    qualitative shape: near-zero no-attack interruption → 2–3 orders-of-magnitude DoS outage
    under a single forged switch, with clear separation of the CIs. Record actual numbers
    (not force-fit) and compare shape to §8.

17. **Documentation (README).** `mtp/README.md`: how to build/run/sweep/reproduce, the two
    modelling boundaries (B1, B2) spelled out, scope statement (attack only; Ch. 6–7 out of
    scope), directory map, and a results summary. Do NOT document secrets.

18. **Final cleanup.** Remove scratch/build artefacts not needed for reproduction, ensure the
    tree is buildable from clean, verify `changes.txt` is complete, tidy the sweep/results dirs.

---

## SCOPE CHANGE (user-directed, 2026-08-27) — read this before doing anything else

The user has narrowed the immediate goal. **Do NOT do Steps 6, 7, 10 (full multi-axis CLI
sweep parameterisation), 11 (smoke sweep), 12 (sweep harness), 13 (aggregation), 14 (plots),
15/16 (large-scale validation) right now.** No measurement campaign, no statistics, no plots,
no city-scale (many-gNB, many-UE) runs for now — that is explicitly deferred to a later phase.

**Current goal, and the new definition of "done" for this phase:** get the forged
LTM cell-switch attack mechanism itself working *correctly* at SMALL SCALE (a handful of
gNBs, a handful of UEs — whatever Step 3's scenario already uses is fine, e.g. 4 cells /
3-8 UEs) and DEMONSTRATE it with one or a few real runs:
1. Step 5 (RLF/RRC re-establishment tracing) — still needed, in progress. Keep it, but keep
   it minimal/correct rather than building out a big metrics system.
2. Step 8 (link-tier margin -> P(forge-decode) lookup table, §6 of the spec) — needed, this
   is how attack success is decided per attempt.
3. Step 9 (attacker injection logic: forged/spoofed target cell-switch command, drawn via the
   Step-8 table) — this is the actual attack. Get it correct and honest to the thesis's
   threat model (unicast, single/few victim UEs, spoofed Target Configuration ID, no keys).
4. A basic CLI toggle for attacker on/off, attacker count, and overshadow margin is enough —
   do NOT build the full sweep-axis CLI surface from Step 10.
5. Demonstrate with real, reported runs: baseline (no attack) shows clean handover, low
   interruption; with the attack enabled, show the forged switch causing RLF ->
   RRC re-establishment -> a clearly larger outage. A handful of runs at a couple of margin
   values is enough to show it behaves correctly (attack lands sometimes per the probability
   table, causes DoS when it does) — this is a correctness demonstration, not a statistical
   campaign.

Once that is genuinely working and verified (not fabricated), STOP. Write a short final
summary (reuse REVIEW_SUMMARY.md) and end both agents' work for this phase. The full
city-scale sweep/measurement/plotting campaign (original Steps 10-16, plus real multi-cell/
many-UE scale) is picked up in a later phase, not now.

## Deviations / decisions log
- (Step 1/2) Using ns-3.48 + nr v5.1 (latest pair) rather than the spec's example "ns-3.40+",
  because the host toolchain (g++ 15.2, cmake 4.2, Python 3.14) is far newer than ns-3.40
  supports; the latest release is the compatible choice. Spec says "recent release, e.g.
  ns-3.40+", so this is within spec.
- Seed count: spec permits reducing from ≥100 if computationally infeasible, with
  justification. Actual per-point seed count will be decided at Step 12 based on measured
  single-run wall-clock time on 8 cores, and documented there and in `changes.txt`.
