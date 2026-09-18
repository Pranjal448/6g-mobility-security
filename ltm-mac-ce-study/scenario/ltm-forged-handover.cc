// SPDX-License-Identifier: GPL-2.0-only
//
// ltm-forged-handover.cc
// =====================================================================================
// 6G LTM forged-handover ATTACK MODEL — ns-3 + 5G-LENA (nr) system-tier scenario.
//
// STEP 3 (scenario skeleton) + STEP 4 (baseline fast MAC-triggered handover and its
// near-zero interruption validation) of the implementation plan (see mtp/PLAN.md).
//
//   - Urban grid gNB layout, 250 m inter-site distance, 4 GHz carrier.
//   - Configurable: --numCells, --numUes, --ueSpeedKmph, --simTime, --rngSeed, --rngRun,
//                   --timeToTriggerMs (default 320), --hysteresisMeters.
//   - UEs move (constant-speed bounded random walk) and traverse cell edges.
//   - DL + UL UDP bearers so there is real traffic to measure.
//
//   STEP 4: an LTM-style *fast MAC-triggered intra-frequency handover* proxy. Per
//   modelling boundary B1, 6G LTM is approximated by NR's X2 handover machinery, but
//   TRIGGERED FAST and directly (via NrHelper::HandoverRequest) from our own geometric
//   A3-like measurement logic (target cell stronger — here, closer — than serving by a
//   hysteresis, sustained for the 320 ms time-to-trigger), rather than via the slow
//   default RRC-measurement report path.
//
//   The baseline (no-attack) handover interruption is reported two ways (see the
//   computation block near the end of main()):
//     (1) cell-switch execution time = HandoverEndOk - HandoverStart (~2 ms) — the direct
//         proxy of the intra-BS LTM ~1-2 ms "near-zero" cell-switch budget (headline KPI);
//     (2) DL data-plane gap straddling the switch (~tens of ms) — the full user-plane
//         outage, larger than (1) because NR's X2 HO is not make-before-break/lossless.
//
//   MODELLING NOTE (kept nr PRISTINE — no simulator-internal patches): NR's PHY half-duplex
//   guards fatal-error if a UE transmits UL across a handover transition (lossless HO is not
//   implemented). The upstream nr handover tests avoid this by pausing traffic over the HO
//   window. We follow that sanctioned pattern by keeping DL flowing across the switch (the
//   thing we measure) and disabling UL by default; this needs NO change to nr-spectrum-phy.
//   An earlier revision patched those guards to log-and-drop — that was reverted as both
//   unnecessary (DL-only measurement is clean) and incomplete (it missed one of the guards).
//
//   STEP 5: RLF / RRC re-establishment (FAILURE-PATH) tracing. The RRC StateTransition,
//   RadioLinkFailure and RadioLinkFailureCause traces are hooked per UE to timestamp the
//   outage window of a failed switch: onset = entry to CONNECTED_PHY_PROBLEM (radio-link
//   failure detected — T310 expired or a handover failed), recovery = return to
//   CONNECTED_NORMALLY (RRC re-establishment completed). Two interruption figures result:
//     (A) control-plane outage = recovery - onset (RRC state-machine failure duration);
//     (B) data-plane mobility interruption = last DL delivered before onset -> first DL
//         delivered after recovery ("last good DL -> first restored DL").
//   RLF timers (T310/N310/N311) and re-establishment are CLI-exposed. A CONTROLLED FAILURE
//   PROBE (--rlfProbeUe / --rlfProbeTimeMs) forces one UE to a wrong (farthest) target cell
//   to provoke this path against a real failure condition — validation only, NOT the Step-9
//   attacker (which will drive the same path probabilistically from the link-tier table).
//
//   STEP 8: link-tier margin->P(forge-decode) lookup table (spec §6), the ONLY place the RF
//   capture effect enters (boundary B2). See PForgeDecode().
//
//   STEP 9: forged-handover ATTACK injection. When the network reaches an opportune LTM
//   cell-switch moment for a targeted victim UE (--attackEnabled, --numAttackers victims,
//   --overshadowMarginDb), the attacker overshadows the legitimate MAC-CE switch: a per-attempt
//   Bernoulli with p = PForgeDecode(margin) decides whether the forged frame "decodes"; on a
//   land the UE is mis-switched to a WRONG (farthest) target cell -> RLF -> RRC re-establishment
//   (the DoS, measured by the Step-5 machinery); on a miss the legitimate switch proceeds. See
//   DoOpportuneSwitch(). Small-scale demonstration only (no measurement campaign this phase).
//
// Modelling boundaries (mirrored from the thesis, see mtp/PLAN.md / README):
//   B1: 6G is not in ns-3 — NR + a fast MAC-triggered handover approximates the LTM
//       cell-switch MAC CE trigger.
//   B2: the RF capture effect is not simulated — it enters only as a per-attempt success
//       probability (added in steps 8/9).
// =====================================================================================

#include "ns3/antenna-module.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/nr-module.h"
#include "ns3/point-to-point-module.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <map>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("LtmForgedHandover");

// -------------------------------------------------------------------------------------
// Per-UE handover + measurement state.
// -------------------------------------------------------------------------------------
struct UeHoState
{
    uint16_t servingCellId = 0;
    Ptr<NetDevice> servingGnbDev = nullptr;
    uint16_t candidateCellId = 0; // cell currently accumulating time-to-trigger
    Time candidateSince = Seconds(0);
    bool hoInProgress = false;
    uint32_t hoCount = 0;
    uint32_t hoFailures = 0;
    std::vector<double> dlRxTimes;                    // s, DL packet arrival times at UE
    std::vector<double> hoStartTimes;                 // s, HandoverStart instants
    std::vector<std::pair<double, double>> hoWindows; // s, (start, end) of completed HOs

    // ---- Step 5: RLF / RRC re-establishment (failure-path) tracing state ----
    // An "outage" begins when the UE enters CONNECTED_PHY_PROBLEM (radio-link failure
    // detected, i.e. T310 has expired or a handover failed) and ends when the UE next
    // returns to CONNECTED_NORMALLY (RRC re-establishment succeeded). If it never returns,
    // the outage is left-censored (recovery = -1) and the UE is stuck in IDLE.
    uint32_t rlfCount = 0;             // number of RadioLinkFailure trace firings
    uint32_t phyProblemCount = 0;      // entries into CONNECTED_PHY_PROBLEM
    uint32_t reestabAttemptCount = 0;  // entries into CONNECTED_REESTABLISHING
    uint32_t reestabSuccessCount = 0;  // PHY_PROBLEM/REESTABLISHING -> CONNECTED_NORMALLY
    bool inOutage = false;             // currently between PHY_PROBLEM entry and recovery
    double outageOnset = -1.0;         // s, time of current outage onset
    std::string lastRlfCause;          // most recent RLF cause token
    std::vector<double> rlfCauseT310Ms;   // per-RLF: T310 elapsed at failure (ms), -1 if n/a
    std::vector<std::pair<double, double>> outageWindows; // s, (onset, recovery); recovery<0 = censored
    std::vector<std::string> outageCauses;                // cause token per outage window
    uint16_t lastState = 9;            // last observed NrUeRrc::State (9 = CONNECTED_NORMALLY)

    // ---- Steps 8-9: per-UE attacker bookkeeping ----
    uint32_t forgedAttempts = 0; // opportune switch moments the attacker overshadowed
    uint32_t forgedLanded = 0;   // of those, how many forged commands "decoded" (landed)
    bool forgedActive = false;   // UE is mid-forged-mis-switch: benign HO must not rescue it
    bool needsRestore = false;   // victim was displaced (coverage loss) and awaits restore on RLF
    Vector savedPos;             // pre-attack position, restored so the UE can re-establish
    uint16_t spoofedCell = 0;    // the wrong target Configuration ID the forged command carried
};

// Globals used by the scheduled checker and trace sinks.
static std::vector<UeHoState> g_ue;
static NetDeviceContainer g_ueNetDevs;
static std::vector<Vector> g_gnbPositions;    // by gNB device index
static std::map<uint16_t, Vector> g_cellPos;         // cellId -> position
static std::map<uint16_t, Ptr<NetDevice>> g_cellDev; // cellId -> serving gNB NetDevice
static std::vector<uint16_t> g_cellIds;              // all serving cellIds
static Ptr<NrHelper> g_nrHelper;
static double g_hysteresisM = 20.0;
static Time g_ttt = MilliSeconds(320);
static bool g_verbose = false;

// ---- Steps 8-9: attacker (forged LTM cell-switch) state ----
static bool g_attackEnabled = false;
static double g_overshadowMarginDb = 4.0;      // attacker-to-legit power margin (dB), spec §5/§6
static std::vector<bool> g_isVictim;           // per-UE: targeted by an overshadowing attacker
static Ptr<UniformRandomVariable> g_attackRng; // Bernoulli draw for "forged command decodes"
static uint32_t g_forgedAttempts = 0;          // opportune moments where a forgery was attempted
static uint32_t g_forgedLanded = 0;            // attempts where the forged command "decoded"

