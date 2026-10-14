# PERKY4S — guarded shared-program placement

PERKY4S preserves PERKY4R's direct-AU-proven Complex TUNE, modulation-frequency
and sustain repairs. It fixes the unsafe four-engine placement policy exposed
by the physical first-trigger sequencer stall. No renderer/control instruction,
stock effect, startup clear, voice admission, synthesis clock or source gain changes.

PERKY4R placed T1's frame return at P:0x3fffe, next to the mapped shared-memory
boundary. The instruction-executing emulator does not model speculative program
fetches beyond that boundary. Removing the new dispatch instructions (P4RNDISP)
still stalled hardware; retaining the R ColdFire runtime with PERKY4 DSP
(P4ROLDDSP) worked. The six-word guard build (P4RPG6) then worked on T1 and T5,
all algorithms, with Dark Reverb used on both, according to the user.

These observations isolate a DSP placement/integration regression and support
the guarded build. The precise prefetch mechanism and minimum safe margin are
inferred: several shards move when the deterministic packer enforces the guard.
Six words are a conservative reservation, not a measured silicon fetch depth.
See [the investigation](PERKY4R_RUNTIME_REGRESSION.md) for the controlled images.

The normal production builder reproduces the hardware-tested P4RPG6 MAIN OS
byte for byte: SHA256
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
PERKY4S has its own updater identifier; P4RPG6, PERKY4R and PERKY4 remain frozen.

The exact P ledger is 770/774 private words per core (four free), and 2398
shared code words plus six explicitly uploaded NOP guard words, 2404/2404
physical shared words (zero free). Both uploads carry the same union. Full
physical startup-clear spans remain unchanged. The development cycle ceiling
remains 23040 modeled cycles. Physical arbitration timing is not modeled.

## Local release procedure

Use the user's original project read-only. Preserve frozen input directories at
`out/frozen/PERKY4` and `out/frozen/PERKY4R`, including their original receipts.
The usual local assets and isolated port/host dependencies are required.

```sh
export OT_PROJECT='/Users/jrold/Documents/EZBot templates/Hyper FX 1.0.6 Template by EZBOT/Hyper FX 1FF 1.0.6'
.venv/bin/python3 tools/perky/build_four_machine.py --qualify-only
# Commit the qualified sources before packaging. Use the qualified local EFT.
OCTABAM_NO_CACHE=1 PERKY_EFT="$PWD/out/eft-qualified/elektron-firmware-tool" .venv/bin/python3 tools/perky/build_four_machine.py --package-qualified
.venv/bin/python3 tools/verify/verify_perky_four_provenance.py --report out/perky/four/PERKY4S_RELEASE.json
```

The release JSON records every command, log hash, exact AU/component version,
source and input hashes, memory ledger, component results, and committed rebuild.
The permanent guard gate rejects preserved unsafe R placement; the old AU,
PCM/state, controls, startup, FX, sequencer, boot and wrapper gates remain.
Additional actual-image source comparisons cover all four engines on both cores,
and a dry delayed-first-trigger replay covers cold activation.

## Physical confirmation

The reported P4RPG6 audio/playback cases have passed. Test duration and exhaustive
transition/modulation coverage were not specified. This is separate from local
executable qualification and direct installed-AU comparisons.

Keep PERKY4 as rollback. After installing PERKY4S, use a blank project and trigger
T1 and T5 separately, then together. Cycle all four algorithms and three modes;
exercise ALGO locks, retriggers, LFOs/scenes and Dark Reverb on both voices over
several full 64-step cycles. Compare Complex against the AU using the captured
settings in [the AU repair procedure](PERKY4R_AU_REPAIR.md). Record any stall,
its trigger, and whether the screen/encoders still respond. Do not overwrite
the original project fixture.
