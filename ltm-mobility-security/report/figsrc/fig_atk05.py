import sys; sys.path.insert(0, "/home/pranjal/mtp_report/figsrc")
from common import *
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

fig = plt.figure(figsize=(9.4, 3.8))
gs  = GridSpec(1, 2, width_ratios=[1.12, 1.0], wspace=0.14, figure=fig)

# ------------------------------------------------- panel A : geometry
ax = fig.add_subplot(gs[0]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

box(ax, 0.02, 0.60, 0.17, 0.11, "UE", fc=GREY, fs=10, weight="bold")
box(ax, 0.78, 0.60, 0.20, 0.11, "candidate\ncell", fc=GREY, fs=9.5, weight="bold")
box(ax, 0.40, 0.17, 0.21, 0.11, "RELAY", fc=REDF, ec=RED, fs=9.5, weight="bold", tc=RED)

arrow(ax, (0.195, 0.655), (0.775, 0.655), color=GREEN, lw=1.6)
label(ax, 0.485, 0.695, "direct path — true distance", fs=8.2, color=GREEN,
      weight="bold", mask=True)

arrow(ax, (0.165, 0.605), (0.405, 0.285), color=RED, lw=1.5, ls=(0,(4,2)))
arrow(ax, (0.608, 0.285), (0.858, 0.592), color=RED, lw=1.5, ls=(0,(4,2)))
label(ax, 0.505, 0.095, "receive, delay by $\\tau$, retransmit", fs=8.2, color=RED,
      weight="bold")

label(ax, 0.50, 0.455, "the relay ADDS a path.\nIt does not remove the direct one.",
      fs=8.4, color=INK, weight="bold", mask=True)

# ------------------------------------------------- panel B : detector
bx = fig.add_subplot(gs[1])
t = np.linspace(-1, 9, 1400)

def peak(t, t0, a, w=0.26):
    return a*np.exp(-0.5*((t-t0)/w)**2)

direct  = peak(t, 1.6, 0.52)
relayed = peak(t, 5.4, 1.00)
bx.fill_between(t, 0, direct,  color=GREEN, alpha=0.22)
bx.fill_between(t, 0, relayed, color=RED,   alpha=0.20)
bx.plot(t, direct,  color=GREEN, lw=1.6)
bx.plot(t, relayed, color=RED,   lw=1.8)

bx.axhline(0.66, color=MUTED, lw=1.2, ls=(0,(5,3)))
bx.text(8.9, 0.70, "detector threshold", fontsize=8, color=MUTED, ha="right")

bx.annotate("", xy=(1.6, -0.13), xytext=(5.4, -0.13),
            arrowprops=dict(arrowstyle="<|-|>", color=AMBER, lw=1.6))
bx.text(3.5, -0.235, "inflated round trip  $\\Rightarrow$  stored TA too large",
        fontsize=8.6, color=AMBER, weight="bold", ha="center")

bx.text(1.6, 0.56, "direct\n(below threshold)", fontsize=8.2, color=GREEN, ha="center",
        va="bottom", weight="bold")
bx.text(5.4, 1.05, "relayed\n(detected)", fontsize=8.2, color=RED, ha="center",
        va="bottom", weight="bold")

bx.set_ylabel("correlator output", fontsize=9)
bx.set_title("The candidate measures whatever it detects\nin that preamble occasion",
             fontsize=9.2, weight="bold")
bx.set_xlim(-0.6, 9.4); bx.set_ylim(-0.40, 1.34)
bx.set_yticks([]); bx.set_xticks([])
for s in ("top","right","left"): bx.spines[s].set_visible(False)
bx.spines["bottom"].set_position(("data", 0))

save(fig, "atk05_relay")