// -------------------------------------------------------------------------------------
// Step 8: link-tier margin -> P(forge-decode) lookup table (THESIS_ATTACK_SPEC §6), the
// ONLY place the RF capture effect enters (modelling boundary B2). Piecewise-linear
// interpolation between the thesis's tabulated points; clamped outside the range.
//   margin(dB): 0    1    2    3    4    6    8
//   P(decode):  .37  .42  .46  .50  .54  .63  .71
// -------------------------------------------------------------------------------------
static double
PForgeDecode(double marginDb)
{
    static const double mx[] = {0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0};
    static const double py[] = {0.37, 0.42, 0.46, 0.50, 0.54, 0.63, 0.71};
    const int n = 7;
    if (marginDb <= mx[0])
    {
        return py[0];
    }
    if (marginDb >= mx[n - 1])
    {
        return py[n - 1];
    }
    for (int i = 0; i < n - 1; ++i)
    {
        if (marginDb >= mx[i] && marginDb <= mx[i + 1])
        {
            double frac = (marginDb - mx[i]) / (mx[i + 1] - mx[i]);
            return py[i] + frac * (py[i + 1] - py[i]);
        }
    }
    return py[n - 1]; // unreachable
}

// -------------------------------------------------------------------------------------
// Trace sinks (ue index bound as first argument via MakeBoundCallback).
// -------------------------------------------------------------------------------------
static void
DlRxSink(uint32_t ueIdx, Ptr<const Packet>, const Address&, const Address&)
{
    g_ue[ueIdx].dlRxTimes.push_back(Simulator::Now().GetSeconds());
}

static void
HoStartSink(uint32_t ueIdx, uint64_t imsi, uint16_t cellId, uint16_t /*rnti*/, uint16_t targetCid)
{
    g_ue[ueIdx].hoStartTimes.push_back(Simulator::Now().GetSeconds());
    if (g_verbose)
    {
        std::cout << std::fixed << std::setprecision(4) << Simulator::Now().GetSeconds()
                  << "s  HO-START   UE" << ueIdx << " imsi=" << imsi << " cell " << cellId
                  << " -> " << targetCid << std::endl;
    }
}

static void
HoEndOkSink(uint32_t ueIdx, uint64_t imsi, uint16_t cellId, uint16_t /*rnti*/)
{
    double te = Simulator::Now().GetSeconds();
    UeHoState& s = g_ue[ueIdx];
    // Pair this completion with the most recent unmatched HandoverStart.
    if (s.hoWindows.size() < s.hoStartTimes.size())
    {
        double ts = s.hoStartTimes.back();
        s.hoWindows.emplace_back(ts, te);
    }
    s.servingCellId = cellId;
    auto it = g_cellDev.find(cellId);
    if (it != g_cellDev.end())
    {
        s.servingGnbDev = it->second;
    }
    s.hoInProgress = false;
    s.candidateCellId = 0;
    s.hoCount++;
    if (g_verbose)
    {
        std::cout << std::fixed << std::setprecision(4) << te << "s  HO-END-OK  UE" << ueIdx
                  << " imsi=" << imsi << " now on cell " << cellId << std::endl;
    }
}

static void
HoEndErrorSink(uint32_t ueIdx, uint64_t imsi, uint16_t cellId, uint16_t /*rnti*/)
{
    UeHoState& s = g_ue[ueIdx];
    s.hoInProgress = false;
    s.candidateCellId = 0;
    s.hoFailures++;
    if (g_verbose)
    {
        std::cout << std::fixed << std::setprecision(4) << Simulator::Now().GetSeconds()
                  << "s  HO-END-ERR UE" << ueIdx << " imsi=" << imsi << " cell " << cellId
                  << std::endl;
    }
}

// -------------------------------------------------------------------------------------
// Step 5 trace sinks: RLF onset, its cause, and the RRC state machine used to bound the
// outage window (CONNECTED_PHY_PROBLEM entry -> CONNECTED_NORMALLY return).
//
// -------------------------------------------------------------------------------------

// RadioLinkFailure: ImsiCidRnti signature. Fired at T310 expiry (radio link deemed failed).
static void
RlfSink(uint32_t ueIdx, uint64_t imsi, uint16_t cellId, uint16_t /*rnti*/)
{
    UeHoState& s = g_ue[ueIdx];
    s.rlfCount++;
    // If this UE lost its link to a landed forged switch (modelled as coverage loss), the radio
    // link has now been declared failed; restore its real position so RRC re-establishment (via
    // IDLE cell (re)selection) can find a reachable cell. The outage window (onset = the imminent
    // CONNECTED_PHY_PROBLEM entry) already began the moment the link was lost.
    if (s.needsRestore)
    {
        Ptr<MobilityModel> mm = g_ueNetDevs.Get(ueIdx)->GetNode()->GetObject<MobilityModel>();
        mm->SetPosition(s.savedPos);
        s.needsRestore = false;
    }
    if (g_verbose)
    {
        std::cout << std::fixed << std::setprecision(4) << Simulator::Now().GetSeconds()
                  << "s  RLF        UE" << ueIdx << " imsi=" << imsi << " cell " << cellId
                  << " (radio link failed)" << std::endl;
    }
}

// RadioLinkFailureCause: (imsi, cellId, rnti, state, causeToken, t310ElapsedMs, msSinceLastHoSuccess).
static void
RlfCauseSink(uint32_t ueIdx,
             uint64_t imsi,
             uint16_t cellId,
             uint16_t /*rnti*/,
             uint16_t /*state*/,
             std::string cause,
             int64_t t310ElapsedMs,
             int64_t /*msSinceLastHoSuccess*/)
{
    UeHoState& s = g_ue[ueIdx];
    s.lastRlfCause = cause;
    s.rlfCauseT310Ms.push_back(static_cast<double>(t310ElapsedMs));
    if (g_verbose)
    {
        std::cout << std::fixed << std::setprecision(4) << Simulator::Now().GetSeconds()
                  << "s  RLF-CAUSE  UE" << ueIdx << " imsi=" << imsi << " cell " << cellId
                  << " cause=" << cause << " T310elapsed=" << t310ElapsedMs << "ms" << std::endl;
    }
}

// StateTransition: (imsi, cellId, rnti, oldState, newState). Bounds outage windows precisely.
static void
StateSink(uint32_t ueIdx,
          uint64_t imsi,
          uint16_t cellId,
          uint16_t /*rnti*/,
          NrUeRrc::State oldState,
          NrUeRrc::State newState)
{
    UeHoState& s = g_ue[ueIdx];
    s.lastState = static_cast<uint16_t>(newState);
    double now = Simulator::Now().GetSeconds();

    if (newState == NrUeRrc::CONNECTED_PHY_PROBLEM)
    {
        // Radio-link failure detected -> outage onset (only count the first entry if the
        // UE bounces PHY_PROBLEM<->REESTABLISHING before recovering).
        s.phyProblemCount++;
        if (!s.inOutage)
        {
            s.inOutage = true;
            s.outageOnset = now;
        }
    }
    else if (newState == NrUeRrc::CONNECTED_REESTABLISHING)
    {
        s.reestabAttemptCount++;
    }
    else if (newState == NrUeRrc::CONNECTED_NORMALLY && s.inOutage)
    {
        // Recovery: the UE is connected again after the failure. Recovery may arrive via the
        // RRC re-establishment path (CONNECTED_REESTABLISHING -> CONNECTED_NORMALLY) or, when
        // no cell will accept a re-establishment request (no prepared UE context), via a full
        // IDLE cell-(re)selection + reconnect. Either way the outage ends here; the whole
        // interval onset..now is the failure outage.
        s.reestabSuccessCount++;
        s.outageWindows.emplace_back(s.outageOnset, now);
        s.outageCauses.push_back(s.lastRlfCause.empty() ? "UNKNOWN" : s.lastRlfCause);
        s.inOutage = false;
        s.outageOnset = -1.0;
        s.forgedActive = false; // recovered onto a real cell: benign HO may resume
        // Recovery after RLF is an IDLE cell-(re)selection + reconnect, NOT a handover, so
        // HoEndOkSink never fires and s.servingCellId is stale (still the forged cell). The
        // StateTransition to CONNECTED_NORMALLY carries the cell the UE re-established on;
        // resync serving state to it so HandoverCheck measures hysteresis from the real cell.
        if (cellId != 0)
        {
            s.servingCellId = cellId;
            auto it = g_cellDev.find(cellId);
            if (it != g_cellDev.end())
            {
                s.servingGnbDev = it->second;
            }
        }
    }
    if (g_verbose)
    {
        std::cout << std::fixed << std::setprecision(4) << now << "s  STATE      UE" << ueIdx
                  << " imsi=" << imsi << " " << oldState << " -> " << newState << std::endl;
    }
}

// -------------------------------------------------------------------------------------
// Return the strongest candidate cell for a position, using distance as an RSRP proxy
// (closest gNB = strongest signal on a homogeneous grid; sanctioned geometric proxy).
// -------------------------------------------------------------------------------------
static void
BestCellByDistance(const Vector& p, uint16_t& bestCell, double& bestDist)
{
    bestDist = std::numeric_limits<double>::max();
    bestCell = g_cellIds.empty() ? 0 : g_cellIds[0];
    for (uint16_t cid : g_cellIds)
    {
        double d = CalculateDistance(p, g_cellPos[cid]);
        if (d < bestDist)
        {
            bestDist = d;
            bestCell = cid;
        }
    }
}

