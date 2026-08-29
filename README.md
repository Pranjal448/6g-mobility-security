# Forged 6G LTM Cell-Switch Attack — ns-3 / 5G-LENA

A system-level model, in **ns-3.48 + 5G-LENA (`nr`) v5.1**, of a forged **6G Lower-layer
Triggered Mobility (LTM)** cell-switch attack: an unauthenticated Layer-2 MAC Control Element
(MAC CE) mobility command is forged by an overshadowing attacker, forcing one target UE to
mis-switch, which produces a radio-link failure, an RRC re-establishment, and a targeted
denial-of-service far above the near-zero intra-base-station interruption LTM is meant to
provide.

This reproduces the *system tier* of the M.Tech thesis *"Detecting Forged Handovers — a
measured attack on the 6G L2 cell-switch command."*

---

## What is modelled

- A **real LTM cell-switch MAC CE** carried on the downlink control channel (added to the `nr`
  core as `NrLtmCellSwitchMessage`), below PDCP and **unauthenticated**.
- **Accurate LTM semantics**: the UE is **pre-configured with candidate target cells** in
  advance; the MAC CE **activates a candidate by its Target Configuration ID** — an activation,
  not a fresh L3 reconfiguration.
- The **attack**: an SDR overshadower injects a *forged* MAC CE at the victim UE's PHY carrying
  a **spoofed Target Configuration ID** the UE has no candidate for → the switch cannot be
  activated → handover failure → RRC re-establishment → **DoS**.
- Whether the forged frame "captures" is drawn from the thesis's link-tier
  **margin → P(forge-decode)** table.

### Headline result (real simulation output)

| Metric | Legitimate LTM activation | Forged switch |
|---|---|---|
| Cell-switch execution (control-plane) | **~2.0 ms** | **~240 ms** |
| Data-plane interruption | ~2–14 ms | **~262 ms** |

A single forged MAC CE inflates the mobility-interruption KPI by ~120×, at 8 dB overshadow
margin with the forged frame capturing 71 % of the time (matching the thesis §6 table).

---

## Honest modelling boundaries

- **B1 — 6G ≈ NR.** 6G is modelled as NR (5G-LENA); the attack targets the unauthenticated
  MAC-CE trigger, which is implemented natively.
- **B2 — the RF capture effect is not simulated.** The overshadow enters only as the
  margin-indexed probability that the forged frame decodes; ns-3 plays out the mobility/DoS
  consequence, not the radio waveform. The attacker is an injection hook on the victim PHY, not
  a separate radiating node.
- **Attacker recon stages** (route mapping, C-RNTI recovery, reactive PDCCH monitoring) are not
  simulated — consistent with the thesis, which treats them as assembled prior-art primitives.
- **RACH-less LTM activation timing is not modelled.** `nr` has no RACH-less / prepare-and-hold
  path, so the *mechanical* move of a valid activation reuses `nr`'s handover execution (the
  ~2 ms is `nr`'s fast X2 handover, not a true sub-millisecond RACH-less activation). The LTM
  *architecture* (pre-configured candidates + MAC-CE activation by config ID) is faithful; the
  RACH-less *timing* is not.

See `docs/` and `report/NS3_LTM_Forged_Handover_Report.pdf` for the full write-up.

---

## Repository layout

```
scenario/ltm-forged-handover.cc   The scenario + attacker (the ns-3 program)
patches/nr-v5.1-ltm.patch         Our additive changes to the nr v5.1 core (the LTM MAC CE)
patches/README.md                 How to apply and build
docs/                             THESIS_ATTACK_SPEC.md, PLAN.md, changes.txt (full change-log)
report/                           15+ page technical report (PDF) + its generator scripts
```

---

## Reproduce it

**1. Get ns-3 + nr (matched versions):**
```bash
git clone https://gitlab.com/nsnam/ns-3-dev.git
cd ns-3-dev && git checkout ns-3.48
git clone https://gitlab.com/cttc-lena/nr.git contrib/nr
cd contrib/nr && git checkout v5.1 && cd ../..
```

**2. Apply the LTM core changes and drop in the scenario:**
```bash
# from ns-3-dev/contrib/nr
git apply /path/to/patches/nr-v5.1-ltm.patch
cp /path/to/scenario/ltm-forged-handover.cc examples/
# (the patch already registers the example in examples/CMakeLists.txt)
```

**3. Build:**
```bash
cd ns-3-dev
./ns3 configure -d optimized --enable-examples
./ns3 build ltm-forged-handover
```

**4. Run.**

The small-scale attack (1 attacker · 1 victim UE · 2 gNB):
```bash
./ns3 run "ltm-forged-handover --numCells=2 --numUes=1 --ueSpeedKmph=30 --simTime=9 \
           --attackEnabled=1 --numAttackers=1 --overshadowMarginDb=8 \
           --attackForceTimeMs=2000 --verbose=1"
```
Look for `FORGE-INJ`, `LTM-RX ... configId=50001 -> NO pre-configured candidate (spoofed)`,
`DURING_HANDOVER`, and `Failure outage ... 240 ms`.

Baseline (attack off, same scenario — should be clean):
```bash
./ns3 run "ltm-forged-handover --numCells=2 --numUes=1 --ueSpeedKmph=30 --simTime=9 --attackEnabled=0"
```

Legitimate LTM activations over the air (multi-cell, natural handovers):
```bash
./ns3 run "ltm-forged-handover --numCells=4 --numUes=8 --ueSpeedKmph=120 --simTime=10 \
           --attackEnabled=0 --verbose=1"
```
Shows `LTM-RX ... -> ACTIVATE pre-configured candidate cell C [legit]`, ~2.0 ms switch time.

Verify the capture-probability table:
```bash
./ns3 run "ltm-forged-handover --printForgeTable"
```

### Key command-line arguments

| Arg | Meaning |
|---|---|
| `--numCells`, `--numUes`, `--ueSpeedKmph` | topology & mobility |
| `--attackEnabled`, `--numAttackers` | attack on/off; number of targeted victim UEs |
| `--overshadowMarginDb` | attacker power margin 0–8 dB → capture probability (§6 table) |
| `--attackForceTimeMs` | force one attack at this time (deterministic demo); omit for natural triggering |
| `--rngSeed`, `--rngRun` | deterministic, reproducible seeding |
| `--printForgeTable` | unit-check the capture-probability table and exit |

---

## Machine-readable output

Each run prints `RESULT_BASELINE`, `RESULT_RLF` and `RESULT_ATTACK` lines carrying every
parameter and metric (interruption times, handover-failure count, forged attempts/lands,
throughput/loss) for scripted collection.

---

*Built on [ns-3](https://www.nsnam.org/) and the [CTTC 5G-LENA `nr`](https://gitlab.com/cttc-lena/nr)
module. The `nr` core changes are additive (a new control-message type, gNB emit, UE PHY
dispatch, CPHY-SAP upcall, UE-RRC candidate activation) and are provided as a patch against
`nr` v5.1; the `nr` module itself is not redistributed here.*
