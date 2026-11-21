# Security Analysis of Mobility Mechanisms in 6G Networks

M.Tech thesis (ongoing) — IIT Guwahati, under Prof. Moumita Patra.

This repository collects work toward my M.Tech thesis on the security of handover and
mobility procedures in 6G / 5G-Advanced networks. The thesis problem is still being
finalized; this repo will grow as the work develops.

## Contents

- **[`ltm-mobility-security/`](ltm-mobility-security/)** — the current thesis direction: a
  security analysis of LTM's own speed-up mechanisms (pre-cached candidate configs, early
  timing-advance acquisition, RACH-less cell switch), independent of any message forgery.
  Reports two findings — an unauthenticated, unbounded early timing-advance measurement, and
  a scheduling-request deadlock when the spec's own recovery escape is gated shut — backed by
  real srsRAN/OpenAirInterface simulation campaigns. Includes the full report (LaTeX + PDF),
  simulation harness source, and raw result CSVs.
- **`ltm-mac-ce-study/`** — an early exploratory study modelling a forged Lower-layer
  Triggered Mobility (LTM) cell-switch in ns-3 / 5G-LENA. Kept as background work; not the
  final thesis direction.

More directions and write-ups will be added here as the thesis progresses.
