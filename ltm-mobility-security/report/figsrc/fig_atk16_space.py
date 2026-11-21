"""ATK-16: how much of the configuration space admits the deadlock, and what it costs to leave.

Left panel  -- fraction of configurations in which the scheduling request counter is exhausted
               before the switch window closes, against the switch window length, for the
               90-pair space at a fixed periodicity and for the whole 5400-configuration space.
               Data: 09_full_sims/atk16/results/window_by_mu_period.csv.
Right panel -- the two things that grow together: the dead interval the device suffers, and the
               minimum scheduling request interval a safe configuration must accept.
"""

import csv
import os
from collections import defaultdict

from common import AMBER, BLUE, GREEN, INK, MUTED, RED, plt, save

SIM = "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/09_full_sims/atk16/results"

T304 = [50, 100, 150, 200, 500, 1000, 2000, 10000]
T_EXHAUST_REF = 128.0          # ms, reference configuration (mu=1, sl2, n8, ms16)
REEST_FLOOR = 1.929            # ms, re-establishment floor at mu=1
SR_TRANS_MAX = 64              # the ASN.1 maximum

rows = list(csv.DictReader(open(os.path.join(SIM, "window_by_mu_period.csv"))))

fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.2, 2.9))

# ---------------------------------------------------------------- left
pairs = defaultdict(dict)
for r in rows:
    pairs[(int(r["mu"]), r["periodicity"])][int(r["t304_ms"])] = float(r["fraction"])

whole = {}
for t in T304:
    sel = [float(r["pairs_inside"]) for r in rows if int(r["t304_ms"]) == t]
    tot = [float(r["pairs_total"]) for r in rows if int(r["t304_ms"]) == t]
    whole[t] = sum(sel) / sum(tot)

for key, col, lab in (((1, "1"), BLUE, "90 pairs, one-slot period, $\\mu=1$"),
                      ((0, "640"), GREEN, "90 pairs, 640-slot period, $\\mu=0$")):
    if key not in pairs:
        continue
    axL.plot(T304, [pairs[key][t] for t in T304], color=col, lw=1.5, marker="o", ms=3.2,
             label=lab)
axL.plot(T304, [whole[t] for t in T304], color=RED, lw=2.0, marker="s", ms=3.6,
         label="whole space, 5400 configurations")

axL.set_xscale("log")
axL.set_xticks(T304)
axL.set_xticklabels(["50", "100", "", "200", "500", "1000", "2000", "10000"], fontsize=7)
axL.minorticks_off()
axL.annotate("72 of 90", xy=(10000, 0.80), xytext=(2300, 0.90), fontsize=7, color=INK,
             arrowprops=dict(arrowstyle="-|>", lw=0.8, color=MUTED, shrinkB=2))
axL.set_xlabel("switch supervision window T304 (ms)", fontsize=8)
axL.set_ylabel("fraction admitting the deadlock", fontsize=8)
axL.set_title("How much of the space is exposed", fontsize=8.5, color=INK, pad=5)
axL.set_ylim(0, 1.0)
axL.legend(fontsize=6.4, frameon=False, loc="upper left")
axL.tick_params(labelsize=7)
for sp in ("top", "right"):
    axL.spines[sp].set_visible(False)

# ---------------------------------------------------------------- right
# Below T304 = 150 ms the window closes before the counter exhausts, so there is no deadlock
# at the reference configuration and no outage to plot.
dead = [(t - T_EXHAUST_REF + REEST_FLOOR) if t > T_EXHAUST_REF else float("nan") for t in T304]
need = [t / SR_TRANS_MAX for t in T304]

axR.plot(T304, dead, color=RED, lw=1.6, marker="o", ms=3.2,
         label="device outage, floor (ms)")
axR.plot(T304, need, color=BLUE, lw=1.6, marker="s", ms=3.2,
         label="minimum safe SR interval (ms)")
axR.set_xscale("log")
axR.set_yscale("log")
axR.set_xticks(T304)
axR.set_xticklabels(["50", "100", "", "200", "500", "1000", "2000", "10000"], fontsize=7)
axR.minorticks_off()
axR.axhline(0.5, color=MUTED, lw=0.8, ls=":")
axR.text(55, 0.56, "one slot at $\\mu=1$", fontsize=6.6, color=MUTED, va="bottom")
axR.annotate("9.9 s", xy=(10000, dead[-1]), xytext=(4200, 1500), fontsize=7, color=RED,
             arrowprops=dict(arrowstyle="-|>", lw=0.8, color=RED, shrinkB=3))
axR.text(52, 4.0, "no deadlock here: the window\ncloses before the counter does",
         fontsize=6.4, color=MUTED, ha="left", va="bottom", linespacing=1.35)
axR.annotate("156 ms", xy=(10000, need[-1]), xytext=(2400, 330), fontsize=7, color=BLUE,
             arrowprops=dict(arrowstyle="-|>", lw=0.8, color=BLUE, shrinkB=2))
axR.set_xlabel("switch supervision window T304 (ms)", fontsize=8)
axR.set_ylabel("milliseconds", fontsize=8)
axR.set_title("Both costs grow with the same parameter", fontsize=8.5, color=INK, pad=5)
axR.legend(fontsize=6.6, frameon=False, loc="upper left")
axR.tick_params(labelsize=7)
for sp in ("top", "right"):
    axR.spines[sp].set_visible(False)

fig.tight_layout(pad=0.6)
save(fig, "atk16_space")
