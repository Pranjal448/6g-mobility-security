import sys; sys.path.insert(0, "/home/pranjal/mtp_report/figsrc")
from common import *
import csv, glob, numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

R = "/run/media/pranjal/hdd/mtp/LTM_ATTACK_SURFACE/08_final_factcheck/sim_rebuild/results"

def load(path):
    return list(csv.DictReader(open(path)))

fig = plt.figure(figsize=(9.6, 3.9))
gs  = GridSpec(1, 2, width_ratios=[1.0, 1.0], wspace=0.26, figure=fig)

# ------------------------------------------------ panel A : window asymmetry
ax = fig.add_subplot(gs[0])
for w, col, lab, ls in ((0.0, RED, "window offset 0", "-"),
                        (0.5, BLUE, "window offset 0.5  (srsRAN default)", "-")):
    rows = load(f"{R}/A_window_flat_fdfilter_w{w}.csv")
    x = np.array([float(r["ta_units"]) for r in rows])
    y = np.array([float(r["evm_snr_db_mean"]) for r in rows])
    o = np.argsort(x)
    ax.plot(x[o], y[o], color=col, lw=1.9, ls=ls, label=lab, marker="o", ms=2.6)

ax.axvline(0, color=MUTED, lw=0.9)
ax.axhline(0, color="#cbd5e1", lw=0.8, ls=(0,(4,3)))
ax.set_xlabel("timing error  (TA units)", fontsize=9)
ax.set_ylabel("post-equalisation SNR  (dB)", fontsize=9)
ax.set_title("The early/late asymmetry is a receiver setting,\nnot a property of OFDM",
             fontsize=9.3, weight="bold")
ax.text(-14.0, 26, "$\\leftarrow$ late", fontsize=8.5, color=MUTED, weight="bold")
ax.text(9.0, 26, "early $\\rightarrow$", fontsize=8.5, color=MUTED, weight="bold")
ax.legend(fontsize=7.8, loc="lower center", frameon=False, bbox_to_anchor=(0.52, -0.02))
ax.set_xlim(-16, 16); ax.tick_params(labelsize=8)
for s in ("top","right"): ax.spines[s].set_visible(False)
ax.grid(color="#eef2f7", lw=0.7); ax.set_axisbelow(True)

# ------------------------------------------------ panel B : relay capture
bx = fig.add_subplot(gs[1])
for d, col, mk in ((5, GREEN, "o"), (10, AMBER, "s"), (20, RED, "^")):
    pwr, cap = [], []
    for f in sorted(glob.glob(f"{R}/E_relay_d{d}_p*.csv")):
        rows = load(f)
        r = rows[0]
        p = float(r["relay_power_db"])
        # TA unit in ns at this numerology, from the row itself
        mu = int(r["mu"]); ta_ns_unit = 16*64/(2**mu)/(480000*4096)*1e9
        captured = float(r["ta_est_ns_mean"]) / (d * ta_ns_unit) * 100.0
        pwr.append(p); cap.append(captured)
    o = np.argsort(pwr)
    pwr = np.array(pwr)[o]; cap = np.array(cap)[o]
    bx.plot(pwr, cap, color=col, lw=1.9, marker=mk, ms=4.0,
            label=f"relay delay = {d} TA units")

bx.axhline(100, color=GREEN, lw=1.2, ls=(0,(5,3)))
bx.text(19.6, 93, "full capture", fontsize=8, color=GREEN, ha="right", weight="bold")
bx.axhline(0, color=MUTED, lw=0.9)
bx.set_xlabel("relayed path power, relative to the direct path  (dB)", fontsize=9)
bx.set_ylabel("of the relay's delay actually captured  (%)", fontsize=9)
bx.set_title("The relay cannot transfer its own delay\ninto the stored TA", fontsize=9.3,
             weight="bold")
bx.legend(fontsize=7.8, loc="upper left", frameon=False, bbox_to_anchor=(0.02, 0.86))
bx.tick_params(labelsize=8)
for s in ("top","right"): bx.spines[s].set_visible(False)
bx.grid(color="#eef2f7", lw=0.7); bx.set_axisbelow(True)

save(fig, "atk05_sim")
