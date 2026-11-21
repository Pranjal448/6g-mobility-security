"""End-to-end Finding-1 simulation: capture -> TA corruption -> decode failure.

Left panel  -- the two negative controls versus the attack at a representative
               +10 dB relay advantage, for all three induced delays. Driven by
               chained real capture (atk05a) and real composed-BLER (sim_rebuild)
               data, not an assumed pipeline.
Right panel -- p_captured versus p_decode_fail(e2e) across relay power advantage,
               delta=7 units: the two curves diverge visibly only at delta=7
               (BLER<1 there); for delta=16/32 they track closely (BLER~=1
               beyond 8 units), plotted for comparison. Both negative controls
               (not plotted here) use the same real zero-error noise floor
               rather than an assumed zero.
Data: 09_full_sims/atk05c_e2e/results/summary.csv.
"""

import csv
import os

from common import AMBER, BLUE, GREEN, INK, MUTED, RED, plt, save

SIM = "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/09_full_sims/atk05c_e2e/results"


def read():
    with open(os.path.join(SIM, "summary.csv")) as fh:
        return [r for r in csv.DictReader(fh)]


rows = read()


def find(label_substr):
    for r in rows:
        if label_substr in r["label"]:
            return r
    raise KeyError(label_substr)


def series(delta):
    pts = sorted((float(r["rel_db"]), float(r["p_captured"]), float(r["p_decode_fail_e2e"]))
                 for r in rows if r["group"] == "attack" and int(float(r["delta_units"])) == delta)
    return pts


fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.2, 2.9))

# ------------------------------------------------------------ left: controls vs attack
cats = [
    ("No relay\n$\\Delta=0$", find("delta=0"), BLUE),
    ("Weak relay\n$\\Delta=4$", find("delta=4"), BLUE),
    ("Attack\n$\\Delta=7$", find("delta=7 units, rel_db=+10"), AMBER),
    ("Attack\n$\\Delta=16$", find("delta=16 units, rel_db=+10"), RED),
    ("Attack\n$\\Delta=32$", find("delta=32 units, rel_db=+10"), RED),
]
x = [i * 1.5 for i in range(len(cats))]
vals = [float(r["p_decode_fail_e2e"]) for _, r, _ in cats]
colors = [c for _, _, c in cats]
axL.bar(x, vals, color=colors, width=0.8, zorder=3)
for xi, v in zip(x, vals):
    axL.text(xi, v + 0.03, f"{v:.3f}" if v > 0 else "0", ha="center", va="bottom", fontsize=7, color=INK)
axL.set_xticks(list(x))
axL.set_xticklabels([c for c, _, _ in cats], fontsize=6.9)
axL.set_xlim(x[0] - 0.85, x[-1] + 0.85)
axL.set_ylabel("P(decode fail), 200,000 trials", fontsize=8)
axL.set_ylim(0, 1.12)
axL.tick_params(labelsize=7.4)
axL.spines[["top", "right"]].set_visible(False)
axL.set_title("Same code, same datasets (attack: +10 dB relay)", fontsize=7.6, color=INK, pad=6)

# ------------------------------------------------------------ right: capture vs decode-fail
s7 = series(7)
s16 = series(16)
axR.plot([p[0] for p in s7], [p[1] for p in s7], color=INK, lw=1.6, ls="--", label="p(captured)")
axR.plot([p[0] for p in s7], [p[2] for p in s7], color=AMBER, lw=1.6, marker="o", ms=3,
          label="p(decode fail), $\\Delta=7$")
axR.plot([p[0] for p in s16], [p[2] for p in s16], color=RED, lw=1.6, marker="s", ms=3,
          label="p(decode fail), $\\Delta=16$/$32$")
axR.set_xlabel("relay power advantage (dB)", fontsize=8)
axR.set_ylabel("probability", fontsize=8)
axR.set_ylim(0, 1.05)
axR.tick_params(labelsize=7.4)
axR.legend(fontsize=6.6, frameon=False, loc="upper left")
axR.spines[["top", "right"]].set_visible(False)
axR.set_title("Stage B only matters at $\\Delta=7$", fontsize=8, color=INK, pad=6)

save(fig, "atk05c_e2e")
