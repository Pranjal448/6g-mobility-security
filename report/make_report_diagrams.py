#!/usr/bin/env python3
"""Generate the diagrams embedded in the ns-3 LTM work report."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os

OUT = "/run/media/pranjal/hdd/mtp/report_assets"
os.makedirs(OUT, exist_ok=True)

BLUE = "#1f5fae"
GREEN = "#2e8b57"
RED = "#c0392b"
GREY = "#5a5a5a"
LIGHT = "#eef3fb"
LIGHTR = "#fdecea"


def box(ax, x, y, w, h, text, fc, ec, fs=8.5, tc="black"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1.3, edgecolor=ec, facecolor=fc))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, wrap=True)


def arrow(ax, x1, y1, x2, y2, color=GREY, style="-|>", lw=1.6, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=13,
                                 linewidth=lw, color=color, linestyle=ls,
                                 shrinkA=2, shrinkB=2))


# ---------------- Diagram 1: LTM MAC-CE message flow (legit vs forged) ----------------
fig, ax = plt.subplots(figsize=(9.2, 5.4))
ax.set_xlim(0, 12)
ax.set_ylim(0, 8)
ax.axis("off")
ax.text(6, 7.7, "6G LTM cell-switch over the air interface: legitimate command vs. forged injection",
        ha="center", fontsize=11, weight="bold")

# gNB
box(ax, 0.3, 4.6, 2.3, 1.1, "Serving gNB\n(NrGnbPhy)", LIGHT, BLUE, 9)
# air
ax.text(4.7, 6.35, "DL control channel (air)", ha="center", fontsize=8, style="italic", color=GREY)
# UE PHY / MAC / RRC stack
box(ax, 6.7, 4.6, 2.4, 1.1, "UE PHY\n(NrUePhy)", LIGHT, BLUE, 9)
box(ax, 9.4, 4.6, 2.3, 1.1, "UE RRC\n(NrUeRrc)", LIGHT, BLUE, 9)
box(ax, 6.7, 2.6, 5.0, 1.0, "Example: execute switch (reuse nr handover)\nlegit -> fast switch (~2 ms) | forged -> RACH fails -> DoS", "#f4f7fb", GREEN, 8)

# legit arrow gNB -> UE PHY
arrow(ax, 2.6, 5.4, 6.7, 5.4, GREEN, lw=2.0)
ax.text(4.65, 5.62, "SendLtmCellSwitch()\nNrLtmCellSwitchMessage (MAC CE)", ha="center", fontsize=7.3, color=GREEN)
# UE PHY -> RRC
arrow(ax, 9.1, 5.15, 9.4, 5.15, BLUE)
ax.text(9.25, 5.42, "CPHY SAP", ha="center", fontsize=6.8, color=BLUE)
# RRC -> execute (down)
arrow(ax, 10.5, 4.6, 10.5, 3.6, GREY)
ax.text(11.0, 4.1, "trace", ha="left", fontsize=6.8, color=GREY)
# UE PHY -> execute
arrow(ax, 7.9, 4.6, 7.9, 3.6, GREY)

# attacker
box(ax, 6.7, 0.5, 2.4, 1.0, "Attacker SDR\n(overshadow)", LIGHTR, RED, 8.5)
arrow(ax, 7.9, 1.5, 7.9, 4.6, RED, lw=2.0, ls=(0, (4, 2)))
ax.text(6.0, 3.05, "InjectForgedLtmCellSwitch()\n(forged MAC CE at PHY,\nspoofed Target Config ID)",
        ha="center", fontsize=7.3, color=RED)

ax.text(0.3, 0.6, "Green = legitimate path (real air interface)   Red = forged injection at the victim PHY (capture effect)",
        fontsize=7.5, color=GREY)
plt.tight_layout()
plt.savefig(f"{OUT}/flow.png", dpi=170, bbox_inches="tight")
plt.close()

# ---------------- Diagram 2: interruption-time inflation ----------------
fig, ax = plt.subplots(figsize=(9.2, 3.9))
labels = ["Legitimate LTM\ncell-switch\n(control-plane)",
          "Forged switch\ncontrol-plane\noutage",
          "Forged switch\ndata-plane\ninterruption"]
vals = [2.036, 240.0, 262.4]
colors = [GREEN, RED, "#e67e22"]
bars = ax.bar(labels, vals, color=colors, width=0.55, edgecolor="black", linewidth=0.8)
ax.set_ylabel("milliseconds (log scale)")
ax.set_yscale("log")
ax.set_ylim(1, 1000)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v * 1.1, f"{v:.1f} ms", ha="center", fontsize=9, weight="bold")
ax.set_title("Mobility-interruption inflation from a single forged LTM cell-switch (2 gNB / 1 UE / 1 attacker)",
             fontsize=10.5, weight="bold")
ax.text(0.5, 1.4, "~118x", color=RED, fontsize=10, weight="bold")
plt.tight_layout()
plt.savefig(f"{OUT}/inflation.png", dpi=170, bbox_inches="tight")
plt.close()

# ---------------- Diagram 3: capture probability vs margin ----------------
fig, ax = plt.subplots(figsize=(9.2, 3.6))
margin = [0, 1, 2, 3, 4, 6, 8]
p = [0.37, 0.42, 0.46, 0.50, 0.54, 0.63, 0.71]
ax.plot(margin, p, "o-", color=BLUE, lw=2, markersize=6, label="Thesis Section 6 table (link-tier)")
meas_x = [0, 4, 8]
meas_y = [0.50, 0.53, 0.71]
ax.plot(meas_x, meas_y, "s", color=RED, markersize=8, label="Measured in ns-3 (20 seeds/pt)")
ax.set_xlabel("Attacker-to-legitimate power margin (dB)")
ax.set_ylabel("P(forged command decodes)")
ax.set_ylim(0.3, 0.8)
ax.grid(alpha=0.3)
ax.legend(fontsize=8.5, loc="upper left")
ax.set_title("Capture-effect success probability vs. power margin (boundary B2)", fontsize=10.5, weight="bold")
plt.tight_layout()
plt.savefig(f"{OUT}/margin.png", dpi=170, bbox_inches="tight")
plt.close()

print("diagrams written to", OUT)
