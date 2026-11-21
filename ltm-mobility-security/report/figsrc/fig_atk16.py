import sys; sys.path.insert(0, "/home/pranjal/mtp_report/figsrc")
from common import *

fig, ax = canvas(8.8, 6.4)
P = 0.008                                  # boxstyle pad, in axes units
L, CW  = 0.040, 0.450
CW2    = 0.520
R, RW  = 0.600, 0.340
cx, cx2 = L + CW/2, L + CW2/2
AX     = 0.610

def vlink(y0, y1, x=None, color=EDGE, lw=1.1, tag=None, tagcol=MUTED):
    x = cx if x is None else x
    arrow(ax, (x, y0), (x, y1), color=color, lw=lw)
    if tag:
        label(ax, x - 0.016, (y0+y1)/2, tag, fs=7.4, color=tagcol, ha="right")

box(ax, L, 0.915, CW, 0.068,
    "Pending Scheduling Request\nMAC entity — TS 38.321 §5.4.4", fc=GREY, fs=9.5, weight="bold")
vlink(0.915-P, 0.868+P)

box(ax, L, 0.770, CW, 0.098,
    "$\\bf{1>}$  no valid PUCCH for the SR   $\\bf{and}$\n"
    "$\\bf{\\ \\ \\ \\ \\ }$  no ongoing RACH-less LTM switch   $\\bf{and}$\n"
    "$\\bf{\\ \\ \\ \\ \\ }$  rach-LessHO not configured",
    fc=AMBERF, ec=AMBER, fs=8.2, ha="left")

box(ax, R, 0.790, RW, 0.058,
    "$\\bf{2>}$ initiate Random Access,\n$\\bf{\\ \\ \\ \\ \\ }$ cancel the pending SR",
    fc=REDF, ec=RED, fs=8.2, ha="left", tc=RED)
arrow(ax, (L+CW+P, 0.819), (R-P, 0.819), color=RED)
label(ax, (L+CW+R)/2, 0.837, "true", fs=7.4, color=RED)
label(ax, R-P, 0.745, "✗  FALLBACK 1 — unreachable during\n     a RACH-less LTM cell switch",
      fs=7.9, color=RED, weight="bold", ha="left")

vlink(0.770-P, 0.720+P, tag="false")
box(ax, L, 0.660, CW, 0.060,
    "$\\bf{1>}$ $\\bf{else}$ — SR transmission occasion\n$\\bf{\\ \\ \\ \\ \\ }$ on a valid PUCCH resource",
    fc=BLUEF, ec=BLUE, fs=8.2, ha="left")

vlink(0.660-P, 0.610+P)
box(ax, L, 0.552, CW, 0.058,
    "$\\bf{4>}$  SR_COUNTER  $<$  sr-TransMax ?", fc=GREY, fs=9, ha="left", weight="bold")

box(ax, R, 0.520, RW, 0.092,
    "$\\bf{5>}$ signal SR on the PUCCH resource\n"
    "$\\bf{6>}$ SR_COUNTER += 1\n"
    "$\\bf{6>}$ start sr-ProhibitTimer",
    fc=GREENF, ec=GREEN, fs=8.2, ha="left")
arrow(ax, (L+CW+P, 0.566), (R-P, 0.566), color=GREEN)
label(ax, (L+CW+R)/2, 0.584, "yes", fs=7.4, color=GREEN)
arrow(ax, (R+0.03, 0.612+P), (cx+0.075, 0.610+P), color=GREEN, rad=0.40, ls=(0,(4,2)))
label(ax, R-P, 0.650, "retry until the counter is exhausted", fs=7.4,
      color=GREEN, style="italic", ha="left")

vlink(0.552-P, 0.495+P, color=RED, lw=1.5, tag="no", tagcol=RED)
box(ax, L, 0.295, CW2, 0.200,
    "$\\bf{4>}$  $\\bf{else}$   (counter exhausted)\n\n"
    "$\\bf{\\ \\ }$ $\\bf{5>}$ notify RRC to release PUCCH — all serving cells\n"
    "$\\bf{\\ \\ }$ $\\bf{5>}$ notify RRC to release SRS — all serving cells\n"
    "$\\bf{\\ \\ }$ $\\bf{5>}$ clear all DL assignments and UL grants\n"
    "$\\bf{\\ \\ }$ $\\bf{5>}$ clear SP-CSI PUSCH resources",
    fc=REDF, ec=RED, lw=1.6, fs=8.2, ha="left")
label(ax, AX, 0.395, "No condition stands between\nthe $\\bf{else}$ and these four actions.\nThe UE strips its own uplink\nunconditionally.",
      fs=7.9, color=RED, weight="bold", ha="left")

vlink(0.295-P, 0.243+P, color=RED, lw=1.5, x=cx2)
box(ax, L, 0.145, CW2, 0.095,
    "$\\bf{\\ \\ }$ $\\bf{5>}$ $\\bf{if}$ rach-LessHO not configured $\\bf{and}$\n"
    "$\\bf{\\ \\ \\ \\ \\ \\ \\ \\ \\ }$ no ongoing RACH-less LTM switch:\n"
    "$\\bf{\\ \\ \\ \\ }$ $\\bf{6>}$ initiate Random Access, cancel all SRs",
    fc=AMBERF, ec=AMBER, fs=8.2, ha="left")
label(ax, AX, 0.192, "✗  FALLBACK 2\n     also unreachable", fs=7.9,
      color=RED, weight="bold", ha="left")

vlink(0.145-P, 0.098+P, color=RED, lw=1.8, x=cx2)
box(ax, L+0.040, 0.022, 0.440, 0.070,
    "DEADLOCK\nno PUCCH  ·  no grant  ·  no random access",
    fc=RED, ec=RED, fs=9, weight="bold", tc="white")

save(fig, "atk16_deadlock")
