import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.08,
})

INK   = "#1a1a1a"
MUTED = "#6b7280"
BOX   = "#ffffff"
EDGE  = "#334155"
BLUE  = "#1d4ed8"
BLUEF = "#dbeafe"
RED   = "#b91c1c"
REDF  = "#fee2e2"
AMBER = "#b45309"
AMBERF= "#fef3c7"
GREEN = "#15803d"
GREENF= "#dcfce7"
GREY  = "#f1f5f9"

def box(ax, x, y, w, h, text, fc=BOX, ec=EDGE, lw=1.1, fs=8.5, weight="normal",
        tc=INK, style="round,pad=0.008,rounding_size=0.014", ha="center", zorder=3):
    p = FancyBboxPatch((x, y), w, h, boxstyle=style, linewidth=lw,
                       edgecolor=ec, facecolor=fc, zorder=zorder, clip_on=False)
    ax.add_patch(p)
    tx = x + w/2 if ha == "center" else x + 0.012
    ax.text(tx, y + h/2, text, ha=ha, va="center", fontsize=fs,
            color=tc, weight=weight, zorder=zorder+1, linespacing=1.35)
    return p

def arrow(ax, p0, p1, color=EDGE, lw=1.1, style="-|>", ls="-", rad=0.0, zorder=4):
    a = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=11,
                        linewidth=lw, color=color, linestyle=ls,
                        connectionstyle=f"arc3,rad={rad}",
                        shrinkA=1.5, shrinkB=2.5, zorder=zorder, clip_on=False)
    ax.add_patch(a)
    return a

def label(ax, x, y, t, fs=7.6, color=MUTED, ha="center", va="center", weight="normal",
          style="normal", mask=False, zorder=6):
    bbox = dict(facecolor="white", edgecolor="none", pad=0.9) if mask else None
    ax.text(x, y, t, fontsize=fs, color=color, ha=ha, va=va, weight=weight, style=style,
            bbox=bbox, zorder=zorder, linespacing=1.3)

def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax

def save(fig, name):
    import os
    for d, ext in (("/home/pranjal/mtp_report/report/figures", "pdf"),
                   ("/home/pranjal/mtp_report/figpng", "png")):
        os.makedirs(d, exist_ok=True)
        fig.savefig(f"{d}/{name}.{ext}", dpi=220)
    plt.close(fig)
    print("wrote", name)