// -------------------------------------------------------------------------------------
// Step 5 CONTROLLED FAILURE PROBE (validation only; NOT the attacker of Step 9).
// At a scheduled instant, deliberately force a chosen victim UE to hand over to the
// geographically FARTHEST real cell — i.e. a wrong/unreachable target, exactly the
// consequence a forged LTM cell-switch would inject. The UE detaches from its good
// serving cell, cannot sustain the far target (DL below Qout -> N310 out-of-sync ->
// T310 -> radio-link failure), then RRC-re-establishes on a genuinely reachable cell.
// This exercises the full RLF + re-establishment outage-measurement path built here,
// against a real failure condition, before any attacker code exists.
// -------------------------------------------------------------------------------------
// Toggle nr's TestDropRachPreambles on the gNB serving `cellId`. When ON, that gNB drops every
// RACH preamble, so a UE trying to random-access it (e.g. to complete a commanded handover)
// exhausts PreambleTransMax and the handover fails (HandoverFailureMaxRach) -> the UE is routed
// through RRC re-establishment. This is nr's own handover-failure mechanism (test/nr-test-
// handover-failure.cc) and is the 3GPP-faithful realisation of a forged/mis-switch to a target
// the UE cannot actually complete access to (spoofed Target Configuration ID).
static void
SetRachDropAtCell(uint16_t cellId, bool drop)
{
    auto it = g_cellDev.find(cellId);
    if (it == g_cellDev.end() || it->second == nullptr)
    {
        return;
    }
    NrHelper::GetGnbPhy(it->second, 0)->SetAttribute("TestDropRachPreambles", BooleanValue(drop));
}

// Pick a real neighbour cell (nearest non-serving) to name as the (wrong) forged target.
static uint16_t
NearestNeighbourCell(const Vector& pos, uint16_t servingCellId)
{
    uint16_t best = 0;
    double bestDist = std::numeric_limits<double>::max();
    for (uint16_t cid : g_cellIds)
    {
        if (cid == servingCellId || !g_cellPos.count(cid))
        {
            continue;
        }
        double d = CalculateDistance(pos, g_cellPos[cid]);
        if (d < bestDist)
        {
            bestDist = d;
            best = cid;
        }
    }
    return best;
}

// -------------------------------------------------------------------------------------
// Execute a cell switch that the UE was commanded to perform by an LTM cell-switch MAC CE.
// This is the mechanical move; it reuses nr's tested handover execution. For a LEGITIMATE
// command (forged==false) it is a normal fast switch to the (correct, reachable) target. For
// a FORGED command (forged==true) the named target is one the UE cannot complete access to, so
// we drop that target's RACH (nr TestDropRachPreambles) and the handover fails
// (HandoverFailureMaxRach) -> RRC re-establishment: the DoS. Scheduled via ScheduleNow so it
// runs outside the PHY receive/trace context.
// -------------------------------------------------------------------------------------
static void
LtmExecuteSwitch(uint32_t ueIdx, uint16_t targetCellId, bool validCandidate)
{
    if (ueIdx >= g_ue.size())
    {
        return;
    }
    UeHoState& s = g_ue[ueIdx];
    if (s.hoInProgress || s.servingGnbDev == nullptr || !g_cellDev.count(targetCellId))
    {
        return;
    }
    Ptr<NetDevice> ueDev = g_ueNetDevs.Get(ueIdx);
    if (!validCandidate)
    {
        // The MAC CE named a Target Configuration ID the UE has NO pre-configured candidate for
        // (exactly what a forged/spoofed ID carries). LTM cannot activate a non-existent
        // candidate: the UE attempts the commanded switch to an unprepared target and cannot
        // complete access to it (modelled via RACH failure) -> handover failure -> RRC
        // re-establishment: the DoS.
        s.hoInProgress = true;
        s.forgedActive = true;
        s.spoofedCell = targetCellId;
        SetRachDropAtCell(targetCellId, true);
        Simulator::Schedule(MilliSeconds(1500), &SetRachDropAtCell, targetCellId, false);
        g_nrHelper->HandoverRequest(MilliSeconds(0), ueDev, s.servingGnbDev, targetCellId);
        return;
    }
    if (targetCellId == s.servingCellId)
    {
        return; // already on the commanded candidate: nothing to do
    }
    // Valid pre-configured candidate: ACTIVATE it. This is the LTM activation -- the target was
    // provisioned in advance, so no fresh network decision or configuration delivery happens
    // here. The mechanical cell change reuses nr's handover execution (nr has no RACH-less
    // activation path; that timing detail is a documented modelling boundary).
    s.hoInProgress = true;
    g_nrHelper->HandoverRequest(MilliSeconds(0), ueDev, s.servingGnbDev, targetCellId);
    s.servingGnbDev = g_cellDev[targetCellId];
}

// TracedCallback for NrUeRrc::LtmCellSwitchReceived: the UE has acted on an LTM MAC CE. Bounce
// the execution out of the PHY/trace context with ScheduleNow.
static void
LtmCellSwitchSink(uint32_t ueIdx,
                  uint64_t /*imsi*/,
                  uint16_t /*cellId*/,
                  uint16_t /*rnti*/,
                  uint16_t targetCellId,
                  uint16_t targetConfigId,
                  bool forged,
                  bool validCandidate)
{
    if (g_verbose)
    {
        std::cout << std::fixed << std::setprecision(4) << Simulator::Now().GetSeconds()
                  << "s  LTM-RX     UE" << ueIdx << " acts on LTM MAC CE configId=" << targetConfigId
                  << (validCandidate ? " -> ACTIVATE pre-configured candidate cell "
                                     : " -> NO pre-configured candidate (spoofed) cell ")
                  << targetCellId << (forged ? " [FORGED]" : " [legit]") << std::endl;
    }
    Simulator::ScheduleNow(&LtmExecuteSwitch, ueIdx, targetCellId, validCandidate);
}

static void
RlfProbeFire(uint32_t ueIdx)
{
    if (ueIdx >= g_ueNetDevs.GetN())
    {
        return;
    }
    UeHoState& s = g_ue[ueIdx];
    if (s.servingGnbDev == nullptr || s.inOutage)
    {
        return; // not connected / already failing: nothing sensible to force
    }
    Ptr<NetDevice> ueDev = g_ueNetDevs.Get(ueIdx);
    Ptr<MobilityModel> mm = ueDev->GetNode()->GetObject<MobilityModel>();
    Vector pos = mm->GetPosition();
    // Controlled failure (Step-5 validation of the outage path; NOT the Step-9 attacker). Model
    // the consequence of a forged mis-switch the 3GPP-faithful way: command the UE to switch to a
    // (real, neighbouring) target it then cannot complete random access to. We name a real target
    // cell and drop that target's RACH preambles (nr TestDropRachPreambles), so the UE exhausts
    // PreambleTransMax -> HandoverFailureMaxRach -> the UE falls back to RRC re-establishment on a
    // reachable cell. The whole outage (command -> failed RACH -> re-establishment -> restored)
    // is what the Step-5 machinery times. RACH-drop is cleared shortly after so later procedures
    // are unaffected.
    uint16_t target = NearestNeighbourCell(pos, s.servingCellId);
    if (target == 0)
    {
        return; // no neighbour to name as the forged target
    }
    std::cout << std::fixed << std::setprecision(4) << Simulator::Now().GetSeconds()
              << "s  RLF-PROBE  forcing UE" << ueIdx << " (serving cell " << s.servingCellId
              << ") a failing switch to cell " << target << " (RACH dropped -> HO failure)"
              << std::endl;
    s.forgedActive = true;
    s.hoInProgress = true;
    SetRachDropAtCell(target, true);
    g_nrHelper->HandoverRequest(MilliSeconds(0), ueDev, s.servingGnbDev, target);
    // Clear the RACH drop after the failure has certainly resolved, so it does not perturb any
    // later (legitimate) access to that cell.
    Simulator::Schedule(MilliSeconds(1500), &SetRachDropAtCell, target, false);
}

