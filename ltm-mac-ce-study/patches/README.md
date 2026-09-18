# nr v5.1 → LTM core changes

`nr-v5.1-ltm.patch` contains the **additive** changes that add a real 6G LTM cell-switch MAC CE
to the CTTC 5G-LENA `nr` module, generated against tag **v5.1** (commit `cedcead`). No existing
`nr` behaviour is modified.

## What it adds (10 files, ~268 lines)

| File | Addition |
|---|---|
| `model/nr-control-messages.{h,cc}` | `LTM_CELL_SWITCH` message type + `NrLtmCellSwitchMessage` (RNTI, target cell, Target Configuration ID, forged flag) |
| `model/nr-gnb-phy.{h,cc}` | `NrGnbPhy::SendLtmCellSwitch()` — gNB emits the MAC CE on the DL control channel |
| `model/nr-ue-phy.{h,cc}` | UE PHY dispatch for `LTM_CELL_SWITCH` + `NrUePhy::InjectForgedLtmCellSwitch()` (the attacker's PHY injection) |
| `model/nr-ue-cphy-sap.h` | `RecvLtmCellSwitch()` PHY→RRC upcall |
| `model/nr-ue-rrc.{h,cc}` | candidate table + `AddLtmCandidate()` (pre-configuration) + `DoRecvLtmCellSwitch()` (activation by Target Configuration ID) + `LtmCellSwitchReceived` trace |
| `examples/CMakeLists.txt` | registers the `ltm-forged-handover` example |

## Apply

```bash
# from ns-3-dev/contrib/nr  (must be at tag v5.1)
git apply ../path/to/nr-v5.1-ltm.patch
# then place the scenario program the CMakeLists entry expects:
cp ../path/to/scenario/ltm-forged-handover.cc examples/
```

The example itself (`ltm-forged-handover.cc`) is provided separately under `scenario/` because
it is a new (untracked) file; the patch only carries the one-line `CMakeLists.txt` registration
for it.
