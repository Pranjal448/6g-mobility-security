#!/usr/bin/env bash
# Does a scheduling request survive the timing error Finding 1 induces?
# Each set writes one CSV into results/ and skips itself if that CSV already exists.
set -u
cd "$(dirname "$0")"
BIN=./build/sr_pucch_campaign
R=results
mkdir -p "$R" logs

TRIALS=${TRIALS:-2000}
ERR_FULL="-14,-12,-11,-10,-9,-8,-7,-6,-5,-4,-3,-2,-1,0,1,2,3,4,5,6,7,8,9,10,11,12,14"
ERR_FINE="0,0.5,1,1.5,2,2.5,3,3.5,4,4.5,5,5.5,6,6.5,7,8,9,10"

run () { local name=$1; shift
  if [ -s "$R/$name.csv" ]; then echo "skip  $name"; return; fi
  echo "run   $name"
  $BIN "$@" > "$R/$name.csv" 2>> logs/err.log
}

echo "=== geometry gates ==="
$BIN --mode gates | tee logs/gates.log
grep -q FAIL logs/gates.log && { echo "GATE FAILED"; exit 1; }

# A: the main curve, both signs, at the SNR the rest of the report uses.
run A_main_rayleigh --fading rayleigh --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"
run A_main_awgn     --fading none     --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"
run A_main_pdp300   --fading pdp --ds-ns 300 --nof-taps 20 --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"

# B: fine resolution on the early side, which is the side Finding 1 drives.
run B_fine_rayleigh --fading rayleigh --snr-list 10 --err-list "$ERR_FINE" --trials "$TRIALS"
run B_fine_awgn     --fading none     --snr-list 10 --err-list "$ERR_FINE" --trials "$TRIALS"

# C: does a better link rescue the request?  Sweep SNR at the boundary of Finding 1.
run C_snr --fading rayleigh --snr-list -3,0,3,6,10,15,20,25,30 \
    --err-list 0,2,4,6,7,8,9,12 --trials "$TRIALS"

# D: receive diversity and a second PUCCH symbol - the defender's free parameters.
for P in 1 2 4; do
  run "D_ports_$P" --ports $P --fading rayleigh --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"
done
for S in 1 2; do
  run "D_sym_$S" --nof-sym $S --start-sym 12 --fading rayleigh --snr-list 10 \
      --err-list "$ERR_FULL" --trials "$TRIALS"
done

# E: numerology.  The claim is that the boundary is fixed in T_A units at every spacing.
run E_scs15  --scs 15  --fading rayleigh --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"
run E_scs30  --scs 30  --fading rayleigh --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"
run E_scs60  --scs 60  --fading rayleigh --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"
run E_scs120 --scs 120 --fading rayleigh --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"

# F: an empty band, to show the collapse is not interference from other users.
run F_empty --empty-band --fading rayleigh --snr-list 10 --err-list "$ERR_FULL" --trials "$TRIALS"

# G: the receiver window offset, at zero timing error.  Shows the data channel's
# early-side remedy is unavailable to the control channel.
run G_window --fading none --snr-list 20 --err-list 0 --trials 500 --win-units 0
for W in 1 2 3 4 5 6 8; do
  run "G_window_$W" --fading none --snr-list 20 --err-list 0 --trials 500 --win-units $W
done

echo "=== concatenating ==="
python3 - <<'PY'
import csv, glob, os
rows, hdr = [], None
for f in sorted(glob.glob("results/[A-G]_*.csv")):
    with open(f) as fh:
        r = csv.reader(fh)
        try:
            h = next(r)
        except StopIteration:
            continue
        if h[0] != "scs_khz":
            continue
        hdr = hdr or ["set"] + h
        tag = os.path.basename(f)[:-4]
        rows += [[tag] + row for row in r if row]
with open("results/ALL_sr_pucch.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(hdr); w.writerows(rows)
print(f"results/ALL_sr_pucch.csv: {len(rows)} rows")
PY
echo "=== done ==="
