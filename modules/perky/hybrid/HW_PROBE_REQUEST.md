# Hardware request withheld

**INCOMPLETE / BLOCKED. No physical update or test is requested. DO NOT FLASH.**
The original two iterations and one explicitly authorized additional iteration
are exhausted. The third empty-render candidate was bit-exact but worsened
peak timing and was rejected/restored; see ITERATION3.md. A short corrected
model run reached 319.861 us for the complete ISR, 29.611 us above the proposed
80% margin. Zero misses in this short run is not sustained or silicon proof.
The old 370.797 us ISR interpretation is retracted: it was ACK-to-ACK work.

The current MAIN (simulation input only) has SHA256
`46bd31dba62651500de6c672ec0e3e50c38533f8edbe39cd12e200318c93ca2a`.
No matching card/MIDI wrappers were emitted. Old unqualified wrappers are
preserved under `out/perky/hybrid/resume-fixes/before/`; do not use them.
PERKY4S remains unchanged: source `16a8de19a17ee4cba765cbdb30ca051f85af4e23`,
MAIN SHA256 `be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
Its rollback/release evidence is `modules/perky/PERKY4S_RELEASE.md`.

## Future extraction, after local qualification and separate hardware approval

**No CF METER reading, meter effect selection or meter audio decoding is needed.**
The CF-only profiler observes transport RUN and automatically saves a fresh
`PKH2nnnn.PRF` at the card root after STOP, outside the audio callback.
Allow filesystem activity to finish before removing the card. Copy that file
and decode it with the exact source build receipt:

```sh
.venv/bin/python3 tools/perky/read_hybrid_profile.py /path/to/PKH20000.PRF \
  --build out/perky/hybrid/probe/BUILD.json --out /path/to/profile.json
```

The decoder rejects an unrelated source identity, malformed/truncated record,
odd snapshot sequence and wrong timer clock. Files are cumulative snapshots
since boot. A future approved protocol must specify per-row reset/boot and
verify the physical export/read cost; the current path has only emulator and
ABI validation. It is not yet a qualified silicon measurement facility.

Future qualification still requires all seven combinations for >=2 minutes
each and the worst for >=30 minutes, T1/T5 DSP + T2/T6 CF + four stock sampler
tracks, retained busy FX, locks/LFOs/scenes, transitions and lifecycle stress.
Require zero stalls/dropouts/misses and <=290.249433 us worst full service
including probe overhead. Stop at any failure and follow the established
rollback procedure. This describes the deferred contract, not an instruction
to flash or begin testing now. See PHASE2.json and GOAL2_RESUME_HANDOFF.md.
