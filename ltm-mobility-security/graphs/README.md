# Graphs

PNG renders of the figures used across the report, the Phase-I seminar deck, and viva
prep — generated from the raw CSVs in `../simulation/`. The report itself embeds the
vector versions of these in `../report/figures/`; these PNGs are the same results in a
quick-to-view form, plus a few presentation/viva-only diagrams that don't appear in the
final report text.

| File | What it shows |
|---|---|
| `atk05_relay.png`, `atk05_relay_geometry.png`, `atk05_relay_detector.png` | Finding 1: relay geometry and the candidate's correlator output (direct vs. relayed preamble) |
| `atk05_sim.png` | Finding 1: channel-model / simulation harness overview |
| `atk05a_capture.png`, `atk05a_window.png`, `atk05a_window_simple.png` | Finding 1: relay capture-advantage vs. injected delay, and the PRACH search-window boundary |
| `atk05_delta_line.png` | Finding 1: decode-failure rate vs. injected TA delay (the measured 6-8 unit boundary) |
| `atk05b_retrack.png` | Finding 1: srsRAN TA re-tracking behaviour once capture begins |
| `atk05c_e2e.png` | Finding 1: end-to-end composition result |
| `atk16_deadlock.png`, `atk16_e2e.png`, `atk16_space.png` | Finding 2: the SR-deadlock mechanism and configuration-space sweep |
| `atk16_sr.png`, `atk16_sr_single.png` | Finding 2: PUCCH Format 0 SR-detection probability vs. TA error |
| `atk16_t304_safe.png` | Finding 2: the safe-configuration rule, `sr-TransMax x SR interval >= T304` |
| `sr_deadlock_flowchart.png` | Finding 2: TS 38.321 section 5.4.4 SR procedure redrawn as a flowchart, showing both random-access escapes gated shut |
| `ltm_flow.png` | LTM's three speed-up mechanisms (background) |
| `amarisoft_final.png` | Deployed-config case study (Amarisoft LTM configuration) |
| `atk09_delay.png` | Future-work attack (ATK-09), not part of Finding 1 or Finding 2 |