// -------------------------------------------------------------------------------------
// Steps 8-9: perform the cell switch at an opportune moment for UE ueIdx, applying the
// attacker's overshadow if this UE is a victim.
//
// Threat model (THESIS_ATTACK_SPEC §2-3): a co-located attacker blind-decodes the victim's
// PDCCH and, at the moment the network issues a legitimate LTM cell-switch MAC CE, overshadows
// it with a FORGED command carrying a spoofed Target Configuration ID (a wrong cell). Because
// LTM's MAC CE is below PDCP it is unciphered and unintegrity-protected, and the UE applies the
// switch before HARQ confirmation — so IF the forged frame decodes (capture effect), the UE
// mis-switches. Whether it decodes is drawn per-attempt from the link-tier P(forge-decode)
// table (boundary B2): u ~ U[0,1); lands iff u < P(margin). On a land we inject the forged
// switch to the farthest (wrong/unreachable-quality) cell -> RLF -> RRC re-establishment (DoS).
// On a miss, the legitimate switch to the correct (best) cell proceeds unharmed.
//
// This is unicast and single-/few-victim: only UEs flagged g_isVictim are targeted; all others
// hand over normally. Returns nothing; sets s.hoInProgress and updates serving state as usual.
// -------------------------------------------------------------------------------------
static void
DoOpportuneSwitch(uint32_t ueIdx, Ptr<NetDevice> ueDev, Ptr<NetDevice> srcDev, uint16_t bestCell)
{
    UeHoState& s = g_ue[ueIdx];
    bool victim = g_attackEnabled && ueIdx < g_isVictim.size() && g_isVictim[ueIdx];

    // The UE's RNTI at its serving cell -- the unicast address of the LTM cell-switch MAC CE.
    Ptr<NrUeRrc> ueRrc = ueDev->GetObject<NrUeNetDevice>()->GetRrc();
    uint16_t rnti = ueRrc ? ueRrc->GetRnti() : 0;

    if (victim)
    {
        double p = PForgeDecode(g_overshadowMarginDb);
        double u = g_attackRng->GetValue();
        s.forgedAttempts++;
        g_forgedAttempts++;
        if (u < p) // capture effect succeeds: the forged MAC CE decodes at the victim UE
        {
            Ptr<MobilityModel> mm = ueDev->GetNode()->GetObject<MobilityModel>();
            Vector pos = mm->GetPosition();
            // Spoofed Target Configuration ID: name a real neighbour cell as the (wrong) target.
            uint16_t target = NearestNeighbourCell(pos, s.servingCellId);
            if (target == 0)
            {
                target = bestCell; // single-neighbour fallback
            }
            s.forgedLanded++;
            g_forgedLanded++;
            // The overshadowing attacker injects a FORGED LTM cell-switch MAC CE directly at the
            // victim UE PHY (capture effect). The UE cannot authenticate it (below PDCP) and acts
            // on it: it processes the CE, and (via the LtmCellSwitchReceived trace) attempts the
            // commanded switch to the spoofed target -- which it cannot complete (RACH dropped) ->
            // HO failure -> RRC re-establishment (the DoS). Whether the forged frame decodes is the
            // §6 capture-probability draw above (boundary B2); ns-3 plays out the consequence.
            // Spoofed Target Configuration ID: an id the victim has NO pre-configured
            // candidate for (offset far outside the valid candidate id space). The target cell
            // field names a real neighbour so the failed activation has a concrete unprepared
            // target to attempt.
            uint16_t spoofedConfigId = 50000 + target;
            NrHelper::GetUePhy(ueDev, 0)->InjectForgedLtmCellSwitch(target, spoofedConfigId);
            if (g_verbose)
            {
                std::cout << std::fixed << std::setprecision(4) << Simulator::Now().GetSeconds()
                          << "s  FORGE-INJ  UE" << ueIdx << " (margin=" << g_overshadowMarginDb
                          << "dB, P=" << std::setprecision(2) << p << ", u=" << u
                          << " LANDED) attacker injects forged LTM MAC CE -> spoofed target cell "
                          << target << std::endl;
            }
            return;
        }
        if (g_verbose)
        {
            std::cout << std::fixed << std::setprecision(4) << Simulator::Now().GetSeconds()
                      << "s  FORGE-MISS UE" << ueIdx << " (margin=" << g_overshadowMarginDb
                      << "dB, P=" << std::setprecision(2) << p << ", u=" << u
                      << " missed) legit LTM command -> " << bestCell << " proceeds" << std::endl;
        }
        // fall through: the legitimate LTM command is issued
    }

    // Legitimate LTM cell-switch: the serving gNB issues the cell-switch MAC CE on the DL control
    // channel, addressed to this UE, naming the correct (best) target. The UE receives it over the
    // air and executes the switch via the LtmCellSwitchReceived trace. Skip if already best-served.
    if (bestCell == s.servingCellId || rnti == 0 || srcDev == nullptr)
    {
        return;
    }
    NrHelper::GetGnbPhy(srcDev, 0)->SendLtmCellSwitch(rnti, bestCell, bestCell);
}

// -------------------------------------------------------------------------------------
// Steps 8-9 (demonstration helper): the thesis's optional "Trigger" stage (§3.4) — the
// attacker degrades/spoofs the serving beam so the network issues an LTM command on cue,
// giving a known moment to overshadow. At small scale, natural cell-edge crossings take many
// seconds of costly simulation to occur; this forces one opportune switch per victim at a
// scheduled instant so the forged-vs-legit outcome can be demonstrated deterministically. The
// forge/miss decision still goes through the §6 probability table, exactly as for a natural
// trigger. -1/0 disables it.
// -------------------------------------------------------------------------------------
static void
AttackForceOpportunity()
{
    for (uint32_t i = 0; i < g_ueNetDevs.GetN(); ++i)
    {
        UeHoState& s = g_ue[i];
        if (i >= g_isVictim.size() || !g_isVictim[i] || s.hoInProgress || s.servingGnbDev == nullptr)
        {
            continue;
        }
        Ptr<NetDevice> ueDev = g_ueNetDevs.Get(i);
        Vector pos = ueDev->GetNode()->GetObject<MobilityModel>()->GetPosition();
        uint16_t bestCell;
        double bestDist;
        BestCellByDistance(pos, bestCell, bestDist);
        DoOpportuneSwitch(i, ueDev, s.servingGnbDev, bestCell);
    }
}

// -------------------------------------------------------------------------------------
// Periodic A3-like handover checker. For each UE: if a cell is stronger (closer) than the
// serving cell by more than the hysteresis and stays so for the time-to-trigger, trigger
// a fast MAC-style handover to it via NrHelper::HandoverRequest (immediate, delay 0).
// -------------------------------------------------------------------------------------
static void
HandoverCheck(Time interval, Time stop)
{
    Time now = Simulator::Now();
    for (uint32_t i = 0; i < g_ueNetDevs.GetN(); ++i)
    {
        UeHoState& s = g_ue[i];
        // Skip UEs mid-handover, uninitialised, or captured by a landed forged switch (the
        // mis-switched victim must be left to the RLF/re-establishment path, not rescued by
        // the benign geometric HO oracle — the network is out of the loop after an LTM MAC CE).
        if (s.hoInProgress || s.servingGnbDev == nullptr || s.forgedActive)
        {
            continue;
        }
        Ptr<NetDevice> ueDev = g_ueNetDevs.Get(i);
        Ptr<MobilityModel> mm = ueDev->GetNode()->GetObject<MobilityModel>();
        Vector pos = mm->GetPosition();

        uint16_t bestCell;
        double bestDist;
        BestCellByDistance(pos, bestCell, bestDist);
        double servingDist = CalculateDistance(pos, g_cellPos[s.servingCellId]);

        if (bestCell != s.servingCellId && (servingDist - bestDist) > g_hysteresisM)
        {
            if (s.candidateCellId == bestCell)
            {
                if (now - s.candidateSince >= g_ttt)
                {
                    // Opportune cell-switch moment: the network is about to issue a legitimate
                    // LTM switch to bestCell. If this UE is an attacker's victim, the forged
                    // overshadow may hijack it (Steps 8-9); otherwise the legit switch proceeds.
                    // servingGnbDev/cellId are updated here (best/worst) and again on HO-END-OK.
                    Ptr<NetDevice> srcDev = s.servingGnbDev;
                    DoOpportuneSwitch(i, ueDev, srcDev, bestCell);
                    s.candidateCellId = 0;
                }
            }
            else
            {
                s.candidateCellId = bestCell;
                s.candidateSince = now;
            }
        }
        else
        {
            s.candidateCellId = 0;
        }
    }
    if (now + interval < stop)
    {
        Simulator::Schedule(interval, &HandoverCheck, interval, stop);
    }
}

// -------------------------------------------------------------------------------------
// Summary statistics over a vector of samples (all in ms).
// -------------------------------------------------------------------------------------
static void
PrintStats(const std::string& label, std::vector<double> v)
{
    if (v.empty())
    {
        std::cout << label << ": no samples" << std::endl;
        return;
    }
    std::sort(v.begin(), v.end());
    double sum = 0;
    for (double x : v)
    {
        sum += x;
    }
    double mean = sum / v.size();
    auto pct = [&](double p) {
        double idx = p * (v.size() - 1);
        size_t lo = static_cast<size_t>(std::floor(idx));
        size_t hi = static_cast<size_t>(std::ceil(idx));
        double frac = idx - lo;
        return v[lo] * (1.0 - frac) + v[hi] * frac;
    };
    std::cout << std::fixed << std::setprecision(3) << label << ": n=" << v.size()
              << " mean=" << mean << " median=" << pct(0.5) << " p95=" << pct(0.95)
              << " min=" << v.front() << " max=" << v.back() << " (ms)" << std::endl;
}

