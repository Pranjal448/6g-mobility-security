"""The scheduling request under a corrupted timing advance.

Left panel  -- probability that srsRAN's own PUCCH Format 0 detector recovers a positive
               scheduling request, against the UE's timing advance error, for three channels.
               The shaded band is the six-to-eight unit decodability boundary of Finding 1.
               Data: 09_full_sims/atk16b_sr/results/A_main_*.csv.
Right panel -- probability of reaching counter exhaustion, against sr-TransMax, with and
               without the corruption.  Per-attempt failure probabilities are taken from the
               left panel at zero and at seven units.
"""

import csv
import os

from common import AMBER, BLUE, GREEN, INK, MUTED, RED, plt, save

SIM = "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/09_full_sims/atk16b_sr/results"


def read(name):
    with open(os.path.join(SIM, name)) as fh:
        return [r for r in csv.DictReader(fh)]


def curve(rows):
    # Only err_units >= 0 is reachable: a relay can only add delay, never subtract it.
    pts = sorted((float(r["err_units"]), float(r["p_sr"])) for r in rows
                 if float(r["err_units"]) >= 0)
    return [p[0] for p in pts], [p[1] for p in pts]


fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.2, 2.9))

# ---------------------------------------------------------------- left: the detector
series = [
    ("A_main_awgn.csv", "No fading", BLUE, "-", "o"),
    ("A_main_rayleigh.csv", "Flat fading", RED, "-", "s"),
    ("A_main_pdp300.csv", "Urban multipath, 300 ns", AMBER, "-", "^"),
]

# Finding 1's decodability boundary, as a band.
axL.axvspan(6, 8, color="#f1f5f9", zorder=0)
axL.text(7, 0.70, "Finding 1\nboundary", ha="center", va="center", fontsize=6.6,
         color=MUTED, linespacing=1.25)

for fname, lab, col, ls, mk in series:
    try:
        x, y = curve(read(fname))
    except FileNotFoundError:
        continue
    axL.plot(x, y, ls, color=col, lw=1.3, marker=mk, ms=2.6, label=lab, zorder=3)

axL.set_xlabel("relay-injected timing advance error ($T_\mathrm{unit}$)", fontsize=8)
axL.set_ylabel("Scheduling request detected", fontsize=8)
axL.set_xlim(-0.6, 14.6)
axL.set_ylim(-0.04, 1.06)
axL.set_xticks([0, 2, 4, 6, 8, 10, 12, 14])
axL.axhline(0.5, color=MUTED, lw=0.7, ls=":", zorder=1)
axL.tick_params(labelsize=7.4)
axL.legend(fontsize=6.9, loc="lower left", frameon=False, handlelength=1.6)
axL.spines[["top", "right"]].set_visible(False)
axL.set_title("Format 0 detector, 10 dB, 2 symbols", fontsize=8, color=INK, pad=6)

# ---------------------------------------------------------------- right: exhaustion
K = [4, 8, 16, 32, 64]  # the sr-TransMax values TS 38.331 admits


def p_exhaust(p_fail):
    return [p_fail**k for k in K]


cases = [
    (0.0365, "No attacker, aligned", GREEN, "o", "-"),
    (0.965, "Corrupted TA, 7 units, urban", AMBER, "^", "-"),
    (0.9995, "Corrupted TA, 7 units, flat", RED, "s", "-"),
]
for p_fail, lab, col, mk, ls in cases:
    axR.plot(K, p_exhaust(p_fail), ls, color=col, lw=1.3, marker=mk, ms=3.2,
             label=lab, zorder=3)

axR.set_yscale("log")
axR.set_xscale("log", base=2)
axR.set_xticks(K)
axR.set_xticklabels([str(k) for k in K])
axR.set_ylim(1e-26, 4.0)
axR.set_xlabel("sr-TransMax", fontsize=8)
axR.set_ylabel("Reaches the dead state", fontsize=8)
axR.tick_params(labelsize=7.4)
axR.legend(fontsize=6.9, loc="center left", frameon=False, handlelength=1.6)
axR.spines[["top", "right"]].set_visible(False)
axR.set_title("One corruption, many correlated failures", fontsize=8, color=INK, pad=6)
axR.text(0.97, 0.055, "larger values also lose\nthe race against T304",
         transform=axR.transAxes, ha="right", va="bottom", fontsize=6.6,
         color=MUTED, linespacing=1.25)

save(fig, "atk16_sr")
