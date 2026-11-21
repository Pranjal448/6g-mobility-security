# atk16c_statemachine

End-to-end simulation of TS 38.321 clause 5.4.4 as an executable state machine, closing
the gap between "the SR is undetectable" (atk16b_sr, real PHY-layer simulation) and
"therefore the UE deadlocks" (previously established only by reading the clause text).

`deadlock_sim.py` implements the literal clause logic (SR_COUNTER, sr-ProhibitTimer
retry loop, the depth-5> unconditional teardown, the depth-6> guarded recovery) and
drives it with the measured p_sr values from `../atk16b_sr/results/ALL_sr_pucch.csv`
(no fabricated or hand-tuned probabilities).

Includes a negative control: the exact same bad channel, run through the exact same
code, in a legacy/non-LTM context where the recovery guard is open. Result: 0 deadlocks
out of 200,000 trials even at p_sr=0, which is strictly worse than any measured attack
case. This is what demonstrates the deadlock is a consequence of the RACH-less LTM
guard condition, not an artefact of how the state machine is coded.

Run: `python3 deadlock_sim.py` (stdlib only, no dependencies). Output: `results/summary.csv`.
