#!/usr/bin/env bash
# ATK-05a full campaign.  Reference configuration plus one-factor-at-a-time sweeps around it.
# Every set writes one CSV into results/ and skips itself if that CSV already exists, so the
# script is safe to re-invoke after an interruption.
set -u
cd "$(dirname "$0")"
BIN=./build/atk05a_campaign
R=results
mkdir -p "$R" logs

TRIALS=${TRIALS:-2000}
TRIALS_PDP=${TRIALS_PDP:-1000}

# Reference configuration: format B4, PRACH SCS 30 kHz, uplink mu=1, ZCZ 15, SNR 10 dB,
# flat Rayleigh per path, victim at its own geometric delay (taken as the time origin).
REF="--fmt B4 --scs 30 --mu 1"

# Repeater excess delay, in T_A units.  Integers are exactly bin-aligned (2 IDFT bins per
# T_A unit at every numerology), which is the attacker's natural choice.
DELTA_FULL="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,28,32,40,46"
DELTA_CUT="2,4,6,7,8,9,10,12,16,20"
# Relay received power relative to the direct path, in dB.
REL_FULL="-12,-11,-10,-9,-8,-7,-6,-5,-4,-3,-2,-1,0,1,2,3,4,5,6,7,8,9,10,12,15"
REL_CUT="-6,-3,-1,0,1,3,6"

run () {  # run <name> <args...>
  local name=$1; shift
  if [ -s "$R/$name.csv" ]; then echo "skip  $name"; return; fi
  echo "run   $name"
  $BIN "$@" > "$R/$name.csv" 2>> logs/campaign_err.log
}

echo "=== gates ==="
$BIN --mode gates --zcz-list 0,2,4,6,8,9,11,13,15 > logs/gates.log 2>&1
tail -n +2 logs/gates.log | grep -E "FAIL" && { echo "GATE FAILED - refusing to report"; exit 1; }
echo "all gates pass"

# ---------------------------------------------------------------- A: main surface
run A_surface_rayleigh $REF --mode grid --fading rayleigh --zcz-list 15 --snr-list 10 \
    --delta-units "$DELTA_FULL" --rel-list "$REL_FULL" --trials "$TRIALS"

run A_surface_pdp300 $REF --mode grid --fading pdp --ds-ns 300 --nof-taps 20 --zcz-list 15 \
    --snr-list 10 --delta-units "$DELTA_FULL" --rel-list "$REL_FULL" --trials "$TRIALS_PDP"

run A_surface_none $REF --mode grid --fading none --zcz-list 15 --snr-list 10 \
    --delta-units "$DELTA_FULL" --rel-list "$REL_FULL" --trials 200

# ---------------------------------------------------------------- B: fading model
for F in none rayleigh; do
  run "B_fading_$F" $REF --mode grid --fading $F --zcz-list 15 --snr-list 10 \
      --delta-units "$DELTA_CUT" --rel-list "$REL_CUT" --trials "$TRIALS"
done
for DS in 100 300 1000 1400; do
  run "B_fading_pdp$DS" $REF --mode grid --fading pdp --ds-ns $DS --nof-taps 20 --zcz-list 15 \
      --snr-list 10 --delta-units "$DELTA_CUT" --rel-list "$REL_CUT" --trials "$TRIALS_PDP"
done

# ---------------------------------------------------------------- C: SNR
run C_snr $REF --mode grid --fading rayleigh --zcz-list 15 \
    --snr-list -6,-3,0,3,6,10,15,20,30 --delta-units "$DELTA_CUT" --rel-list "$REL_CUT" \
    --trials "$TRIALS"

# ---------------------------------------------------------------- D: zeroCorrelationZoneConfig
run D_zcz $REF --mode grid --fading rayleigh --zcz-list 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
    --snr-list 10 --delta-units "$DELTA_FULL" --rel-list 0,3,6 --trials "$TRIALS"

# ---------------------------------------------------------------- E: victim absent
run E_absent $REF --mode absent --fading rayleigh --zcz-list 15 \
    --snr-list -9,-6,-3,0,3,6,10,20 --delta-units "$DELTA_FULL" --rel-list 0 --trials "$TRIALS"

# ---------------------------------------------------------------- F: numerology
run F_mu1_scs30 --fmt B4 --scs 30 --mu 1 --mode grid --fading rayleigh --zcz-list 15 \
    --snr-list 10 --delta-units "$DELTA_CUT" --rel-list "$REL_CUT" --trials "$TRIALS"
run F_mu0_scs15 --fmt B4 --scs 15 --mu 0 --mode grid --fading rayleigh --zcz-list 15 \
    --snr-list 10 --delta-units "$DELTA_CUT" --rel-list "$REL_CUT" --trials "$TRIALS"
run F_mu2_scs30 --fmt B4 --scs 30 --mu 2 --mode grid --fading rayleigh --zcz-list 15 \
    --snr-list 10 --delta-units "$DELTA_CUT" --rel-list "$REL_CUT" --trials "$TRIALS"

# ---------------------------------------------------------------- G: preamble format
for FMT in A1 A2 A3 B4 C2; do
  run "G_fmt_$FMT" --fmt $FMT --scs 30 --mu 1 --mode grid --fading rayleigh --zcz-list 15 \
      --snr-list 10 --delta-units "$DELTA_CUT" --rel-list "$REL_CUT" --trials "$TRIALS"
done

# ---------------------------------------------------------------- H: victim geometric delay
# The victim is not always at bin 0.  A non-zero victim delay makes the victim pay its own
# off-grid penalty, which partly cancels the attacker's.
for TV in 0.0 0.0651 0.1302 0.5 1.0 2.0 4.0; do
  run "H_tauv_$TV" $REF --mode grid --fading rayleigh --zcz-list 15 --snr-list 10 \
      --tau-v-us $TV --delta-units "$DELTA_CUT" --rel-list "$REL_CUT" --trials "$TRIALS"
done

# ---------------------------------------------------------------- I: raw trial dump
run I_raw_reference $REF --mode grid --fading rayleigh --zcz-list 15 --snr-list 10 \
    --delta-units 7,9,12 --rel-list 0,3,6 --trials 2000 --raw "$R/I_raw_trials.csv"

echo "=== concatenating ==="
python3 - <<'PY'
import csv, glob, os
out = "results/ALL_atk05a.csv"
rows, hdr = [], None
for f in sorted(glob.glob("results/[A-I]_*.csv")):
    if os.path.basename(f) in ("I_raw_trials.csv",) or "G5" in f:
        continue
    with open(f) as fh:
        r = csv.reader(fh)
        try:
            h = next(r)
        except StopIteration:
            continue
        if h[0] != "mode":
            continue
        hdr = hdr or ["set"] + h
        tag = os.path.basename(f)[:-4]
        for row in r:
            if row:
                rows.append([tag] + row)
with open(out, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(hdr)
    w.writerows(rows)
print(f"{out}: {len(rows)} rows")
PY
echo "=== done ==="
