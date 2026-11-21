"""ATK-05a: the capture contest at a real PRACH detector, and where the relay has to stand.

Left panel  -- probability that the candidate cell reports the relayed delay, against the
               relayed copy's received power relative to the direct path, for several induced
               delays.  Data: 09_full_sims/atk05a/results/A_surface_rayleigh.csv.
Right panel -- the placement region that follows, from the TR 38.901 path loss: the largest
               relay-to-candidate distance meeting the 90 % threshold, as a fraction of the
               victim's own distance.  Data: results/SUMMARY_link_budget.csv.
"""

import csv
import os
from collections import defaultdict

from common import AMBER, BLUE, GREEN, INK, MUTED, RED, plt, save

SIM = "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/09_full_sims/atk05a/results"


def read(name):
    path = os.path.join(SIM, name)
    with open(path) as fh:
        return [r for r in csv.DictReader(l for l in fh if not l.startswith("#"))]


fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.2, 2.9))

# ---------------------------------------------------------------- left: the contest
ray = read("A_surface_rayleigh.csv")
pdp = read("A_surface_pdp300.csv")


def curve(rows, delta):
    pts = sorted((float(r["rel_db"]), float(r["p_damaging"])) for r in rows
                 if abs(float(r["delta_units"]) - delta) < 1e-6)
    return [x for x, _ in pts], [y for _, y in pts]


for rows, col, lab in ((ray, BLUE, "flat Rayleigh per path"),
                       (pdp, RED, "20-tap profile, 300 ns spread")):
    for i, d in enumerate((7.0, 16.0, 32.0)):
        x, y = curve(rows, d)
        axL.plot(x, y, color=col, lw=1.4, alpha=1.0 if i == 0 else 0.45,
                 label=lab if i == 0 else None)

axL.axhline(0.5, color=MUTED, lw=0.8, ls=":")
axL.axhline(0.9, color=MUTED, lw=0.8, ls=":")
axL.annotate("+5.3 dB", xy=(5.3, 0.9), xytext=(1.0, 0.97), fontsize=7, color=RED,
             arrowprops=dict(arrowstyle="-|>", lw=0.8, color=RED, shrinkB=2))
axL.annotate("+9.9 dB", xy=(9.9, 0.9), xytext=(11.4, 0.72), fontsize=7, color=BLUE,
             arrowprops=dict(arrowstyle="-|>", lw=0.8, color=BLUE, shrinkB=2))
axL.text(14.2, 0.30, "three induced delays\n(7, 16 and 32 units)\nper fading model, drawn\non top of one another",
         fontsize=6.6, color=MUTED, ha="right", va="center", linespacing=1.35)
axL.set_xlabel("relayed copy's received power, relative to direct path (dB)", fontsize=8)
axL.set_ylabel("P(reported error $\\geq$ 7 T$_\\mathrm{A}$ units)", fontsize=8)
axL.set_title("What the relay must spend", fontsize=8.5, color=INK, pad=5)
axL.set_xlim(-12, 15)
axL.set_ylim(0, 1.02)
axL.legend(fontsize=6.6, frameon=False, loc="upper left", bbox_to_anchor=(-0.02, 1.04))
axL.tick_params(labelsize=7)
for sp in ("top", "right"):
    axL.spines[sp].set_visible(False)

# ---------------------------------------------------------------- right: placement
lb = read("SUMMARY_link_budget.csv")
sel = defaultdict(dict)
for r in lb:
    if r["scenario"] != "UMa NLOS" or not r["relay_r_max_over_d"]:
        continue
    if abs(float(r["ue_distance_m"]) - 500.0) > 1e-6:
        continue
    sel[float(r["threshold_db"])][float(r["eirp_advantage_db"])] = \
        float(r["relay_r_max_over_d"])

for thr, col, lab in ((5.3, RED, "+5.3 dB (90 %, urban multipath)"),
                      (9.9, BLUE, "+9.9 dB (90 %, flat fading)")):
    if thr not in sel:
        continue
    pts = sorted(sel[thr].items())
    axR.plot([a for a, _ in pts], [v for _, v in pts], color=col, lw=1.6, marker="o",
             ms=3.4, label=lab)

axR.axhline(1.0, color=INK, lw=1.0, ls="--")
axR.axvline(10.0, color=MUTED, lw=0.8, ls=":")
axR.annotate("at +10 dB the relay may stand\nas far from the cell as the victim",
             xy=(10, 1.0), xytext=(0.6, 2.25), fontsize=7, color=INK,
             arrowprops=dict(arrowstyle="-|>", lw=0.8, color=MUTED, shrinkB=3))
axR.text(29.5, 0.12, "ratio is the same at victim\ndistances of 200 m to 2 km",
         fontsize=6.6, color=MUTED, ha="right", va="bottom", linespacing=1.35)
axR.set_xlabel("relay radiated power advantage over the device (dB)", fontsize=8)
axR.set_ylabel("usable relay radius / victim distance", fontsize=8)
axR.set_title("Placement, UMa NLOS, 3.5 GHz, victim at 500 m", fontsize=8.5, color=INK, pad=5)
axR.set_ylim(0, 3.6)

axR.set_xlim(-1, 31)
axR.legend(fontsize=6.6, frameon=False, loc="upper left")
axR.tick_params(labelsize=7)
for sp in ("top", "right"):
    axR.spines[sp].set_visible(False)

fig.tight_layout(pad=0.6)
save(fig, "atk05a_capture")
