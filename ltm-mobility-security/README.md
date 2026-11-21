# Security Analysis of Lower-Layer Triggered Mobility (LTM) in 5G-Advanced and 6G

M.Tech Phase-I thesis work — IIT Guwahati, under Prof. Moumita Patra.

LTM (3GPP Rel-18/19) replaces the legacy RRC handover with a single MAC Control
Element, relying on three speed-up mechanisms: pre-cached candidate configurations,
early timing-advance (TA) acquisition over PRACH before the handover happens, and a
RACH-less cell switch that applies the cached TA directly. This work audits those
three mechanisms themselves — independent of any message forgery — and reports two
findings that survive even full MAC CE integrity protection, because neither relies
on a forged value.

## Finding 1 — Corrupted early timing advance

Candidate-cell TA acquisition is bound only to a preamble index, occasion, and cell
ID — never to a UE identity — and 3GPP specifies no retention or expiration bound on
the cached value (TS 38.300 §9.2.3.5.2: "network implementation"). A passive RF relay
can forward the UE's preamble with extra propagation delay, inflating the TA the
candidate cell measures and caches, entirely before the handover takes place.

Using real, unmodified PRACH/PUCCH detectors from srsRAN and OpenAirInterface driven
by a custom channel-model harness (AWGN / flat Rayleigh / TR 38.901-style urban
multipath), we measure:
- a timing error of **6–8 TA units (median 7)** crosses the decodability boundary at
  the candidate cell — deterministic under flat fading/AWGN, more gradual under
  multipath;
- the relay needs only **+9.9 dB** power margin under flat fading, or **+5.3 dB**
  under realistic urban multipath, to win the correlator contest against the UE's own
  direct path;
- the candidate's own PRACH search window (≈46 TA units) is roughly 6× wider than
  this decode boundary, so window truncation is never the limiting factor.

Code: [`simulation/finding1-early-ta-capture/`](simulation/finding1-early-ta-capture/)
(`atk05a` — PRACH capture campaign; `atk05b` — closed-loop TA re-tracking; `atk05c_e2e`
— end-to-end composition). Report chapter: [`report/chapters/timing_advance.tex`](report/chapters/timing_advance.tex).

## Finding 2 — Scheduling Request deadlock

A UE arriving via a RACH-less switch without an uplink grant must request one with a
Scheduling Request (SR) on PUCCH. TS 38.321 §5.4.4 says that once the SR retry counter
exhausts, the UE *unconditionally* releases PUCCH, SRS and all grants — but the
clause's own fallback to random access is gated by a condition that evaluates false
during an ongoing RACH-less switch. The UE is left with no PUCCH, no grant, and no
RACH: a self-sealing deadlock that needs no attacker-crafted message, only an SR that
fails during that window.

Finding 1 feeds directly into Finding 2: a corrupted TA misaligns the UE's uplink, so
its SR goes undecodable at the gNB. We measure the SR counter exhausting with near
certainty under flat fading (P ≥ 0.996) and with high probability under multipath
(P = 0.75–0.97), and we derive the exact configuration rule that determines whether a
deployment is exposed: `sr-TransMax × SR interval ≥ T304`.

Code: [`simulation/finding2-sr-deadlock/`](simulation/finding2-sr-deadlock/)
(`atk16` — deadlock-window/configuration sweep; `atk16b_sr` — real PUCCH Format 0 SR
detector under the corrupted TA; `atk16c_statemachine` — MAC state-machine
replication). Report chapter: [`report/chapters/dead_state.tex`](report/chapters/dead_state.tex).

## Repository layout

```
ltm-mobility-security/
├── report/            LaTeX source + compiled PDF of the thesis report
│   ├── chapters/       introduction, literature review, Finding 1, Finding 2, results, conclusion
│   ├── frontmatter/     abstract, acknowledgements
│   ├── figures/        compiled figures used in the report
│   ├── figsrc/         matplotlib scripts that generate those figures from the result CSVs
│   └── main.pdf         compiled report
└── simulation/
    ├── finding1-early-ta-capture/   relay-capture campaign source + raw result CSVs
    └── finding2-sr-deadlock/        SR-deadlock campaign source + raw result CSVs
```

Each campaign directory under `simulation/` carries its own `src/` (the hand-written
channel-model + detector harness, built against srsRAN/OpenAirInterface — those
upstream trees are not vendored here), the driver script, and `results/*.csv` — the
raw measured data behind every number and plot in the report.

Full methodology, derivations, and related-work positioning are in `report/main.pdf`.
