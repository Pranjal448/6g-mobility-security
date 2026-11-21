"""End-to-end clause 5.4.4 state-machine simulation.

Left panel  -- P(deadlock), 1 port, across the negative control (legacy/non-LTM context,
               same or worse channel), the honest UE (TA error = 0), and the attack at
               6/7/8 units of TA error. Driven by measured p_sr, not assumed values.
Right panel -- the T304 race against the real deployed Amarisoft configuration
               (sr-TransMax=64, 20 ms SR period), stacked: T304-expires-first vs deadlock.
Data: 09_full_sims/atk16c_statemachine/results/summary.csv.
"""

import csv
import os

from common import AMBER, BLUE, GREEN, INK, MUTED, RED, plt, save

SIM = "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/09_full_sims/atk16c_statemachine/results"


def read():
    with open(os.path.join(SIM, "summary.csv")) as fh:
        return [r for r in csv.DictReader(fh)]


rows = read()


def find(label_substr):
    for r in rows:
        if label_substr in r["label"]:
            return r
    raise KeyError(label_substr)


fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.2, 2.9))

# ------------------------------------------------------------ left: control vs attack
cats = [
    ("Negative\ncontrol", find("Legacy handover, p_sr=0.0 "), BLUE),
    ("Honest\nUE", find("Honest, 1 port(s), TA error=0"), GREEN),
    ("Attack\n6 units", find("Attack, 1 port(s), TA error=6"), AMBER),
    ("Attack\n7 units", find("Attack, 1 port(s), TA error=7"), RED),
    ("Attack\n8 units", find("Attack, 1 port(s), TA error=8"), RED),
]
x = [i * 1.3 for i in range(len(cats))]
vals = [float(r["p_deadlock"]) for _, r, _ in cats]
colors = [c for _, _, c in cats]
bars = axL.bar(x, vals, color=colors, width=0.8, zorder=3)
for xi, v in zip(x, vals):
    axL.text(xi, v + 0.03, f"{v:.3f}" if v > 0 else "0", ha="center", va="bottom",
              fontsize=7, color=INK)
axL.set_xticks(list(x))
axL.set_xticklabels([c for c, _, _ in cats], fontsize=6.9)
axL.set_xlim(x[0] - 0.75, x[-1] + 0.75)
axL.set_ylabel("P(deadlock), 200,000 trials", fontsize=8)
axL.set_ylim(0, 1.12)
axL.tick_params(labelsize=7.4)
axL.spines[["top", "right"]].set_visible(False)
axL.set_title("Same state machine, same code, 1 port", fontsize=8, color=INK, pad=6)

# ------------------------------------------------------------ right: T304 race
t1000 = find("t304=1000ms")
t2000 = find("t304=2000ms")
labels = ["t304=1000ms\n(reported: safe)", "t304=2000ms\n(reported: vulnerable)"]
p_t304 = [float(t1000["p_t304_first"]), float(t2000["p_t304_first"])]
p_dead = [float(t1000["p_deadlock"]), float(t2000["p_deadlock"])]
xr = range(2)
axR.bar(xr, p_t304, color=BLUE, width=0.5, label="T304 expires first", zorder=3)
axR.bar(xr, p_dead, bottom=p_t304, color=RED, width=0.5, label="Deadlock", zorder=3)
axR.set_xticks(list(xr))
axR.set_xticklabels(labels, fontsize=7.2)
axR.set_ylabel("Outcome fraction, 20,000 trials", fontsize=8)
axR.set_ylim(0, 1.25)
axR.tick_params(labelsize=7.4)
axR.legend(fontsize=6.9, loc="upper center", frameon=False, handlelength=1.4, ncol=2)
axR.spines[["top", "right"]].set_visible(False)
axR.set_title("Amarisoft config, T_exhaust=1280 ms", fontsize=8, color=INK, pad=6)

save(fig, "atk16_e2e")