int
main(int argc, char* argv[])
{
    // ------------------------------- Parameters --------------------------------------
    uint16_t numCells = 7;
    uint16_t numUes = 10;
    double ueSpeedKmph = 60.0;
    Time simTime = Seconds(5.0);
    uint32_t rngSeed = 1;
    uint32_t rngRun = 1;
    double timeToTriggerMs = 320.0; // spec §5
    double hysteresisMeters = 20.0;

    // ---- Step 5: RLF / RRC re-establishment parameters + controlled failure probe ----
    // RLF-detection timers are exposed so later steps (and this validation) can control how
    // quickly a lost link is declared failed. Defaults match nr's 3GPP-derived defaults
    // (T310=1000 ms, N310=6, N311=2) so the baseline is untouched; the probe run below
    // shortens them to keep the whole outage inside a tractable sim window.
    double t310Ms = 1000.0;
    uint32_t n310 = 6;
    uint32_t n311 = 2;
    bool useReestablishment = true;
    // Controlled failure probe (validation of the failure path; -1 disables it entirely).
    int32_t rlfProbeUe = -1;
    double rlfProbeTimeMs = 2000.0;

    // ---- Steps 8-9: forged-handover ATTACK controls (small-scale demonstration) ----
    bool attackEnabled = false;       // master on/off for the overshadowing attacker
    uint32_t numAttackers = 1;        // overshadowing sources = number of victim UEs targeted
    double overshadowMarginDb = 4.0;  // attacker-to-legit power margin (dB); indexes the §6 table
    double attackForceTimeMs = 0.0;   // >0: force one opportune switch per victim at this time

    double interSiteDistance = 250.0;
    double centralFrequency = 4.0e9;
    double bandwidth = 20.0e6;
    uint16_t numerology = 1;
    double gnbTxPowerDbm = 43.0;
    double gnbHeight = 25.0;
    double ueHeight = 1.5;

    // DL is high-rate/small-packet to give fine (~0.3 ms) interruption resolution;
    // UEs are spread over many cells so aggregate load stays well within cell capacity.
    uint32_t dlPacketSize = 300;
    uint32_t ulPacketSize = 300;
    uint32_t dlLambda = 1000; // packets/s DL (~1 ms spacing) — resolves the interruption gap
    // UL default OFF. NR's half-duplex PHY guards (nr-spectrum-phy.cc "Cannot TX while RX" /
    // "gNB transmission overlaps") deliberately fatal-error if a UE fires a UL grant across a
    // handover transition, because NR does not implement lossless HO. The upstream nr handover
    // tests respect this by PAUSING traffic over the HO window rather than patching the guards.
    // We keep DL flowing across the switch (that is exactly the interruption we measure) and
    // leave UL off by default so no UL grant collides with the transition. Enable UL only for
    // no-handover / steady-state throughput characterization (Step 6 will add the nr-style
    // per-UE UL pause around dynamic HO instants if UL-during-HO is needed).
    uint32_t ulLambda = 0; // packets/s UL (0 = disabled; see note above)

    std::string outputDir = "./";
    std::string simTag = "ltm-baseline";
    bool verbose = false;

    bool printForgeTable = false; // unit-check the section-6 P(forge-decode) table, then exit
    CommandLine cmd(__FILE__);
    cmd.AddValue("numCells", "Number of gNBs in the urban grid (7..19 in the sweep)", numCells);
    cmd.AddValue("numUes", "Total number of UEs (50..300 in the sweep)", numUes);
    cmd.AddValue("ueSpeedKmph", "UE speed in km/h (3/30/60/120 in the sweep)", ueSpeedKmph);
    cmd.AddValue("simTime", "Total simulation time", simTime);
    cmd.AddValue("rngSeed", "RNG seed (SeedManager seed)", rngSeed);
    cmd.AddValue("rngRun", "RNG run number (SeedManager run)", rngRun);
    cmd.AddValue("timeToTriggerMs", "A3-like time-to-trigger in ms (spec = 320)", timeToTriggerMs);
    cmd.AddValue("hysteresisMeters",
                 "Distance hysteresis: target must be closer than serving by this margin",
                 hysteresisMeters);
    cmd.AddValue("interSiteDistance", "gNB inter-site distance in metres", interSiteDistance);
    cmd.AddValue("centralFrequency", "Carrier centre frequency in Hz", centralFrequency);
    cmd.AddValue("bandwidth", "Carrier bandwidth in Hz", bandwidth);
    cmd.AddValue("t310Ms", "RLF T310 timer in ms (radio link declared failed on expiry)", t310Ms);
    cmd.AddValue("n310", "RLF N310: out-of-sync indications before T310 starts", n310);
    cmd.AddValue("n311", "RLF N311: in-sync indications needed to stop T310", n311);
    cmd.AddValue("useReestablishment", "Enable RRC connection re-establishment after RLF",
                 useReestablishment);
    cmd.AddValue("rlfProbeUe",
                 "Controlled failure probe: force this UE index to a wrong (farthest) target "
                 "cell to provoke RLF+re-establishment; -1 disables (validation only, not the "
                 "Step-9 attacker)",
                 rlfProbeUe);
    cmd.AddValue("rlfProbeTimeMs", "Time (ms) at which the RLF probe fires", rlfProbeTimeMs);
    cmd.AddValue("attackEnabled", "Enable the forged-handover overshadowing attacker (Steps 8-9)",
                 attackEnabled);
    cmd.AddValue("numAttackers",
                 "Number of overshadowing attackers = number of victim UEs targeted (UE 0..N-1)",
                 numAttackers);
    cmd.AddValue("overshadowMarginDb",
                 "Attacker-to-legit power margin in dB; sets P(forge-decode) via the §6 table "
                 "(0,1,2,3,4,6,8 dB -> .37,.42,.46,.50,.54,.63,.71)",
                 overshadowMarginDb);
    cmd.AddValue("attackForceTimeMs",
                 "If >0, force one opportune cell-switch per victim at this time (models the "
                 "thesis's optional §3.4 trigger stage) for deterministic demonstration; the "
                 "forge/miss draw still uses the §6 table",
                 attackForceTimeMs);
    cmd.AddValue("dlLambda", "DL packets per second per UE", dlLambda);
    cmd.AddValue("ulLambda", "UL packets per second per UE (0 disables UL traffic)", ulLambda);
    cmd.AddValue("outputDir", "Directory for output files", outputDir);
    cmd.AddValue("simTag", "Tag appended to output filenames", simTag);
    cmd.AddValue("verbose", "Print per-event handover logs", verbose);
    cmd.AddValue("printForgeTable", "Unit-check PForgeDecode(margin) then exit", printForgeTable);
    cmd.Parse(argc, argv);
    if (printForgeTable)
    {
        // Unit-check the section-6 link-tier table + interpolation (boundary B2): exact
        // tabulated points (must reproduce the thesis), midpoints (linear mean of the
        // bracketing points), and out-of-range margins (must clamp).
        std::cout << std::fixed << std::setprecision(4);
        std::cout << "# PForgeDecode(margin) unit-check (THESIS_ATTACK_SPEC section 6)\n";
        std::cout << "# exact points (expect .37 .42 .46 .50 .54 .63 .71):\n";
        for (double m : {0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0})
        {
            std::cout << "  margin=" << m << " dB -> P=" << PForgeDecode(m) << "\n";
        }
        std::cout << "# interpolated midpoints (expect linear mean of bracketing points):\n";
        for (double m : {0.5, 2.5, 5.0, 7.0})
        {
            std::cout << "  margin=" << m << " dB -> P=" << PForgeDecode(m) << "\n";
        }
        std::cout << "# out-of-range (expect clamp to .37 below 0 dB, .71 above 8 dB):\n";
        for (double m : {-5.0, 12.0})
        {
            std::cout << "  margin=" << m << " dB -> P=" << PForgeDecode(m) << "\n";
        }
        return 0;
    }


    NS_ABORT_MSG_IF(numCells < 2, "Need at least 2 gNBs for handover");
    NS_ABORT_MSG_IF(numUes < 1, "Need at least 1 UE");

    g_hysteresisM = hysteresisMeters;
    g_ttt = MilliSeconds(static_cast<uint64_t>(timeToTriggerMs));
    g_verbose = verbose;

    RngSeedManager::SetSeed(rngSeed);
    RngSeedManager::SetRun(rngRun);

    // Steps 8-9: attacker setup. Victims are the first numAttackers UEs (unicast, targeted).
    g_attackEnabled = attackEnabled;
    g_overshadowMarginDb = overshadowMarginDb;
    g_isVictim.assign(numUes, false);
    if (attackEnabled)
    {
        uint32_t nv = std::min<uint32_t>(numAttackers, numUes);
        for (uint32_t i = 0; i < nv; ++i)
        {
            g_isVictim[i] = true;
        }
    }
    // Dedicated RNG stream for the per-attempt forge-decode Bernoulli draw, so the attack
    // outcome is reproducible from (rngSeed,rngRun) and independent of the channel/traffic RNG.
    g_attackRng = CreateObject<UniformRandomVariable>();
    g_attackRng->SetAttribute("Min", DoubleValue(0.0));
    g_attackRng->SetAttribute("Max", DoubleValue(1.0));
    g_attackRng->SetStream(777);

    Config::SetDefault("ns3::NrRlcUm::MaxTxBufferSize", UintegerValue(999999999));

    // Step 5: RLF-detection timers and re-establishment behaviour. These govern the
    // failure path (mis-switch -> out-of-sync -> T310 -> RLF -> re-establishment).
    Config::SetDefault("ns3::NrUeRrc::T310", TimeValue(MilliSeconds(static_cast<uint64_t>(t310Ms))));
    Config::SetDefault("ns3::NrUeRrc::N310", UintegerValue(n310));
    Config::SetDefault("ns3::NrUeRrc::N311", UintegerValue(n311));
    Config::SetDefault("ns3::NrUeRrc::UseRrcReestablishment", BooleanValue(useReestablishment));
    Config::SetDefault("ns3::NrGnbRrc::UseRrcReestablishment", BooleanValue(useReestablishment));
    // Handover-failure (RACH) configuration, used by the forged-mis-switch model: a UE commanded
    // to a target whose RACH is dropped exhausts PreambleTransMax quickly and the handover fails
    // (HandoverFailureMaxRach) -> RRC re-establishment. Small PreambleTransMax makes the failure
    // resolve fast; normal (undropped) access still succeeds on the first attempt.
    Config::SetDefault("ns3::NrGnbMac::PreambleTransMax", UintegerValue(3));

    // ------------------------------ gNB grid layout ----------------------------------
    uint32_t cols = static_cast<uint32_t>(std::ceil(std::sqrt(static_cast<double>(numCells))));
    uint32_t rows = static_cast<uint32_t>(std::ceil(static_cast<double>(numCells) / cols));

    NodeContainer gnbNodes;
    gnbNodes.Create(numCells);

    Ptr<ListPositionAllocator> gnbPositionAlloc = CreateObject<ListPositionAllocator>();
    for (uint16_t i = 0; i < numCells; ++i)
    {
        uint32_t r = i / cols;
        uint32_t c = i % cols;
        Vector p(c * interSiteDistance, r * interSiteDistance, gnbHeight);
        gnbPositionAlloc->Add(p);
        g_gnbPositions.push_back(p);
    }
    MobilityHelper gnbMobility;
    gnbMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    gnbMobility.SetPositionAllocator(gnbPositionAlloc);
    gnbMobility.Install(gnbNodes);

    double xMin = -interSiteDistance / 2.0;
    double xMax = (cols - 1) * interSiteDistance + interSiteDistance / 2.0;
    double yMin = -interSiteDistance / 2.0;
    double yMax = (rows - 1) * interSiteDistance + interSiteDistance / 2.0;

    // ------------------------------- UE mobility -------------------------------------
    NodeContainer ueNodes;
    ueNodes.Create(numUes);
    double ueSpeedMps = ueSpeedKmph / 3.6;

    Ptr<UniformRandomVariable> xPos = CreateObject<UniformRandomVariable>();
    xPos->SetAttribute("Min", DoubleValue(xMin));
    xPos->SetAttribute("Max", DoubleValue(xMax));
    Ptr<UniformRandomVariable> yPos = CreateObject<UniformRandomVariable>();
    yPos->SetAttribute("Min", DoubleValue(yMin));
    yPos->SetAttribute("Max", DoubleValue(yMax));

    Ptr<ListPositionAllocator> uePositionAlloc = CreateObject<ListPositionAllocator>();
    for (uint16_t i = 0; i < numUes; ++i)
    {
        uePositionAlloc->Add(Vector(xPos->GetValue(), yPos->GetValue(), ueHeight));
    }

    // Constant-SPEED, near-straight-line mobility: distance-mode random walk keeps each
    // UE on a fixed heading for a long run (1 km) before turning, bouncing off the
    // deployment bounds. This gives large net displacement so UEs genuinely traverse many
    // cell edges (generating handovers), while holding speed exactly at ueSpeedKmph.
    MobilityHelper ueMobility;
    ueMobility.SetMobilityModel(
        "ns3::RandomWalk2dMobilityModel",
        "Mode", StringValue("Distance"),
        "Distance", DoubleValue(1000.0),
        "Speed",
        StringValue("ns3::ConstantRandomVariable[Constant=" + std::to_string(ueSpeedMps) + "]"),
        "Bounds", RectangleValue(Rectangle(xMin, xMax, yMin, yMax)));
    ueMobility.SetPositionAllocator(uePositionAlloc);
    ueMobility.Install(ueNodes);

    // --------------------------------- NR setup --------------------------------------
    Ptr<NrPointToPointEpcHelper> nrEpcHelper = CreateObject<NrPointToPointEpcHelper>();
    Ptr<IdealBeamformingHelper> beamformingHelper = CreateObject<IdealBeamformingHelper>();
    Ptr<NrHelper> nrHelper = CreateObject<NrHelper>();
    nrHelper->SetBeamformingHelper(beamformingHelper);
    nrHelper->SetEpcHelper(nrEpcHelper);
    g_nrHelper = nrHelper;

    CcBwpCreator ccBwpCreator;
    CcBwpCreator::SimpleOperationBandConf bandConf(centralFrequency, bandwidth, 1);
    OperationBandInfo band = ccBwpCreator.CreateOperationBandContiguousCc(bandConf);

    Ptr<NrChannelHelper> channelHelper = CreateObject<NrChannelHelper>();
    channelHelper->ConfigureFactories("UMa", "Default", "ThreeGpp");
    channelHelper->SetChannelConditionModelAttribute("UpdatePeriod", TimeValue(MilliSeconds(0)));
    channelHelper->SetPathlossAttribute("ShadowingEnabled", BooleanValue(false));
    channelHelper->AssignChannelsToBands({band});
    BandwidthPartInfoPtrVector allBwps = CcBwpCreator::GetAllBwps({band});

    beamformingHelper->SetAttribute("BeamformingMethod",
                                    TypeIdValue(DirectPathBeamforming::GetTypeId()));
    nrEpcHelper->SetAttribute("S1uLinkDelay", TimeValue(MilliSeconds(0)));

    nrHelper->SetUeAntennaAttribute("NumRows", UintegerValue(1));
    nrHelper->SetUeAntennaAttribute("NumColumns", UintegerValue(2));
    nrHelper->SetUeAntennaAttribute("AntennaElement",
                                    PointerValue(CreateObject<IsotropicAntennaModel>()));
    nrHelper->SetGnbAntennaAttribute("NumRows", UintegerValue(4));
    nrHelper->SetGnbAntennaAttribute("NumColumns", UintegerValue(8));
    nrHelper->SetGnbAntennaAttribute("AntennaElement",
                                     PointerValue(CreateObject<IsotropicAntennaModel>()));

    NetDeviceContainer gnbNetDev = nrHelper->InstallGnbDevice(gnbNodes, allBwps);
    NetDeviceContainer ueNetDev = nrHelper->InstallUeDevice(ueNodes, allBwps);

    nrHelper->AssignStreams({.gnbDevs = gnbNetDev, .ueDevs = ueNetDev});

    for (uint32_t i = 0; i < gnbNetDev.GetN(); ++i)
    {
        NrHelper::GetGnbPhy(gnbNetDev.Get(i), 0)
            ->SetAttribute("Numerology", UintegerValue(numerology));
        NrHelper::GetGnbPhy(gnbNetDev.Get(i), 0)->SetTxPower(gnbTxPowerDbm);
    }

    // Build cellId -> {position, device} maps from the installed gNB devices.
    for (uint32_t j = 0; j < gnbNetDev.GetN(); ++j)
    {
        uint16_t cid = gnbNetDev.Get(j)->GetObject<NrGnbNetDevice>()->GetCellId();
        g_cellPos[cid] = g_gnbPositions[j];
        g_cellDev[cid] = gnbNetDev.Get(j);
        g_cellIds.push_back(cid);
    }

    // X2 interfaces between every pair of gNBs (required for handover).
    nrHelper->AddX2Interface(gnbNodes);

    // --------------------------- Core network + Internet -----------------------------
    auto [remoteHost, remoteHostAddr] = nrEpcHelper->SetupRemoteHost("100Gb/s", 2500, Seconds(0.0));

    InternetStackHelper internet;
    internet.Install(ueNodes);
    Ipv4InterfaceContainer ueIpIface = nrEpcHelper->AssignUeIpv4Address(NetDeviceContainer(ueNetDev));

    Ipv4StaticRoutingHelper ipv4RoutingHelper;
    for (uint32_t i = 0; i < ueNodes.GetN(); ++i)
    {
        Ptr<Ipv4StaticRouting> ueStaticRouting =
            ipv4RoutingHelper.GetStaticRouting(ueNodes.Get(i)->GetObject<Ipv4>());
        ueStaticRouting->SetDefaultRoute(nrEpcHelper->GetUeDefaultGatewayAddress(), 1);
    }

    nrHelper->AttachToClosestGnb(ueNetDev, gnbNetDev);

    g_ueNetDevs = ueNetDev;
    g_ue.resize(numUes);

    // Initialise per-UE serving state to the geometrically closest gNB (matches
    // AttachToClosestGnb), so the checker has a valid source cell/device from t=0.
    for (uint32_t i = 0; i < ueNetDev.GetN(); ++i)
    {
        Vector pos = ueNodes.Get(i)->GetObject<MobilityModel>()->GetPosition();
        uint16_t bestCell;
        double bestDist;
        BestCellByDistance(pos, bestCell, bestDist);
        g_ue[i].servingCellId = bestCell;
        g_ue[i].servingGnbDev = g_cellDev[bestCell];
    }

    // --------------------------------- Traffic ---------------------------------------
    uint16_t dlPort = 1234;
    uint16_t ulPort = 2000;
    ApplicationContainer serverApps;
    ApplicationContainer clientApps;
    Time appStart = MilliSeconds(300);

    UdpServerHelper ulSink(ulPort);
    serverApps.Add(ulSink.Install(remoteHost));

    for (uint32_t i = 0; i < ueNodes.GetN(); ++i)
    {
        Ptr<Node> ueNode = ueNodes.Get(i);
        Address ueAddr = ueIpIface.GetAddress(i);

        // DL sink on the UE, with a per-UE Rx trace for interruption measurement.
        UdpServerHelper dlSink(dlPort);
        ApplicationContainer dlServerApp = dlSink.Install(ueNode);
        dlServerApp.Get(0)->TraceConnectWithoutContext("RxWithAddresses",
                                                       MakeBoundCallback(&DlRxSink, i));
        serverApps.Add(dlServerApp);

        UdpClientHelper dlClient(ueAddr, dlPort);
        dlClient.SetAttribute("MaxPackets", UintegerValue(0xFFFFFFFF));
        dlClient.SetAttribute("PacketSize", UintegerValue(dlPacketSize));
        dlClient.SetAttribute("Interval", TimeValue(Seconds(1.0 / dlLambda)));
        clientApps.Add(dlClient.Install(remoteHost));

        if (ulLambda > 0)
        {
            UdpClientHelper ulClient(remoteHostAddr, ulPort);
            ulClient.SetAttribute("MaxPackets", UintegerValue(0xFFFFFFFF));
            ulClient.SetAttribute("PacketSize", UintegerValue(ulPacketSize));
            ulClient.SetAttribute("Interval", TimeValue(Seconds(1.0 / ulLambda)));
            clientApps.Add(ulClient.Install(ueNode));
        }
    }

    serverApps.Start(appStart);
    clientApps.Start(appStart);
    serverApps.Stop(simTime);
    clientApps.Stop(simTime);

    // ---------------------------------- Traces ---------------------------------------
    for (uint32_t i = 0; i < ueNetDev.GetN(); ++i)
    {
        Ptr<NrUeRrc> rrc = ueNetDev.Get(i)->GetObject<NrUeNetDevice>()->GetRrc();
        rrc->TraceConnectWithoutContext("HandoverStart", MakeBoundCallback(&HoStartSink, i));
        rrc->TraceConnectWithoutContext("HandoverEndOk", MakeBoundCallback(&HoEndOkSink, i));
        rrc->TraceConnectWithoutContext("HandoverEndError", MakeBoundCallback(&HoEndErrorSink, i));
        // Step 5: RLF / RRC re-establishment failure-path traces.
        rrc->TraceConnectWithoutContext("RadioLinkFailure", MakeBoundCallback(&RlfSink, i));
        rrc->TraceConnectWithoutContext("RadioLinkFailureCause", MakeBoundCallback(&RlfCauseSink, i));
        rrc->TraceConnectWithoutContext("StateTransition", MakeBoundCallback(&StateSink, i));
        // LTM: fired when the UE acts on a cell-switch MAC CE (legitimate or forged).
        rrc->TraceConnectWithoutContext("LtmCellSwitchReceived",
                                        MakeBoundCallback(&LtmCellSwitchSink, i));
        // LTM candidate PRE-CONFIGURATION (modelling the network delivering candidate target
        // configurations to the UE in advance over RRC). Every real cell is a candidate with
        // configId == cellId; a later cell-switch MAC CE activates one by its Target
        // Configuration ID. A forged/spoofed id outside this set has no candidate to activate.
        for (uint16_t cid : g_cellIds)
        {
            rrc->AddLtmCandidate(cid, cid);
        }
    }

    // Step 5: schedule the controlled failure probe (validation only), if requested.
    if (rlfProbeUe >= 0 && static_cast<uint32_t>(rlfProbeUe) < numUes)
    {
        Simulator::Schedule(MilliSeconds(static_cast<uint64_t>(rlfProbeTimeMs)),
                            &RlfProbeFire,
                            static_cast<uint32_t>(rlfProbeUe));
    }

    // Steps 8-9: schedule the forced opportune moment for the attack demonstration, if requested.
    if (attackEnabled && attackForceTimeMs > 0.0)
    {
        Simulator::Schedule(MilliSeconds(static_cast<uint64_t>(attackForceTimeMs)),
                            &AttackForceOpportunity);
    }

    FlowMonitorHelper flowmonHelper;
    NodeContainer endpointNodes;
    endpointNodes.Add(remoteHost);
    endpointNodes.Add(ueNodes);
    Ptr<FlowMonitor> monitor = flowmonHelper.Install(endpointNodes);

    // Fast MAC-triggered handover checker: start after initial attach, run to sim end.
    Simulator::Schedule(MilliSeconds(350), &HandoverCheck, MilliSeconds(20), simTime);

    std::cout << "=== LTM forged-handover — baseline (no attack) ===" << std::endl;
    std::cout << "gNBs=" << numCells << " (grid " << cols << "x" << rows
              << ", ISD=" << interSiteDistance << " m), UEs=" << numUes
              << ", speed=" << ueSpeedKmph << " km/h, freq=" << centralFrequency / 1e9
              << " GHz, BW=" << bandwidth / 1e6 << " MHz, TTT=" << timeToTriggerMs
              << " ms, hyst=" << hysteresisMeters << " m, simTime=" << simTime.GetSeconds()
              << " s, seed=" << rngSeed << ", run=" << rngRun << std::endl;

    Simulator::Stop(simTime);
    Simulator::Run();

    // ------------------- Mobility interruption time computation -----------------------
    // We report the baseline (no-attack) handover interruption two complementary ways:
    //
    //  (1) CELL-SWITCH EXECUTION TIME = HandoverEndOk - HandoverStart. This is the
    //      control-plane switch break (the time the UE is detached while it applies the
    //      switch). For our fast MAC-triggered NR handover it is ~2 ms, which is the
    //      direct proxy of the intra-BS LTM cell-switch budget quoted in the spec (~1-2 ms,
    //      "near-zero"). This is the headline baseline KPI.
    //
    //  (2) DL DATA-PLANE GAP = last DL packet delivered before, to first delivered after,
    //      the handover instant. This captures the full user-plane outage. It is larger
    //      than (1) (~tens of ms here) because NR's X2 handover is NOT make-before-break /
    //      lossless (RLC PDUs in flight on the source are not forwarded, and the target
    //      re-establishes grants after attach) -- a known property of the B1 proxy, stated
    //      as a modelling boundary. Under the forged-switch attack this gap balloons to
    //      hundreds of ms (RLF + RRC re-establishment), which is the DoS we quantify later.
    std::vector<double> interruptionsMs; // (2) DL data-plane gap straddling each HO
    std::vector<double> switchExecMs;    // (1) HandoverEndOk - HandoverStart
    std::vector<double> ambientGapsMs;   // all consecutive DL-rx gaps (context/sanity)
    uint32_t totalHo = 0;
    uint32_t totalHoFail = 0;

    // ---- Step 5: failure-path (RLF + RRC re-establishment) outage metrics ----
    // For each outage (CONNECTED_PHY_PROBLEM entry -> CONNECTED_NORMALLY return) we report:
    //  (A) CONTROL-PLANE outage = recovery - onset (RRC state-machine duration of the failure).
    //  (B) DATA-PLANE mobility interruption = last DL packet delivered before the onset ->
    //      first DL packet delivered after recovery, i.e. the gap in the delivered DL stream
    //      that straddles the failure. This is the precise "last good DL -> first restored DL"
    //      interruption the plan asks for, measured through the whole RLF+re-establishment
    //      recovery. Under the Step-9 forged switch this is the DoS-inflated KPI.
    // Unrecovered outages (UE never returns to CONNECTED_NORMALLY) are counted separately as
    // censored — their interruption is at least (simEnd - onset) but is not a completed sample.
    std::vector<double> outageCpMs;   // (A) control-plane outage durations
    std::vector<double> outageDpMs;   // (B) data-plane interruption through recovery
    uint32_t totalRlf = 0;
    uint32_t totalPhyProblem = 0;
    uint32_t totalReestabAttempt = 0;
    uint32_t totalReestabSuccess = 0;
    uint32_t totalCensoredOutage = 0;
    double simEndS = simTime.GetSeconds();

    for (uint32_t i = 0; i < numUes; ++i)
    {
        UeHoState& s = g_ue[i];
        totalHo += s.hoCount;
        totalHoFail += s.hoFailures;
        totalRlf += s.rlfCount;
        totalPhyProblem += s.phyProblemCount;
        totalReestabAttempt += s.reestabAttemptCount;
        totalReestabSuccess += s.reestabSuccessCount;
        std::sort(s.dlRxTimes.begin(), s.dlRxTimes.end());
        auto& rx = s.dlRxTimes;
        for (size_t k = 1; k < rx.size(); ++k)
        {
            ambientGapsMs.push_back((rx[k] - rx[k - 1]) * 1000.0);
        }
        for (auto& w : s.hoWindows)
        {
            switchExecMs.push_back((w.second - w.first) * 1000.0);
            double mid = 0.5 * (w.first + w.second);
            if (rx.size() < 2)
            {
                continue;
            }
            auto up = std::upper_bound(rx.begin(), rx.end(), mid);
            if (up == rx.begin() || up == rx.end())
            {
                continue; // handover outside the delivered stream
            }
            double after = *up;
            double before = *(up - 1);
            interruptionsMs.push_back((after - before) * 1000.0);
        }

        // Completed failure outages: control-plane + data-plane interruption.
        for (auto& ow : s.outageWindows)
        {
            double onset = ow.first;
            double recovery = ow.second;
            outageCpMs.push_back((recovery - onset) * 1000.0);
            // Data-plane: last DL rx at/before onset -> first DL rx at/after recovery.
            if (rx.size() >= 2)
            {
                auto lo = std::upper_bound(rx.begin(), rx.end(), onset); // first > onset
                auto hi = std::lower_bound(rx.begin(), rx.end(), recovery); // first >= recovery
                if (lo != rx.begin() && hi != rx.end())
                {
                    double before = *(lo - 1); // last DL delivered at/before onset
                    double after = *hi;        // first DL delivered at/after recovery
                    outageDpMs.push_back((after - before) * 1000.0);
                }
            }
        }
        // Censored: onset with no recovery by sim end.
        if (s.inOutage && s.outageOnset >= 0.0)
        {
            totalCensoredOutage++;
            std::cout << std::fixed << std::setprecision(4)
                      << "  [censored] UE" << i << " entered outage at " << s.outageOnset
                      << "s and had not recovered by sim end (" << simEndS
                      << "s): outage >= " << std::setprecision(1)
                      << (simEndS - s.outageOnset) * 1000.0 << " ms, lastCause="
                      << (s.lastRlfCause.empty() ? "UNKNOWN" : s.lastRlfCause) << std::endl;
        }
    }

    // ----------------------------- FlowMonitor summary -------------------------------
    monitor->CheckForLostPackets();
    Ptr<Ipv4FlowClassifier> classifier =
        DynamicCast<Ipv4FlowClassifier>(flowmonHelper.GetClassifier());
    FlowMonitor::FlowStatsContainer stats = monitor->GetFlowStats();
    uint64_t totalTx = 0;
    uint64_t totalRx = 0;
    double totalRxMbps = 0.0;
    uint64_t dlTx = 0, dlRx = 0, ulTx = 0, ulRx = 0;
    double dlMbps = 0.0, ulMbps = 0.0;
    double durationS = simTime.GetSeconds() - appStart.GetSeconds();
    for (auto it = stats.begin(); it != stats.end(); ++it)
    {
        totalTx += it->second.txPackets;
        totalRx += it->second.rxPackets;
        double mbps = (durationS > 0) ? it->second.rxBytes * 8.0 / durationS / 1e6 : 0.0;
        totalRxMbps += mbps;
        Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(it->first);
        if (t.destinationPort == dlPort) // remoteHost -> UE : downlink
        {
            dlTx += it->second.txPackets;
            dlRx += it->second.rxPackets;
            dlMbps += mbps;
        }
        else // UE -> remoteHost : uplink
        {
            ulTx += it->second.txPackets;
            ulRx += it->second.rxPackets;
            ulMbps += mbps;
        }
    }
    double lossPct = (totalTx > 0) ? 100.0 * (double)(totalTx - totalRx) / (double)totalTx : 0.0;
    double dlLossPct = (dlTx > 0) ? 100.0 * (double)(dlTx - dlRx) / (double)dlTx : 0.0;
    double ulLossPct = (ulTx > 0) ? 100.0 * (double)(ulTx - ulRx) / (double)ulTx : 0.0;
    std::cout << "=== Baseline run summary ===" << std::endl;
    std::cout << "Handover events=" << totalHo << " (failures=" << totalHoFail << ")"
              << ", switch-exec samples=" << switchExecMs.size()
              << ", DL data-plane samples=" << interruptionsMs.size() << std::endl;
    PrintStats("Cell-switch execution time (HO-END-OK - HO-START)", switchExecMs);
    PrintStats("DL data-plane interruption (gap straddling HO)", interruptionsMs);
    PrintStats("Ambient DL-gap (all consecutive, context)", ambientGapsMs);
    // ---- Step 5: RLF / RRC re-establishment (failure-path) summary ----
    std::cout << "--- Failure path (RLF / RRC re-establishment) ---" << std::endl;
    std::cout << "RLF firings=" << totalRlf << ", PHY-PROBLEM entries=" << totalPhyProblem
              << ", re-establishment attempts=" << totalReestabAttempt
              << ", recovered=" << totalReestabSuccess << ", censored (no recovery)="
              << totalCensoredOutage << std::endl;
    PrintStats("Failure outage — control-plane (recovery - onset)", outageCpMs);
    PrintStats("Failure interruption — data-plane (last good DL -> first restored DL)", outageDpMs);
    // ---- Steps 8-9: attack summary ----
    if (attackEnabled)
    {
        double pTab = PForgeDecode(overshadowMarginDb);
        double landRate = (g_forgedAttempts > 0)
                              ? static_cast<double>(g_forgedLanded) / g_forgedAttempts
                              : 0.0;
        std::cout << "--- Attack (forged LTM cell-switch) ---" << std::endl;
        std::cout << "ATTACK ON: victims=" << std::min<uint32_t>(numAttackers, numUes)
                  << " (UE0.." << (std::min<uint32_t>(numAttackers, numUes) - 1)
                  << "), margin=" << overshadowMarginDb << " dB, P(forge-decode)=" << std::fixed
                  << std::setprecision(3) << pTab << "; forged attempts=" << g_forgedAttempts
                  << ", landed=" << g_forgedLanded << " (observed rate=" << std::setprecision(3)
                  << landRate << ")" << std::endl;
    }
    else
    {
        std::cout << "--- Attack: DISABLED (baseline, no forged switches) ---" << std::endl;
    }
    std::cout << "Per-direction: DL tx=" << dlTx << " rx=" << dlRx << " loss=" << std::fixed
              << std::setprecision(2) << dlLossPct << "% thr=" << std::setprecision(3) << dlMbps
              << " Mbps | UL tx=" << ulTx << " rx=" << ulRx << " loss=" << std::setprecision(2)
              << ulLossPct << "% thr=" << std::setprecision(3) << ulMbps << " Mbps" << std::endl;
    std::cout << "Flows=" << stats.size() << " totalTxPkts=" << totalTx
              << " totalRxPkts=" << totalRx << " aggregateRxThroughput=" << std::fixed
              << std::setprecision(3) << totalRxMbps << " Mbps, packetLoss=" << std::setprecision(2)
              << lossPct << " %" << std::endl;

    // Machine-readable one-liner for later harness parsing. Reports both the DL data-plane
    // interruption (primary DoS metric) and the cell-switch execution time (LTM budget proxy).
    auto summarize = [](std::vector<double> v, double& mean, double& median, double& p95) {
        mean = median = p95 = 0.0;
        if (v.empty())
        {
            return;
        }
        std::sort(v.begin(), v.end());
        for (double x : v)
        {
            mean += x;
        }
        mean /= v.size();
        auto pct = [&](double p) {
            double idx = p * (v.size() - 1);
            size_t lo = (size_t)std::floor(idx);
            size_t hi = (size_t)std::ceil(idx);
            double frac = idx - lo;
            return v[lo] * (1 - frac) + v[hi] * frac;
        };
        median = pct(0.5);
        p95 = pct(0.95);
    };
    double dpMean, dpMedian, dpP95;      // DL data-plane interruption
    double swMean, swMedian, swP95;      // cell-switch execution time
    double ocpMean, ocpMedian, ocpP95;   // failure control-plane outage
    double odpMean, odpMedian, odpP95;   // failure data-plane interruption
    summarize(interruptionsMs, dpMean, dpMedian, dpP95);
    summarize(switchExecMs, swMean, swMedian, swP95);
    summarize(outageCpMs, ocpMean, ocpMedian, ocpP95);
    summarize(outageDpMs, odpMean, odpMedian, odpP95);
    std::cout << "RESULT_BASELINE,seed=" << rngSeed << ",run=" << rngRun
              << ",numCells=" << numCells << ",numUes=" << numUes << ",speedKmph=" << ueSpeedKmph
              << ",hoEvents=" << totalHo << ",hoFail=" << totalHoFail
              << ",dpN=" << interruptionsMs.size() << ",dpMeanMs=" << std::setprecision(4) << dpMean
              << ",dpMedianMs=" << dpMedian << ",dpP95Ms=" << dpP95
              << ",swN=" << switchExecMs.size() << ",swMeanMs=" << swMean
              << ",swMedianMs=" << swMedian << ",swP95Ms=" << swP95
              << ",dlLossPct=" << dlLossPct << ",ulLossPct=" << ulLossPct
              << ",dlThrMbps=" << dlMbps << ",ulThrMbps=" << ulMbps << std::endl;
    // Step 5: machine-readable failure-path record (RLF + RRC re-establishment outage).
    std::cout << "RESULT_RLF,seed=" << rngSeed << ",run=" << rngRun
              << ",numCells=" << numCells << ",numUes=" << numUes << ",speedKmph=" << ueSpeedKmph
              << ",rlfProbeUe=" << rlfProbeUe << ",t310Ms=" << t310Ms << ",n310=" << n310
              << ",n311=" << n311 << ",rlf=" << totalRlf << ",phyProblem=" << totalPhyProblem
              << ",reestabAttempt=" << totalReestabAttempt << ",recovered=" << totalReestabSuccess
              << ",censored=" << totalCensoredOutage
              << ",ocpN=" << outageCpMs.size() << ",ocpMeanMs=" << std::setprecision(4) << ocpMean
              << ",ocpMedianMs=" << ocpMedian << ",ocpP95Ms=" << ocpP95
              << ",odpN=" << outageDpMs.size() << ",odpMeanMs=" << odpMean
              << ",odpMedianMs=" << odpMedian << ",odpP95Ms=" << odpP95 << std::endl;
    // Steps 8-9: machine-readable attack record.
    std::cout << "RESULT_ATTACK,seed=" << rngSeed << ",run=" << rngRun
              << ",attackEnabled=" << (attackEnabled ? 1 : 0)
              << ",numAttackers=" << numAttackers << ",marginDb=" << overshadowMarginDb
              << ",pForge=" << std::setprecision(4) << PForgeDecode(overshadowMarginDb)
              << ",forgedAttempts=" << g_forgedAttempts << ",forgedLanded=" << g_forgedLanded
              << ",rlf=" << totalRlf << ",recovered=" << totalReestabSuccess
              << ",odpN=" << outageDpMs.size() << ",odpMeanMs=" << odpMean
              << ",odpP95Ms=" << odpP95 << std::endl;

    Simulator::Destroy();
    return 0;
}
