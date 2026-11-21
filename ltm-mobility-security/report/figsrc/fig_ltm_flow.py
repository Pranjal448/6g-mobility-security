import sys; sys.path.insert(0, "/home/pranjal/mtp_report/figsrc")
from common import *

fig, ax = canvas(8.6, 5.4)

lanes = [(0.105, "UE"), (0.455, "Serving cell\n(source DU)"), (0.820, "Candidate cell\n(target DU)")]
TOP, BOT = 0.885, 0.065

for x, name in lanes:
    box(ax, x-0.105, TOP, 0.210, 0.062, name, fc=GREY, fs=9, weight="bold")
    ax.plot([x, x], [BOT, TOP-0.010], color=MUTED, lw=0.9, ls=(0, (3, 3)), zorder=1)

UE, SRV, CAND = lanes[0][0], lanes[1][0], lanes[2][0]

def msg(y, x0, x1, text, color=EDGE, ls="-", fs=8.0, dy=0.021, weight="normal"):
    arrow(ax, (x0, y), (x1, y), color=color, lw=1.2, ls=ls)
    label(ax, (x0+x1)/2, y+dy, text, fs=fs, color=color, weight=weight, mask=True, zorder=3)

def phase(y, text, color=MUTED):
    ax.plot([0.012, 0.988], [y, y], color="#e2e8f0", lw=0.8, zorder=0)
    label(ax, 0.012, y+0.022, text, fs=7.6, color=color, ha="left", weight="bold", mask=True)

phase(0.815, "PREPARATION")
msg(0.775, SRV, CAND, "candidate preparation  (F1AP / Xn)", fs=7.9)
msg(0.715, SRV, UE, "RRC: up to 8 LTM candidate configurations, stored by the UE", fs=7.9)

phase(0.655, "MONITORING")
msg(0.615, UE, SRV, "L1-RSRP measurement reports  (lower-layer, no RRC)", fs=7.9)

phase(0.545, "EARLY TIMING-ADVANCE ACQUISITION   (optional — studied in Chapter 3)")
msg(0.500, SRV, UE, "PDCCH order — send a preamble to the candidate", fs=7.9, color=BLUE)
msg(0.440, UE, CAND, "PRACH preamble", fs=7.9, color=BLUE)
msg(0.380, CAND, SRV, "measured TA for the candidate cell", fs=7.9, color=BLUE)
box(ax, SRV-0.150, 0.300, 0.300, 0.050,
    "TA held at the source gNB\nvalidity is implementation-dependent",
    fc=BLUEF, ec=BLUE, fs=7.8)

phase(0.272, "EXECUTION")
msg(0.196, SRV, UE, "LTM Cell Switch Command MAC CE\n3-bit candidate index + 12-bit TA command",
    fs=8.2, color=RED, weight="bold", dy=0.044)
box(ax, UE-0.093, 0.112, 0.196, 0.052,
    "apply stored config\n+ TA from the command", fc=AMBERF, ec=AMBER, fs=7.8)
msg(0.070, UE, CAND, "uplink transmission  —  RACH-less, no random access", fs=8.0, color=GREEN,
    weight="bold")

label(ax, 0.988, 0.016, "No integrity protection on the MAC CE  ·  no random access to fall back on",
      fs=7.8, color=RED, ha="right", weight="bold", style="italic")

save(fig, "ltm_flow")
