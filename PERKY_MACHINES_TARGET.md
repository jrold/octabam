# Perky Machines — Locked Target Specification

This document is the authoritative target for the Perky Machines work in Octabam.
Intermediate audition/canary builds may intentionally implement only a subset, but they must not be described as the finished Perky Machines implementation unless every requirement below is satisfied.

## Development and release policy

All Perky Machines work stays on the `perky-machines` branch.

GitHub-hosted CI pipelines and GitHub Actions are not used for this work. Qualification is run locally with the repository's own tools.

A firmware is not eligible for physical Octatrack testing until both of these gates pass against the exact image being packaged:

1. the executable PCM/control qualification compares the production PĒRKONS renderers against the pinned PerkyBits/native reference and passes bit-exact PCM/state/control tests; and
2. the Octabam whole-machine emulator (`tools/emu/ot_emu`) boots the exact built MAIN OS, loads a real staged Octatrack project, runs the real sequencer/trig path, proves PERKY source audio is produced, and proves ordinary stock tracks/sequencer operation continue normally.

Host callback fixtures are useful integration tests, but they do not substitute for the whole-machine emulator gate.

## Four independent Perky Machines tracks

The target is **four simultaneous, independent PĒRKONS-style synthesis voices** on the Octatrack.

Each Perky Machines track must be able to select **any supported PĒRKONS algorithm**. No final track may be permanently tied to a particular voice family or algorithm.

## SRC page

Each Perky Machines track exposes exactly these six synthesis controls on the Octatrack SRC page:

| SRC encoder | Parameter | P-lockable |
| --- | --- | --- |
| A | Tune | Yes |
| B | Decay | Yes |
| C | Algo | Yes |
| D | Param 1 | Yes |
| E | Param 2 | Yes |
| F | Mode | Yes |

All six parameters must support **independent per-step parameter locks**.

In particular:

- `Algo` must be p-lockable on every trig.
- `Mode` must be p-lockable on every trig.
- Changing `Algo` on a trig must select the requested supported synthesis algorithm for that step, rather than merely changing a display value or taking effect only after a later trigger.
- The four tracks must remain independent: changing any of the six controls on one Perky Machines track must not alter the synthesis state of another track.
- The old redundant PERKY algorithm browser is not part of the final UI; Algo selection belongs on SRC encoder C.

## Stock FX requirement

Both original Octatrack FX slots must remain fully functional.

- No stock effect may be removed.
- No stock effect may be replaced by a Perky synthesis engine.
- No stock effect may become unavailable when a Perky Machines track is active.
- A completed implementation must not reserve stock FX program/data memory in a way that prevents the original effects from operating normally.

## Completion criteria

Perky Machines is not considered complete until all of the following are true simultaneously:

1. Four Perky Machines voices can run at once.
2. Each of the four voices can select any supported PĒRKONS algorithm.
3. Tune, Decay, Algo, Param 1, Param 2, and Mode are all independently p-lockable per trig.
4. Per-trig Algo and Mode changes reach the correct synthesis engine/state before that trig is rendered.
5. Both stock Octatrack FX slots remain fully functional with the original stock effects available.
6. Production voice PCM/state/control tests pass against the pinned PerkyBits/native reference.
7. The exact candidate firmware passes the full `ot_emu` project/sequencer/audio user-path gate without breaking stock track rendering or sequencer progress.
8. Local memory-layout, realtime-budget, stock-DSP identity, image-integrity and firmware packaging gates pass.
9. Only after items 1–8 pass is a firmware handed off for physical Octatrack testing.

This specification supersedes fixed-engine four-track audition mappings such as T1=Fold1, T2=Karplus, T5=Fold2, T6=Noise/Tone. Those mappings are useful development canaries only; they are not the final Perky Machines architecture.
