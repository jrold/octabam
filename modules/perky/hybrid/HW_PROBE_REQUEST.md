# Goal 2 hardware request — WITHHELD / CLOSED UNQUALIFIED

No physical update or test is requested. **Do not flash.** No current qualified
card/MIDI/ELUP set exists. Goal 2 performance experiments are finished and the
proposed 20% timing margin is not waived. See CLOSEOUT.md and CLOSEOUT.json.

The retained 4,000-frame local-model maximum is 319.860902 us against 362.811791 us,
with zero observed ISR-duration misses, but this is not physical safety proof.
It remains 29.611469 us above the proposed engineering ceiling. Independently,
full lifecycle/BSS, stack/nesting/backlog, sustained mixed-load, per-effect active
processing, per-core completion and exact current package/cap/corruption gates
are not complete. The documented 264 MHz CPU basis versus modeled 266 MHz also
needs reconciliation. Short duration does not avoid the first-frame maximum,
and this image defaults CF armed with no probe-specific automatic abort.

A restricted timing probe could in principle answer unknown hardware timing,
but **this existing candidate is not justified for installation now**. Independent
boot/memory/lifecycle and package safety plus trustworthy timing/capture/stop
scope must be closed, with known rollback and a separately approved bounded
activation/failure protocol and explicit margin review. No such probe is created
or approved by this assessment. The recommendation is targeted non-optimization
investigation of these qualification blockers, not flashing or more tuning.

Automatic UI STOP-to-card `PKH2nnnn.PRF` export and the source-matched decoder
are locally implemented/tested. A future separately qualified measurement path
can use those files without CF METER readings or a new DSP insert. Hybrid silicon
read cost and card export remain unverified; no new physical procedure is issued.

Simulation-only MAIN SHA256:
`46bd31dba62651500de6c672ec0e3e50c38533f8edbe39cd12e200318c93ca2a`.
This is not a qualified flash identity. Old archived wrappers in
`out/perky/hybrid/resume-fixes/before/` belong to an earlier unqualified build.
The rejected iteration 3 image is historical evidence only and was restored away.

Preserved PERKY4S release evidence: modules/perky/PERKY4S_RELEASE.md,
source 16a8de19a17ee4cba765cbdb30ca051f85af4e23, MAIN SHA256
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
No rollback/installation action is being requested. Goal 2 ends here; no Goal 3.
