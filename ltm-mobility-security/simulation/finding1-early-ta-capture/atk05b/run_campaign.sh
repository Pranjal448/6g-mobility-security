#!/usr/bin/env bash
# ATK-05b full campaign -- Leg R (receiver re-tracking) and the surrounding sensitivity sweeps.
#
# The 2026-11-11 rebuild measured the decodability boundary with the receiver's FFT window held
# FIXED, and listed closed-loop re-tracking as the single highest-value untested item, noting
# that the fixed-window model is attacker-favourable.  This campaign runs the same srsRAN
# receive chain with a two-pass closed loop, so the boundary is measured against a receiver that
# re-estimates its timing from DM-RS -- which is what a deployed gNB does.
#
# Every set writes one CSV into results/ and is skipped if that CSV already exists.
set -u
cd "$(dirname "$0")"
BIN=./build/atk05b_closedloop
R=results
mkdir -p "$R" logs

TRIALS=${TRIALS:-400}

run () {  # run <name> <args...>
  local name=$1; shift
  if [ -s "$R/$name.csv" ]; then echo "skip  $name"; return; fi
  echo "run   $name"
  $BIN "$@" --csv "$R/$name.csv" > "logs/$name.log" 2>&1 || echo "  FAILED $name"
}

# ---------------------------------------------------------------- gates
# G1  aligned, AWGN-flat, no closed loop: EVM must be small and the estimator must read ~0.
# G2  the TA unit must be dft/128 samples and the ordinary CP exactly 9 TA units, at every mu
#     (printed in each run's header comment; checked by analyse.py).
# G3  the closed loop must not make an ALIGNED slot worse by more than the quantisation step.
echo "=== gates ==="
run GATE_aligned_awgn      --mu 1 --prb 25 --awgn-only --snr 30 --ta-min -1 --ta-max 1 \
                           --trials 200 --closed-loop
run GATE_aligned_tdl       --mu 1 --prb 25 --profile TDL-C --ds-ns 30 --snr 30 \
                           --ta-min -1 --ta-max 1 --trials 200 --closed-loop

# ---------------------------------------------------------------- A: the headline sweep
# Open loop vs closed loop, over the full TA range, at the reference operating point.
for DS in 30 100 300; do
  for PROF in TDL-A TDL-C; do
    run "A_mu1_${PROF}_ds${DS}_cl"   --mu 1 --prb 25 --profile $PROF --ds-ns $DS --snr 30 \
                                     --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop
  done
done

# ---------------------------------------------------------------- B: numerology
for MU in 0 1 2 3; do
  run "B_mu${MU}_cl"  --mu $MU --prb 25 --profile TDL-C --ds-ns 300 --snr 30 \
                      --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop
done

# ---------------------------------------------------------------- C: SNR
for SNR in 0 5 10 15 20 25 30 35; do
  run "C_snr${SNR}_cl" --mu 1 --prb 25 --profile TDL-C --ds-ns 300 --snr $SNR \
                       --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop
done

# ---------------------------------------------------------------- D: modulation order
for MOD in QPSK QAM16 QAM64; do
  run "D_mod${MOD}_cl" --mu 1 --prb 25 --profile TDL-C --ds-ns 300 --snr 30 --mod $MOD \
                       --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop
done

# ---------------------------------------------------------------- E: receiver window offset
# w = 0.5 is srsRAN's deployed uplink value; w = 0 is the textbook placement.
for W in 0.0 0.25 0.5 0.75; do
  run "E_win${W}_cl" --mu 1 --prb 25 --profile TDL-C --ds-ns 300 --snr 30 --win-offset $W \
                     --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop
done

# ---------------------------------------------------------------- F: estimator strategy
for FD in filter mean none; do
  run "F_fd${FD}_cl" --mu 1 --prb 25 --profile TDL-C --ds-ns 300 --snr 30 --fd $FD \
                     --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop
done
run F_td_interpolate_cl --mu 1 --prb 25 --profile TDL-C --ds-ns 300 --snr 30 \
                        --td interpolate --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop

# ---------------------------------------------------------------- G: bandwidth
for PRB in 10 25 50 100; do
  run "G_prb${PRB}_cl" --mu 1 --prb $PRB --profile TDL-C --ds-ns 300 --snr 30 \
                       --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop
done

# ---------------------------------------------------------------- H: the relay as an added path
# The relay contaminates the measurement; here the corrupted TA is already applied and the relay
# is additionally present in the uplink, which is the physically consistent case.
for RP in -6 0 6 20; do
  run "H_relay_p${RP}_cl" --mu 1 --prb 25 --profile TDL-C --ds-ns 300 --snr 30 \
                          --relay --relay-delay-ta 7 --relay-power-db $RP \
                          --ta-min -14 --ta-max 20 --trials "$TRIALS" --closed-loop
done

echo "=== concatenating ==="
python3 - <<'PY'
import csv, glob, os
rows, hdr = [], None
for f in sorted(glob.glob("results/*.csv")):
    tag = os.path.basename(f)[:-4]
    if tag == "ALL_atk05b":
        continue
    with open(f) as fh:
        body = [l for l in fh if not l.startswith("#")]
    if not body:
        continue
    r = csv.reader(body)
    h = next(r)
    hdr = hdr or ["set"] + h
    for row in r:
        if row:
            rows.append([tag] + row)
with open("results/ALL_atk05b.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(hdr)
    w.writerows(rows)
print(f"results/ALL_atk05b.csv: {len(rows)} rows")
PY
echo "=== done ==="
