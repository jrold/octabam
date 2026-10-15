# Hardware request withheld — post-closeout safety assessment

**No hardware update or profiling test is recommended. Do not flash.** Goal 2
remains closed at `bee3830134b2061151a3628f6622347de2916f38`; Goal 3 has not begun.
The current assessment is [SAFETY_QUALIFICATION.md](SAFETY_QUALIFICATION.md), with
exact identities and evidence in its JSON companion. CLOSEOUT.md records the
older image and its historical clock assumptions.

The safety task corrected the nominal CPU basis to 264 MHz and selected the
132 MHz PIT bus input, fixed native control BSS initialization and moved timer
read calibration after stock timer setup. It preserved all DSP/FX bytes and
synthesis algorithms. Current short full-ISR maximum is **323.765152 us**, zero
observed duration misses in 4,000 frames; modeled deadline headroom **39.046640 us**.
It exceeds the unwaived 80% ceiling by **33.515718 us**. No exception is approved.

Packaging, cap and targeted corruption gates now pass. Local PKHYB2P build 11
MAIN/card/MIDI files exist, but **no qualified diagnostic installation set exists**.
Current MAIN SHA256:
`a2d6915bc71a97d63f44e223e558cc4941d52113708f7ba92a57bdd669339b40`.
Current card SHA256:
`10c92102780d8795d5944488b78830f2f35fca51a9f234c67bf23cf74f898a69`.
These hashes identify unqualified artifacts; they are not flash instructions.

Essential stack/nesting bounds, real Bank/Part/machine/project transitions,
UI queue loss/backlog, physical DMA/cache ownership and independent core
completion timing remain open. CF defaults armed; there is no validated
probe-specific automatic abort. A short requested duration cannot guarantee
responsive STOP/export or contain a stall. The next bounded investigation is
stack/nesting qualification, not another synthesis optimization experiment.
Independent safety gates must pass before an explicit user margin decision and
restricted activation/abort/capture protocol can justify installation.

Automatic STOP-to-card export passed again on the current image under the port:
one source-matched 1,864-byte PRF. It can avoid CF METER readings or a DSP insert.
Physical timer read/probe overhead and card export remain unmeasured.

Known working PERKY4S remains unchanged: source
`16a8de19a17ee4cba765cbdb30ca051f85af4e23`, MAIN SHA256
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`;
see [PERKY4S_RELEASE.md](../PERKY4S_RELEASE.md). No rollback or installation
action is requested. No flashing, pushing, new branch/worktree or Goal 3.

BLOCKED BY UNRESOLVED TIMING
