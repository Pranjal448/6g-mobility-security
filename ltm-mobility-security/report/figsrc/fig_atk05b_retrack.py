"""ATK-05b Leg R: what a re-tracking receiver can and cannot recover.

Left panel  -- post-equalisation error vector magnitude against the uplink timing error, with
               the receiver's window fixed (what srsRAN does) and after a correction derived
               from the reference-symbol timing estimate (the most generous closed loop).
Right panel -- why the closed loop runs out: the timing estimate against the true error. The
               estimate tracks the truth only to about four units, then folds back, so beyond
               that the receiver cannot measure the error it would have to correct.

Data: 09_full_sims/atk05b/results/A_mu1_TDL-C_ds300_cl.csv
"""

import csv
import os

from common import BLUE, GREEN, INK, MUTED, RED, plt, save

SIM = "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/09_full_sims/atk05b/results"
SRC = "A_mu1_TDL-C_ds300_cl.csv"

with open(os.path.join(SIM, SRC)) as fh:
    rows = [r for r in csv.DictReader(l for l in fh if not l.startswith("#"))]
# Only ta_units >= 0 ("EARLY_arrival_attack_dir") is physically reachable: a relay can only
# add delay, never subtract it, so it can never produce the negative ("LATE_arrival") branch.
rows = [r for r in rows if int(r["ta_units"]) >= 0]
rows.sort(key=lambda r: int(r["ta_units"]))

ta = [int(r["ta_units"]) for r in rows]
evm = [float(r["evm_mean"]) for r in rows]
cl = [float(r["cl_evm_mean"]) if r["cl_evm_mean"] not in ("", "nan") else float("nan")
      for r in rows]
est = [float(r["ta_est_units_mean"]) for r in rows]

fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.2, 2.9))

# ---------------------------------------------------------------- left
axL.semilogy(ta, evm, color=RED, lw=1.7, marker="o", ms=3.0,
             label="window fixed (what srsRAN does)")
axL.semilogy(ta, cl, color=BLUE, lw=1.7, marker="s", ms=3.0,
             label="window re-tracked (most generous)")
axL.axhline(0.3162, color=MUTED, lw=0.9, ls=":")
axL.axhline(1.0, color=MUTED, lw=0.9, ls="--")
bb = dict(facecolor="white", edgecolor="none", pad=0.8)
axL.text(19.5, 0.345, "$-10$ dB: still carryable", fontsize=6.5, color=MUTED, va="bottom",
         ha="right", bbox=bb)
axL.text(19.5, 1.10, "0 dB: error equals signal", fontsize=6.5, color=MUTED, va="bottom",
         ha="right", bbox=bb)
axL.axvspan(5.0, 6.9, color=GREEN, alpha=0.10)
axL.annotate("re-tracking buys\n+1.9 units at the median",
             xy=(6.0, 0.6), xytext=(0.6, 0.022), fontsize=6.8, color=INK,
             arrowprops=dict(arrowstyle="-|>", lw=0.8, color=MUTED, shrinkB=3))
axL.set_xlabel("relay-injected uplink timing error (T$_\\mathrm{A}$ units)",
               fontsize=7.6)
axL.set_ylabel("post-equalisation EVM", fontsize=8)
axL.set_title("Where the uplink stops working", fontsize=8.5, color=INK, pad=5)
axL.set_xlim(-1, 20)
axL.set_ylim(0.01, 60)
axL.legend(fontsize=6.5, frameon=False, loc="lower right")
axL.tick_params(labelsize=7)
for sp in ("top", "right"):
    axL.spines[sp].set_visible(False)

# ---------------------------------------------------------------- right
axR.plot([-1, 20], [-1, 20], color=MUTED, lw=0.9, ls="--")
axR.plot(ta, [-v for v in est], color=BLUE, lw=1.7, marker="o", ms=3.0,
         label="reference-symbol timing estimate")
axR.axvspan(0, 4.3, color=GREEN, alpha=0.10)
axR.text(2.15, 17.0, "estimate\nusable", fontsize=6.6, color=INK, ha="center", linespacing=1.2)
axR.annotate("ideal: estimate = truth", xy=(15, 15), xytext=(7.5, 9.5), fontsize=6.8,
             color=MUTED, arrowprops=dict(arrowstyle="-|>", lw=0.8, color=MUTED, shrinkB=2))
axR.annotate("beyond about four units the\nestimate folds back towards zero",
             xy=(17, -0.4), xytext=(11.0, 17.5), fontsize=6.8, color=INK,
             arrowprops=dict(arrowstyle="-|>", lw=0.8, color=MUTED, shrinkB=3))
axR.set_xlabel("relay-injected uplink timing error (T$_\\mathrm{A}$ units)", fontsize=8)
axR.set_ylabel("estimated error (T$_\\mathrm{A}$ units)", fontsize=8)
axR.set_title("The receiver cannot measure what it must correct", fontsize=8.5, color=INK,
              pad=5)
axR.set_xlim(-1, 20)
axR.set_ylim(-3, 20)
axR.tick_params(labelsize=7)
for sp in ("top", "right"):
    axR.spines[sp].set_visible(False)

fig.tight_layout(pad=0.6)
save(fig, "atk05b_retrack")
