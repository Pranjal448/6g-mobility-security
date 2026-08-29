#!/usr/bin/env python3
"""Build the ns-3 6G LTM forged-handover work report (PDF, reportlab)."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table,
                                TableStyle, Image, HRFlowable, ListFlowable, ListItem)
import html as _html

OUT = "/run/media/pranjal/hdd/mtp/NS3_LTM_Forged_Handover_Report.pdf"
ASSETS = "/run/media/pranjal/hdd/mtp/report_assets"

BLUE = colors.HexColor("#1f5fae")
DARK = colors.HexColor("#16324f")
GREEN = colors.HexColor("#2e8b57")
RED = colors.HexColor("#c0392b")
GREY = colors.HexColor("#444444")
CODEBG = colors.HexColor("#f4f6f8")
CODEBORDER = colors.HexColor("#cdd5dd")
TBLHDR = colors.HexColor("#1f5fae")
TBLALT = colors.HexColor("#eef3fb")

ss = getSampleStyleSheet()
styles = {}
styles["title"] = ParagraphStyle("title", parent=ss["Title"], fontSize=22, leading=26, textColor=DARK, spaceAfter=6)
styles["subtitle"] = ParagraphStyle("subtitle", fontSize=12.5, leading=17, textColor=BLUE, alignment=TA_CENTER, spaceAfter=4)
styles["meta"] = ParagraphStyle("meta", fontSize=9.5, leading=13, textColor=GREY, alignment=TA_CENTER)
styles["h1"] = ParagraphStyle("h1", fontSize=15.5, leading=19, textColor=colors.white, backColor=BLUE,
                              borderPadding=(5, 6, 5, 6), spaceBefore=14, spaceAfter=9, leftIndent=0)
styles["h2"] = ParagraphStyle("h2", fontSize=12.5, leading=16, textColor=DARK, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold")
styles["h3"] = ParagraphStyle("h3", fontSize=10.8, leading=14, textColor=BLUE, spaceBefore=7, spaceAfter=3, fontName="Helvetica-Bold")
styles["body"] = ParagraphStyle("body", fontSize=9.7, leading=13.6, alignment=TA_JUSTIFY, spaceAfter=5, textColor=colors.HexColor("#1a1a1a"))
styles["bodyl"] = ParagraphStyle("bodyl", parent=styles["body"], alignment=TA_LEFT)
styles["bullet"] = ParagraphStyle("bullet", fontSize=9.6, leading=13.2, alignment=TA_LEFT, textColor=colors.HexColor("#1a1a1a"))
styles["code"] = ParagraphStyle("code", fontName="Courier", fontSize=8.1, leading=10.6, textColor=colors.HexColor("#12233a"),
                                backColor=CODEBG, borderColor=CODEBORDER, borderWidth=0.7, borderPadding=(5, 6, 5, 6), spaceAfter=6, spaceBefore=2)
styles["caption"] = ParagraphStyle("caption", fontSize=8.4, leading=11, textColor=GREY, alignment=TA_CENTER, spaceAfter=8, spaceBefore=2)
styles["tcell"] = ParagraphStyle("tcell", fontSize=8.6, leading=11.3, textColor=colors.HexColor("#1a1a1a"))
styles["tcellb"] = ParagraphStyle("tcellb", fontSize=8.6, leading=11.3, textColor=colors.white, fontName="Helvetica-Bold")
styles["note"] = ParagraphStyle("note", fontSize=9.3, leading=12.8, alignment=TA_LEFT, textColor=colors.HexColor("#4a3000"),
                                backColor=colors.HexColor("#fff8e6"), borderColor=colors.HexColor("#e6c34a"),
                                borderWidth=0.8, borderPadding=(6, 7, 6, 7), spaceAfter=7, spaceBefore=2)


_ENTS = {"&mdash;": "—", "&ndash;": "–", "&rsquo;": "’", "&lsquo;": "‘",
         "&ldquo;": "“", "&rdquo;": "”", "&minus;": "−", "&plusmn;": "±",
         "&ge;": "≥", "&le;": "≤", "&nbsp;": " ", "&bull;": "•", "&times;": "×"}

def esc(t):
    s = str(t)
    for k, v in _ENTS.items():
        s = s.replace(k, v)
    return _html.escape(s)


story = []


def H1(t): story.append(Paragraph(esc(t), styles["h1"]))
def H2(t): story.append(Paragraph(esc(t), styles["h2"]))
def H3(t): story.append(Paragraph(esc(t), styles["h3"]))
def P(t): story.append(Paragraph(t, styles["body"]))  # allow inline markup
def PL(t): story.append(Paragraph(t, styles["bodyl"]))
def SP(h=5): story.append(Spacer(1, h))
def NOTE(t): story.append(Paragraph(t, styles["note"]))


def CODE(lines):
    txt = "<br/>".join(esc(l).replace(" ", "&nbsp;") for l in lines)
    story.append(Paragraph(txt, styles["code"]))


def BULLETS(items):
    lf = ListFlowable(
        [ListItem(Paragraph(it, styles["bullet"]), leftIndent=10, value="•") for it in items],
        bulletType="bullet", start="•", leftIndent=14, bulletColor=BLUE)
    story.append(lf)
    SP(4)


def TABLE(rows, colw, hdr=True, caption=None, fs=8.6):
    data = []
    for ridx, r in enumerate(rows):
        cells = []
        for c in r:
            st = styles["tcellb"] if (hdr and ridx == 0) else styles["tcell"]
            cells.append(Paragraph(esc(c), st))
        data.append(cells)
    t = Table(data, colWidths=colw, repeatRows=1 if hdr else 0)
    cmds = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, CODEBORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if hdr:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), TBLHDR))
        for r in range(2, len(rows), 2):
            cmds.append(("BACKGROUND", (0, r), (-1, r), TBLALT))
    else:
        for r in range(1, len(rows), 2):
            cmds.append(("BACKGROUND", (0, r), (-1, r), TBLALT))
    t.setStyle(TableStyle(cmds))
    story.append(t)
    if caption:
        story.append(Paragraph(esc(caption), styles["caption"]))
    else:
        SP(6)


from reportlab.lib.utils import ImageReader

def IMG(name, w, caption=None):
    iw, ih = ImageReader(f"{ASSETS}/{name}").getSize()
    story.append(Image(f"{ASSETS}/{name}", width=w, height=w * ih / iw))
    if caption:
        story.append(Paragraph(esc(caption), styles["caption"]))


# ============================ TITLE PAGE ============================
SP(60)
story.append(Paragraph("Modelling a Forged 6G LTM Cell-Switch Attack in ns-3 / 5G-LENA", styles["title"]))
SP(4)
story.append(Paragraph("An unauthenticated Layer-2 mobility-command forgery and its measured denial-of-service", styles["subtitle"]))
SP(20)
IMG("flow.png", 165 * mm)
SP(16)
story.append(Paragraph("System-level implementation report and technical walkthrough", styles["meta"]))
story.append(Paragraph("ns-3.48 &nbsp;+&nbsp; 5G-LENA (nr) v5.1 &nbsp;&bull;&nbsp; scenario + attacker + real air-interface LTM MAC CE in nr core", styles["meta"]))
SP(8)
story.append(Paragraph("Prepared for supervisor review &bull; 2026-08-28", styles["meta"]))
story.append(PageBreak())

# ============================ EXEC SUMMARY ============================
H1("Executive summary")
P("This report documents, from the beginning, the ns-3 work built to reproduce the attack of the "
  "M.Tech thesis <i>&ldquo;Detecting Forged Handovers &mdash; a measured attack on the 6G L2 cell-switch "
  "command.&rdquo;</i> The thesis observes that 5G-Advanced / 6G <b>Lower-layer Triggered Mobility (LTM)</b> "
  "delivers the cell-switch command as a <b>MAC Control Element (MAC CE)</b> &mdash; a Layer-2 frame that sits "
  "below PDCP and therefore carries <b>no integrity protection and no ciphering</b>. An attacker with a "
  "commodity SDR can forge this command by overshadowing (the capture effect), forcing one target UE to "
  "mis-switch to a wrong cell, producing a radio-link failure, an RRC re-establishment, and a "
  "denial-of-service interruption far above the near-zero intra-base-station budget.")
P("We have built a working system-level model of this attack in ns-3 with the CTTC 5G-LENA <font face='Courier'>nr</font> "
  "module. The deliverable to date is a single, self-contained, reproducible simulation program plus a set of "
  "additive changes to the <font face='Courier'>nr</font> core that add a genuine 6G LTM cell-switch as an "
  "unauthenticated MAC Control Element on the real air interface.")
H3("Headline results (all produced by real simulation runs, not asserted)")
BULLETS([
  "A <b>legitimate</b> LTM cell-switch, delivered as a MAC CE on the downlink control channel, completes in "
  "<b>~2.0 ms</b> &mdash; the near-zero intra-base-station interruption LTM exists to provide.",
  "A <b>single forged</b> LTM cell-switch, injected at the victim PHY, inflates the interruption to "
  "<b>~240 ms</b> (control plane) / <b>~262 ms</b> (data plane) &mdash; a two-orders-of-magnitude "
  "denial-of-service on the exact KPI 6G is optimising.",
  "The forged-command success probability tracks the thesis&rsquo; link-tier table across power margins "
  "(measured 0.71 at 8&nbsp;dB vs. table 0.71).",
  "The attack is <b>unicast and single-UE</b> (targeted, stealthy) and needs <b>no keys, no core access, "
  "no node compromise.</b>",
])
H3("Status at a glance")
TABLE([
  ["Component", "Status"],
  ["ns-3.48 + 5G-LENA nr v5.1 toolchain and build", "Done, verified"],
  ["Urban multi-cell scenario (configurable, with real beamforming)", "Done, verified"],
  ["LTM-style fast cell-switch + near-zero baseline interruption", "Done, verified (~2 ms)"],
  ["RLF / handover-failure / RRC re-establishment tracing + outage timing", "Done, verified"],
  ["Link-tier margin -> P(forge-decode) table (thesis Section 6) + unit check", "Done, verified"],
  ["Attacker forged-injection logic driven by that table", "Done, verified"],
  ["Real air-interface LTM cell-switch MAC CE in nr core + PHY-level forgery", "Done, verified"],
  ["Large-scale measurement campaign, statistics, plots, defence", "Deferred (out of current scope)"],
], [95 * mm, 70 * mm])
story.append(PageBreak())

# ============================ CH 1 ============================
H1("1. The problem and what we are modelling")
H2("1.1 The vulnerability")
P("In 5G-Advanced, the lowest-latency handover is <b>Lower-layer Triggered Mobility (LTM)</b>. Instead of "
  "commanding the cell switch with an integrity-protected RRC message (as classical handover does), LTM "
  "delivers it as a <b>MAC Control Element</b> &mdash; a Layer-2 frame below PDCP. That trade buys latency "
  "(no RRC round-trip) at the cost of protection: the command carries no MAC-I integrity tag and no ciphering. "
  "It is <b>unicast</b> (there is no quorum to break), <b>below PDCP</b> (there is nothing to decrypt) and "
  "<b>unverified</b> (there is nothing to fail). The UE acts on it essentially immediately.")
H2("1.2 The attacker and the goal")
P("The adversary is a commodity SDR (srsRAN / Amarisoft class) that can decode the downlink control channel in "
  "real time and inject a symbol-synchronised, cyclic-prefix-aligned frame a few dB above the legitimate "
  "signal &mdash; the <b>capture effect</b>, not a power race. The attacker is co-located with the target "
  "(angularly identical to the UE, defeating beam separation) or stands off on a wider control-channel beam. "
  "The goal is a <b>targeted, stealthy, single-UE denial of service:</b> force one UE to mis-switch to a wrong "
  "or non-existent cell, producing radio-link failure and re-establishment &mdash; without the mass "
  "RACH-failure footprint that aggregate detectors watch for.")
H2("1.3 The thesis&rsquo; two-tier methodology and where ns-3 sits")
P("The thesis is explicitly a <b>two-tier</b> study. A <b>link-tier</b> model (MATLAB 5G Toolbox) characterises "
  "the RF overshadow / capture step and produces a single number: the probability that a forged command "
  "decodes, as a function of the attacker-to-legitimate power margin. A <b>system-tier</b> model (ns-3 + "
  "5G-LENA) then models the multi-cell mobility scenario and injects the <i>consequence</i> of a forged command "
  "that lands with that probability, measuring the denial-of-service and mobility impact. <b>Our work is the "
  "system tier.</b> Two modelling boundaries follow directly from this split and are stated throughout:")
BULLETS([
  "<b>Boundary B1 &mdash; 6G is not in ns-3.</b> 6G NR is modelled as NR (5G-LENA); the attack targets the "
  "unauthenticated MAC-CE trigger, which we implement natively (Chapter 7).",
  "<b>Boundary B2 &mdash; the RF capture effect is not simulated in ns-3.</b> It enters only as the "
  "link-tier success probability (thesis Section 6); ns-3 plays out the mobility / DoS consequence, not the "
  "radio-frequency overshadow waveform.",
])
NOTE("<b>Scope note.</b> The user narrowed the immediate goal to an accurate <b>small-scale</b> attack model "
     "(one attacker, one victim UE, two base stations, real beamforming and a real LTM cell-switch). The "
     "large-scale measurement campaign (many cells / many UEs, statistics, plots) and the thesis&rsquo; "
     "non-cryptographic <i>defence</i> are explicitly out of the current scope and are listed under "
     "&ldquo;what remains&rdquo; (Chapter 11).")
story.append(PageBreak())

# ============================ CH 2 ============================
H1("2. Environment, toolchain and build")
H2("2.1 Software stack")
TABLE([
  ["Component", "Version / choice", "Notes"],
  ["ns-3", "ns-3.48", "System-level discrete-event simulator"],
  ["5G-LENA (nr module)", "v5.1", "CTTC NR module; v5.1 is the matched pair for ns-3.48"],
  ["Compiler / build", "g++ 15.2, CMake 4.2, Ninja", "optimized build (-d optimized)"],
  ["Python", "3.14 venv", "numpy / pandas / matplotlib / scipy for orchestration & this report"],
  ["Location", "/run/media/pranjal/hdd/mtp", "Everything lives on the 1&nbsp;TB HDD"],
], [42 * mm, 45 * mm, 78 * mm])
P("The thesis names &ldquo;ns-3.40+&rdquo; as an example; we use the newest matched release (ns-3.48 + nr v5.1) "
  "because the host toolchain (g++ 15.2) is far newer than ns-3.40 supports. This is within the thesis&rsquo; "
  "stated requirement.")
H2("2.2 What was installed and verified")
P("Build dependencies (build-essential, CMake, Ninja, libsqlite3, libeigen3, libgsl, ccache) were installed; "
  "<font face='Courier'>ns-3-dev</font> was cloned at tag <font face='Courier'>ns-3.48</font> and the "
  "<font face='Courier'>nr</font> module at tag <font face='Courier'>v5.1</font> into "
  "<font face='Courier'>contrib/nr</font>. The stack was verified end-to-end by building and running the "
  "stock <font face='Courier'>cttc-nr-demo</font> example, which produced real FlowMonitor throughput "
  "(Flow&nbsp;1 ~10.2&nbsp;Mbps, Flow&nbsp;2 ~102.2&nbsp;Mbps, sub-millisecond delays) &mdash; confirming the "
  "NR stack, 3GPP channel model and beamforming all run correctly before any of our code was added.")
H2("2.3 Directory map")
CODE([
  "mtp/",
  "  THESIS_ATTACK_SPEC.md      # extracted, authoritative attack spec (what to build)",
  "  PLAN.md                    # 18-step plan + scope-change + deviations log",
  "  changes.txt                # detailed running change-log (every step)",
  "  ns-3-dev/                  # ns-3.48 tree",
  "    contrib/nr/              # 5G-LENA nr v5.1 (LTM MAC CE added to core; see Ch.7)",
  "      model/                 # 9 core files modified for LTM",
  "      examples/",
  "        ltm-forged-handover.cc   # THE scenario + attacker (1395 lines, 27 CLI args)",
  "  venv/                      # python venv (orchestration + this report)",
])
story.append(PageBreak())

# ============================ CH 3 ============================
H1("3. The ns-3 scenario")
P("The whole scenario and attacker live in one program, "
  "<font face='Courier'>contrib/nr/examples/ltm-forged-handover.cc</font> (1395 lines, 27 command-line "
  "arguments). It is built and run through the nr module&rsquo;s own build system, so it links against the "
  "real NR PHY/MAC/RRC stack.")
H2("3.1 Topology and radio")
TABLE([
  ["Parameter", "Value"],
  ["Deployment", "Urban grid of gNBs, 250 m inter-site distance"],
  ["Carrier", "4 GHz, 20 MHz bandwidth, numerology 1, single band / CC / BWP"],
  ["Channel model", "3GPP UMa (Urban Macro), shadowing disabled for determinism"],
  ["gNB antenna / power", "4x8 planar array, 43 dBm; ideal beamforming (DirectPath)"],
  ["UE antenna / mobility", "1x1; constant-speed distance-mode random walk (crosses cell edges)"],
  ["Core / traffic", "EPC + remote host; per-UE downlink (and optional uplink) UDP bearers, FlowMonitor"],
], [42 * mm, 123 * mm])
P("<b>Beamforming is real, not a stub:</b> the gNB uses a 4x8 antenna array with 5G-LENA&rsquo;s "
  "<font face='Courier'>IdealBeamformingHelper</font> and <font face='Courier'>DirectPathBeamforming</font> "
  "over the 3GPP UMa channel. The beam direction tracks UE geometry. (One fidelity limit, inherited from the "
  "baseline scenario, is that the fast-fading channel <i>matrix</i> is cached at the UE&rsquo;s initial "
  "position; the beam direction still updates. See Chapter 10.)")
H2("3.2 Command-line parameters (selected)")
TABLE([
  ["Argument", "Meaning / default"],
  ["--numCells / --numUes", "gNB count / UE count (small-scale demo: 2 / 1)"],
  ["--ueSpeedKmph", "UE speed (3 / 30 / 60 / 120)"],
  ["--simTime, --rngSeed, --rngRun", "duration and deterministic seeding (reproducible)"],
  ["--timeToTriggerMs", "A3-like time-to-trigger, default 320 ms (thesis operating point)"],
  ["--attackEnabled, --numAttackers", "master attack switch; number of targeted victim UEs"],
  ["--overshadowMarginDb", "attacker power margin (0..8 dB); indexes the Section-6 table"],
  ["--attackForceTimeMs", "force one attack opportunity at a fixed time (deterministic demo)"],
  ["--t310Ms / --n310 / --n311", "3GPP radio-link-failure timers / counters"],
  ["--printForgeTable", "unit-check the Section-6 probability table, then exit"],
], [55 * mm, 110 * mm])
story.append(PageBreak())

# ============================ CH 4 ============================
H1("4. How it was built, step by step (baseline)")
P("The implementation followed an 18-step plan; the steps relevant to the delivered small-scale attack are "
  "summarised below. Each was executed and independently verified before the next.")
H2("Step 1&ndash;2 &mdash; Toolchain, clone, build, verify")
P("Installed dependencies; cloned ns-3.48 + nr v5.1; configured and built; verified with the stock "
  "<font face='Courier'>cttc-nr-demo</font> (real throughput output). Recon confirmed the nr module exposes "
  "the handover, RLF and control-message hooks the later steps would need.")
H2("Step 3 &mdash; Scenario skeleton")
P("Created <font face='Courier'>ltm-forged-handover.cc</font>: the urban grid, UE mobility, per-UE UDP "
  "bearers, FlowMonitor and the full CLI. Verified that UEs associate to real cells and genuinely traverse "
  "cell edges (a UE&rsquo;s nearest-gNB index changes over time).")
H2("Step 4 &mdash; LTM-style fast switch + near-zero baseline")
P("Implemented the mobility trigger: a periodic <b>A3-like checker</b> (<font face='Courier'>HandoverCheck</font>) "
  "that, when a neighbour is closer than the serving cell by a hysteresis <i>sustained for the 320 ms "
  "time-to-trigger</i>, causes a fast cell switch. Instrumented two interruption metrics: the "
  "<b>cell-switch execution time</b> (HandoverEndOk &minus; HandoverStart) and the <b>data-plane gap</b> "
  "(last good downlink packet before &rarr; first restored after). The no-attack baseline cell-switch "
  "execution time measured <b>2.036 ms</b> &mdash; matching the thesis&rsquo; ~1&ndash;2 ms intra-base-station "
  "LTM budget. This was reproduced independently and matched bit-for-bit.")
TABLE([
  ["Baseline metric (4 cells, 8 UEs, 120 km/h, 10 s)", "Value"],
  ["Handover events / failures", "5 / 0"],
  ["Cell-switch execution time (mean)", "2.036 ms (deterministic)"],
  ["Downlink data-plane gap (mean / p95)", "14.0 ms / 31.1 ms"],
], [110 * mm, 55 * mm])
story.append(PageBreak())

# ============================ CH 5 ============================
H1("5. Step 5 &mdash; RLF, handover failure and re-establishment")
P("Step 5 makes a forged mis-switch <b>deliberately and reliably</b> produce a failure &rarr; RRC "
  "re-establishment outage, and times it. The RRC state machine is traced precisely: entry to "
  "<font face='Courier'>CONNECTED_PHY_PROBLEM</font> marks the outage onset, and the return to "
  "<font face='Courier'>CONNECTED_NORMALLY</font> marks recovery; the interval is the failure outage.")
H2("5.1 An honest debugging story")
P("The originally-scaffolded failure mechanism displaced the victim into &ldquo;coverage loss&rdquo; so "
  "nr&rsquo;s radio-link monitoring would emit out-of-sync indications and trip the 3GPP RLF chain "
  "(out-of-sync &rarr; N310 &rarr; T310 &rarr; RadioLinkFailure). <b>It did not fire in this scenario.</b> "
  "The following were each tested on real runs and ruled out as the cause: the RLF timers (N310/N311/T310, "
  "including 1/1/1000 ms), the channel-<i>condition</i> update period, the channel-<i>matrix</i> update "
  "period, the displacement distance (1.5&ndash;20 km), and the MAC scheduler. nr&rsquo;s own radio-link-failure "
  "test triggers RLF with an identical position jump, but reproducing it here would require porting "
  "nr&rsquo;s entire RLF-test scenario configuration and would perturb the validated beamforming / handover "
  "scenario.")
H2("5.2 The 3GPP-faithful mechanism adopted")
P("Per the supervisor&rsquo;s steer (&ldquo;use whatever is more realistic and accurate per the thesis and "
  "6G/3GPP&rdquo;), the failure is realised with nr&rsquo;s <b>own handover-failure machinery</b> "
  "(<font face='Courier'>test/nr-test-handover-failure.cc</font>). A forged cell-switch names a real "
  "neighbour cell as the (wrong) target; that target&rsquo;s random-access preambles are dropped "
  "(<font face='Courier'>TestDropRachPreambles</font>), so the UE exhausts "
  "<font face='Courier'>PreambleTransMax</font> &rarr; a <b>DURING_HANDOVER failure</b> "
  "(<font face='Courier'>HandoverFailureMaxRach</font>) &rarr; RRC re-establishment (cell search + reconnect) "
  "on a reachable cell. This is the emergent 3GPP failure&ndash;recovery path, and it is the faithful model of "
  "a mis-switch to a target the UE cannot complete access to (a spoofed Target Configuration ID). "
  "A trial with a truly non-existent cell id was rejected: nr null-dereferences the missing target gNB and "
  "segmentation-faults.")
TABLE([
  ["Failure-path outcome (2 gNB, 1 UE, forced trigger)", "Value"],
  ["Handover failures / recoveries", "1 / 1"],
  ["Control-plane outage (recovery - onset)", "240.0 ms"],
  ["Data-plane interruption (last good DL -> first restored DL)", "262.4 ms"],
], [115 * mm, 50 * mm])
story.append(PageBreak())

# ============================ CH 6 ============================
H1("6. Steps 8&ndash;9 &mdash; link-tier table and attacker injection")
H2("6.1 Step 8 &mdash; the Section-6 capture-probability table")
P("The only place the RF capture effect enters the model (boundary B2). "
  "<font face='Courier'>PForgeDecode(margin)</font> reproduces the thesis&rsquo; Section-6 table exactly with "
  "piecewise-linear interpolation and clamping. A built-in unit check "
  "(<font face='Courier'>--printForgeTable</font>) verifies it:")
CODE([
  "$ ./ns3 run \"ltm-forged-handover --printForgeTable\"",
  "# exact points (expect .37 .42 .46 .50 .54 .63 .71):",
  "  margin=0 dB -> P=0.3700   margin=1 -> 0.4200   margin=2 -> 0.4600",
  "  margin=3 dB -> 0.5000     margin=4 -> 0.5400   margin=6 -> 0.6300   margin=8 -> 0.7100",
  "# interpolated midpoints (linear mean of bracketing points):",
  "  0.5 dB -> 0.3950   2.5 -> 0.4800   5.0 -> 0.5850   7.0 -> 0.6700",
  "# out-of-range (clamped): -5 dB -> 0.3700   12 dB -> 0.7100",
])
IMG("margin.png", 150 * mm, "Figure 2. Capture probability vs. power margin: thesis table vs. ns-3 measurement.")
H2("6.2 Step 9 &mdash; the attacker injection")
P("On an opportune cell-switch moment for a targeted victim, the attacker draws a Bernoulli trial with "
  "probability <font face='Courier'>P(margin)</font> from the Step-8 table using a dedicated, seeded random "
  "stream. On success (&ldquo;the forged command decodes&rdquo;) the attacker forges a switch to a spoofed "
  "target &rarr; failure &rarr; DoS. On a miss, the legitimate command proceeds. Victims are the first "
  "<font face='Courier'>numAttackers</font> UEs (unicast, targeted). Measured success rate vs. the table "
  "(20 seeds/point): 0 dB &rarr; 0.50 (table 0.37, within sampling noise at n=28), 4 dB &rarr; 0.53 (0.54), "
  "8 dB &rarr; 0.71 (0.71, exact) &mdash; monotonic and matching at the higher-confidence points.")
story.append(PageBreak())

# ============================ CH 7 ============================
H1("7. Implementing a real 6G LTM cell-switch in nr core")
P("Up to this point the cell-switch was triggered by a direct function call. The supervisor asked for a "
  "<b>genuine 6G LTM cell-switch delivered as an unauthenticated MAC Control Element on the real air "
  "interface</b>, with the attacker forging it at the PHY. nr v5.1 has <b>no native LTM</b> (and no "
  "conditional handover), so this was built from scratch across nr&rsquo;s PHY, MAC and RRC. The change is "
  "<b>additive</b> (new message type, new methods, new trace) &mdash; no existing nr behaviour was altered.")
H2("7.1 The nine nr-core files changed (229 inserted lines)")
TABLE([
  ["File", "What was added"],
  ["model/nr-control-messages.h/.cc", "New LTM_CELL_SWITCH message type + NrLtmCellSwitchMessage class (RNTI, targetCellId, Target Configuration ID, forged flag)"],
  ["model/nr-gnb-phy.h/.cc", "NrGnbPhy::SendLtmCellSwitch() &mdash; gNB emits the MAC CE on the DL control channel"],
  ["model/nr-ue-phy.h/.cc", "UE PHY dispatch branch for LTM_CELL_SWITCH; NrUePhy::InjectForgedLtmCellSwitch() (attacker PHY injection)"],
  ["model/nr-ue-cphy-sap.h", "New PHY->RRC upcall RecvLtmCellSwitch() (+ member SAP forwarding)"],
  ["model/nr-ue-rrc.h/.cc", "NrUeRrc::DoRecvLtmCellSwitch() + new LtmCellSwitchReceived trace source"],
], [58 * mm, 107 * mm])
H2("7.2 The end-to-end path")
P("<b>Legitimate command:</b> the A3-like checker asks the serving gNB to switch a UE. "
  "<font face='Courier'>NrGnbPhy::SendLtmCellSwitch()</font> builds an "
  "<font face='Courier'>NrLtmCellSwitchMessage</font>, stamps the source BWP ARFCN, and enqueues it on the "
  "downlink control channel with no added latency (the LTM design point). It travels the air interface; the "
  "victim&rsquo;s <font face='Courier'>NrUePhy</font> receives it, checks it addresses its own RNTI (unicast), "
  "and relays it up the CPHY SAP to <font face='Courier'>NrUeRrc::DoRecvLtmCellSwitch()</font>, which fires "
  "the <font face='Courier'>LtmCellSwitchReceived</font> trace. The example executes the mechanical switch "
  "(reusing nr&rsquo;s tested handover): a legitimate target completes fast (~2 ms).")
P("<b>Forged command (the attack):</b> the attacker calls "
  "<font face='Courier'>NrUePhy::InjectForgedLtmCellSwitch()</font> directly on the victim&rsquo;s PHY &mdash; "
  "modelling the capture-effect overshadow. The forged MAC CE enters the <i>same</i> downlink-control receive "
  "path; the UE cannot authenticate it (below PDCP, no MAC-I) and acts on it identically, attempting a switch "
  "to the spoofed target, which fails &rarr; re-establishment &rarr; DoS.")
NOTE("<b>Bring-up bug fixed.</b> Over-the-air control messages are routed at the UE by their source ARFCN; "
     "the legitimate path initially crashed (SIGABRT in <font face='Courier'>nr-control-messages.cc</font>) "
     "until <font face='Courier'>SendLtmCellSwitch</font> / <font face='Courier'>InjectForgedLtmCellSwitch</font> "
     "stamped the message with <font face='Courier'>DoGetArfcn()</font>.")
P("<b>Why this matters for accuracy:</b> the cell-switch trigger is now a real unauthenticated Layer-2 frame "
  "on the air interface, received and acted upon through nr&rsquo;s genuine PHY&rarr;MAC&rarr;RRC path, and "
  "the forgery is a real PHY-level injection of that frame. This is precisely the attack surface the thesis "
  "targets, rather than a stand-in function call.")
story.append(PageBreak())

# ============================ CH 8 ============================
H1("8. How to run it, and what the output means")
P("All commands are run from <font face='Courier'>/run/media/pranjal/hdd/mtp/ns-3-dev</font>.")
H2("8.1 Build")
CODE(["cd /run/media/pranjal/hdd/mtp/ns-3-dev",
      "./ns3 build ltm-forged-handover      # builds libnr + the scenario program"])
H2("8.2 Unit-check the capture-probability table")
CODE(['./ns3 run "ltm-forged-handover --printForgeTable"'])
P("Prints the Section-6 table at exact, interpolated and out-of-range margins, then exits. Confirms the "
  "link-tier probabilities are wired correctly (Chapter 6).")
H2("8.3 Legitimate LTM handovers over the air (no attack)")
CODE(['./ns3 run "ltm-forged-handover --numCells=4 --numUes=8 --ueSpeedKmph=120 \\',
      '                        --simTime=10 --attackEnabled=0 --verbose=1"'])
P("Expected output includes lines such as:")
CODE(["2.2700s  LTM-RX  UE5 acts on LTM cell-switch MAC CE -> target 4 (legit)",
      "Handover events=5 (failures=0), switch-exec ... swMeanMs=1.9998"])
P("<b>Reading it:</b> each <font face='Courier'>LTM-RX ... (legit)</font> line is a UE receiving a real LTM "
  "MAC CE over the air and executing the switch. <font face='Courier'>swMeanMs=1.9998</font> is the ~2 ms "
  "near-zero cell-switch execution time. Zero failures &mdash; legitimate mobility is healthy.")
H2("8.4 The forged-handover attack (small scale: 2 gNB, 1 UE, 1 attacker)")
CODE(['./ns3 run "ltm-forged-handover --numCells=2 --numUes=1 --ueSpeedKmph=30 \\',
      '           --simTime=9 --attackEnabled=1 --numAttackers=1 \\',
      '           --overshadowMarginDb=8 --attackForceTimeMs=2000 --verbose=1"'])
P("Expected output (abridged):")
CODE([
  "2.0000s FORGE-INJ UE0 (margin=8dB, P=0.71, u=0.59 LANDED) attacker injects",
  "                  forged LTM MAC CE -> spoofed target cell 1",
  "2.0000s LTM-RX    UE0 acts on LTM cell-switch MAC CE -> target 1 (FORGED)",
  "2.0180s RLF-CAUSE UE0 cell 1 cause=DURING_HANDOVER",
  "        STATE     UE0 CONNECTED_HANDOVER -> CONNECTED_PHY_PROBLEM -> IDLE_CELL_SEARCH",
  "Failure outage control-plane: 240.0 ms   data-plane: 262.4 ms",
  "RESULT_ATTACK,... forgedAttempts=1,forgedLanded=1,recovered=1,odpMeanMs=262.3929",
])
P("<b>Reading it:</b> <font face='Courier'>FORGE-INJ</font> is the attacker injecting the forged MAC CE at "
  "the victim PHY; the capture draw landed (u&nbsp;&lt;&nbsp;P). "
  "<font face='Courier'>LTM-RX ... (FORGED)</font> shows the UE acting on it &mdash; it cannot tell it from a "
  "legitimate command. The <font face='Courier'>DURING_HANDOVER</font> failure, the state transitions through "
  "<font face='Courier'>PHY_PROBLEM</font> and cell search, and the ~240/262 ms outage are the "
  "denial-of-service. The machine-readable <font face='Courier'>RESULT_ATTACK</font> / "
  "<font face='Courier'>RESULT_RLF</font> / <font face='Courier'>RESULT_BASELINE</font> lines carry every "
  "parameter and metric for scripted collection.")
H2("8.5 Result-line fields (reference)")
TABLE([
  ["Field", "Meaning"],
  ["forgedAttempts / forgedLanded", "attack opportunities vs. those where the forged frame decoded"],
  ["swMeanMs", "legitimate cell-switch execution time (~2 ms)"],
  ["ocpMeanMs", "failure outage, control-plane (onset -> recovery)"],
  ["odpMeanMs", "failure interruption, data-plane (last good DL -> first restored DL)"],
  ["rlf / phyProblem / recovered", "radio-link-failure / PHY-problem entries / recoveries"],
], [58 * mm, 107 * mm])
story.append(PageBreak())

# ============================ CH 9 ============================
H1("9. Results and what they mean")
IMG("inflation.png", 155 * mm, "Figure 3. A single forged LTM switch inflates the interruption ~118x.")
P("The central, publishable result is the <b>before/after pair</b>: LTM exists to deliver a near-zero "
  "intra-base-station interruption, and a single forged switch turns that into a multi-hundred-millisecond "
  "outage on the exact KPI 6G is optimising. Our small-scale numbers reproduce the qualitative shape of the "
  "thesis&rsquo; own model (which projects a mean ~295 ms).")
TABLE([
  ["Metric", "Legitimate", "Forged switch", "Change"],
  ["Cell-switch execution (control-plane)", "2.036 ms", "240.0 ms", "~118x"],
  ["Data-plane interruption", "~2-14 ms", "262.4 ms", "~19-130x"],
  ["Handover failures", "0", "1 per landed forge", "&mdash;"],
], [64 * mm, 34 * mm, 37 * mm, 30 * mm])
H2("9.1 What is proven")
BULLETS([
  "A legitimate LTM cell-switch, carried as a real MAC CE over the air, is fast (~2 ms) and reliable.",
  "A forged MAC CE injected at the victim PHY is <b>indistinguishable to the UE</b> and causes a large, "
  "measured denial-of-service (~240&ndash;262 ms).",
  "The attack is <b>probabilistic in the power margin</b> exactly as the thesis&rsquo; link tier specifies, "
  "and <b>targeted to a single UE</b>.",
  "Legitimate mobility and forged attacks <b>coexist</b> in the same multi-cell run without instability.",
])
story.append(PageBreak())

# ============================ CH 10 ============================
H1("10. Accuracy vs. the thesis: what is faithful, what is abstracted")
P("The thesis attack has five stages. The table maps each to the model, honestly.")
TABLE([
  ["Thesis stage", "In the model?"],
  ["1. Pre-position (map handover regions)", "No - assumed"],
  ["2. Re-identify victim C-RNTI (LTrack)", "No - victim addressed by RNTI directly"],
  ["3. Reactive PDCCH monitoring (AdaptOver)", "No - injection at an opportune moment"],
  ["4. Induce (degrade serving beam to trigger a real command)", "Partial - forced/opportune trigger, no beam degradation"],
  ["5. Inject forged LTM MAC CE (spoofed Target Config ID)", "Yes - real MAC CE, injected at victim PHY"],
], [95 * mm, 70 * mm])
P("The thesis itself labels stages 1&ndash;4 as prior-art primitives its attack <i>assembles</i>, and calls "
  "stage 5 &ldquo;this work.&rdquo; The absence of 1&ndash;3 is therefore consistent with the thesis framing, "
  "but they are genuinely not simulated.")
H2("10.1 Faithfully depicted")
BULLETS([
  "The unauthenticated Layer-2 MAC CE on the real air interface, unicast to the victim RNTI; the UE acts on "
  "legitimate and forged commands identically (the core vulnerability).",
  "The spoofed Target Configuration ID; PHY-level forgery (capture effect); capture success vs. power margin "
  "(Section-6 table); the targeted single-UE DoS outcome; no keys / no core access.",
])
H2("10.2 Abstracted or differing (be aware)")
BULLETS([
  "<b>RF capture physics</b> (symbol-synchronised, cyclic-prefix-aligned, same-subframe overshadow) is not "
  "simulated; it enters only as the Section-6 probability. This is the thesis&rsquo; own boundary B2.",
  "<b>&lsquo;Acts before HARQ confirmation&rsquo;</b> (a TS 38.321 timing detail) is not explicitly modelled; "
  "the UE acts on the CE when received.",
  "<b>Failure trigger:</b> the thesis says mis-switch &rarr; radio-link failure (T310); we realise the DoS as "
  "a handover failure (RACH-to-spoofed-target). Same class and magnitude, different trigger &mdash; because "
  "the literal coverage-loss RLF would not fire in this nr scenario (five causes were ruled out).",
  "<b>Attack sub-types:</b> only <i>forge</i> is implemented; the thesis&rsquo; <i>replay</i> and "
  "<i>induce-then-inject</i> variants are not distinct.",
  "<b>Channel-matrix caching</b> (fast fading frozen at the UE&rsquo;s start position; beam direction still "
  "updates) &mdash; inherited from the validated baseline scenario.",
])
story.append(PageBreak())

# ============================ CH 11 ============================
H1("11. What remains")
P("The delivered milestone is an accurate <b>small-scale</b> attack model (one attacker, one victim, two "
  "gNBs, real beamforming, a real air-interface LTM MAC CE). The following are deliberately deferred:")
BULLETS([
  "<b>Large-scale campaign:</b> the thesis&rsquo; sweeps (7&ndash;19 cells, 50&ndash;300 UEs, "
  "1&ndash;10 attackers, 0&ndash;8 dB, 3&ndash;120 km/h, &ge;100 seeds/point). A performance study showed the "
  "full-scale point (~12 cells / 150 UEs / 10 s) costs order-of-an-hour per seed, so a documented seed/scale "
  "reduction is required; this was agreed but not yet executed.",
  "<b>Statistics, tables and plots</b> (mean &plusmn; 95% CI, interruption / RLF / throughput / ping-pong vs. "
  "each swept axis).",
  "<b>Throughput-collapse and packet-loss</b> headline metrics on the victim bearer (the plumbing exists; "
  "they are not yet the reported figures).",
  "<b>Higher-fidelity attack stages</b> (Chapter 10): the induce step, the replay / induce-then-inject "
  "sub-types, and optionally a literal T310 RLF trigger.",
  "<b>The thesis&rsquo; non-cryptographic defence</b> (per-UE detector + ML attacker-localiser) &mdash; "
  "explicitly out of the current attack-only scope.",
])
story.append(PageBreak())

# ============================ CH 12 ============================
H1("12. Questions raised in review")
H2("Q1. Must the attacker&rsquo;s RSRP be higher than the serving cell? (a higher RSRP is detectable)")
P("<b>Not by much, and not as a power race.</b> The thesis models the injection as a <i>capture effect</i>: a "
  "symbol-synchronised, cyclic-prefix-aligned frame that the receiver locks onto within the CP window. The "
  "Section-6 table makes this quantitative &mdash; even at a <b>0 dB</b> mean margin the forged command decodes "
  "~37% of the time, and only a modest <b>3&ndash;4 dB</b> advantage (routine for a co-located or beam-aligned "
  "SDR) pushes it past 50%. So the attacker does <i>not</i> need a large, conspicuous power increase; a few dB "
  "suffices, and 0 dB still works probabilistically. That is exactly why the attack is stealthy. Your point "
  "about detectability is correct and is in fact the basis of the thesis&rsquo; <i>defence</i>: a large or "
  "anomalous received-power / BLER / EVM signature is a detectable PHY overshadow fingerprint. In our current "
  "ns-3 model the RF power is not simulated directly (boundary B2); the margin enters only through the "
  "probability table, so the model reflects &lsquo;modest margin &rarr; stealthy, probabilistic success&rsquo; "
  "but does not itself model RSRP detectability. Modelling that fingerprint belongs to the (deferred) defence "
  "tier.")
H2("Q2. Resource allocation uses a DNN &mdash; does that change the mechanism?")
P("<b>No, the attack is orthogonal to the resource scheduler.</b> The vulnerability is in the "
  "<i>control-plane mobility trigger</i> (the unauthenticated LTM cell-switch MAC CE), not in how "
  "user-plane PDSCH/PUSCH resources are allocated. Whether the scheduler is round-robin, proportional-fair, "
  "or a DNN-based allocator, the cell-switch command is still an unauthenticated Layer-2 frame the UE acts on, "
  "so a DNN scheduler does not alter the forgeability or the DoS mechanism. Our model uses nr&rsquo;s standard "
  "MAC scheduler, not a DNN. One <i>indirect</i> interaction is worth noting: the scheduler decides whether a "
  "UE is granted downlink control, which feeds the UE&rsquo;s radio-link monitoring &mdash; we observed this "
  "when investigating RLF (Chapter 5). But that affects <i>failure detection</i>, not the attack itself. If "
  "the lab&rsquo;s work applies a DNN to resource allocation, it is a separate user-plane optimisation that "
  "sits beside, and does not protect, the L2 mobility command.")
H2("Q3. What type of handover is this &mdash; make-before-break or break-before-make? Soft or hard?")
P("In nr / 5G-LENA the executed handover is a <b>hard, break-before-make</b> handover: the UE releases the "
  "source before completing random access to the target, which is why there is a measurable (if small) "
  "interruption. It is a <b>hard</b> handover, not a soft one (soft handover with macro-diversity belongs to "
  "CDMA/UMTS, not NR). LTM&rsquo;s contribution in the standard is to <i>shrink</i> that interruption toward "
  "zero via pre-configured candidate cells and early synchronisation, approaching make-before-break-like "
  "continuity without true soft combining. Our model captures LTM&rsquo;s <i>low-latency trigger</i> and its "
  "near-zero result (~2 ms), while the mechanical execution underneath is nr&rsquo;s break-before-make "
  "handover (boundary B1). The forged attack turns this fast, hard switch into a <i>failed</i> hard switch.")
H2("Q4. Vertical / horizontal? inter/intra-RAT, -frequency, -layer, -operator? early/late? KPIs?")
TABLE([
  ["Handover dimension", "This model"],
  ["Horizontal vs. vertical", "Horizontal (gNB to gNB, same access type)"],
  ["Inter- vs. intra-RAT", "Intra-RAT (all NR / 5G-LENA; no LTE<->NR)"],
  ["Inter- vs. intra-frequency", "Intra-frequency (single 4 GHz carrier; LTM is an intra-frequency switch)"],
  ["Inter- vs. intra-layer", "Intra-layer (single macro tier; no small-cell/macro layering)"],
  ["Inter- vs. intra-operator", "Intra-operator (single core / EPC)"],
  ["Early / late handover", "A3-like trigger, 320 ms time-to-trigger; the forged switch is a mis-timed/wrong-target (too-late-like) failure"],
  ["Soft vs. hard", "Hard (break-before-make)"],
  ["Switching KPIs measured", "Interruption time, handover-failure rate, RLF, and (available) throughput / packet-loss / ping-pong"],
], [58 * mm, 107 * mm])
P("In short: this is an <b>intra-frequency, intra-RAT, intra-layer, intra-operator, horizontal, hard "
  "(break-before-make) handover</b> &mdash; matching the thesis&rsquo; &ldquo;fast intra-frequency LTM cell "
  "switch.&rdquo; Vertical / inter-RAT / inter-frequency / inter-operator mobility and soft handover are out "
  "of scope (and largely not applicable to the LTM cell-switch the thesis attacks).")
story.append(PageBreak())

# ============================ APPENDIX ============================
H1("Appendix A. Complete change inventory")
H2("A.1 nr core (9 files, additive, 229 lines) &mdash; the LTM MAC CE")
TABLE([
  ["File", "Lines +", "Addition"],
  ["nr-control-messages.h", "36", "LTM_CELL_SWITCH type + NrLtmCellSwitchMessage class"],
  ["nr-control-messages.cc", "55", "NrLtmCellSwitchMessage implementation"],
  ["nr-gnb-phy.h / .cc", "10 / 18", "SendLtmCellSwitch() (gNB emits the MAC CE)"],
  ["nr-ue-phy.h / .cc", "10 / 32", "LTM dispatch + InjectForgedLtmCellSwitch() (attacker)"],
  ["nr-ue-cphy-sap.h", "21", "RecvLtmCellSwitch() PHY->RRC upcall"],
  ["nr-ue-rrc.h / .cc", "28 / 19", "DoRecvLtmCellSwitch() + LtmCellSwitchReceived trace"],
], [55 * mm, 22 * mm, 88 * mm])
H2("A.2 Scenario program")
BULLETS([
  "<font face='Courier'>contrib/nr/examples/ltm-forged-handover.cc</font> &mdash; 1395 lines, 27 CLI "
  "arguments. Contains: the urban-grid scenario; the A3-like <font face='Courier'>HandoverCheck</font>; the "
  "Section-6 <font face='Courier'>PForgeDecode</font> table + unit-check; the attacker "
  "(<font face='Courier'>DoOpportuneSwitch</font> emitting legitimate / forged MAC CEs); the "
  "execution/failure bridge (<font face='Courier'>LtmExecuteSwitch</font>, "
  "<font face='Courier'>SetRachDropAtCell</font>); the RLF / handover-failure / re-establishment trace sinks "
  "and outage timing; and the machine-readable result lines.",
  "Registered in <font face='Courier'>contrib/nr/examples/CMakeLists.txt</font>.",
])
H2("A.3 Supporting files on the drive")
BULLETS([
  "<font face='Courier'>mtp/THESIS_ATTACK_SPEC.md</font> &mdash; the extracted, authoritative attack spec.",
  "<font face='Courier'>mtp/PLAN.md</font> &mdash; the 18-step plan, scope change and deviations log.",
  "<font face='Courier'>mtp/changes.txt</font> &mdash; the detailed running change-log (every step, with "
  "verification output).",
])
SP(8)
story.append(HRFlowable(width="100%", thickness=0.8, color=CODEBORDER))
SP(6)
P("<i>All figures and results in this report were produced by real simulation runs of the program described "
  "above. Nothing is asserted or fabricated; where a value is a model input (e.g. the Section-6 capture "
  "probabilities) it is labelled as such.</i>")


# ---- footer with page numbers ----
def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 12 * mm, "ns-3 / 5G-LENA — Forged 6G LTM cell-switch attack")
    canvas.drawRightString(192 * mm, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(CODEBORDER)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                        topMargin=16 * mm, bottomMargin=18 * mm,
                        title="ns-3 6G LTM Forged Handover Report")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("PDF written:", OUT)
