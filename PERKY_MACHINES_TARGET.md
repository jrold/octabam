# Perky Machines — Locked Target Specification

This document is the authoritative target for the Perky Machines work in Octabam.
Intermediate audition/canary builds may intentionally implement only a subset, but they must not be described as the finished Perky Machines implementation unless every requirement below is satisfied.

## Four independent Perky Machines tracks

The target is **four simultaneous, independent PĒRKONS-style synthesis voices** on the Octatrack.

Each Perky Machines track must be able to select **any supported PĒRKONS algorithm**. No final track may be permanently tied to a particular voice family or algorithm.

## SRC page

Each Perky Machines track exposes exactly these six synthesis controls on the Octatrack SRC page:

| SRC encoder | Parameter | P-lockable |
| --- | --- | --- |
| A | Decay | Yes |
| B | Tune | Yes |
| C | Param 1 | Yes |
| D | Param 2 | Yes |
| E | Mode | Yes |
| F | Algo | Yes |

All six parameters must support **independent per-step parameter locks**.

In particular:

- `Mode` must be p-lockable on every trig.
- `Algo` must be p-lockable on every trig.
- Changing `Algo` on a trig must select the requested supported synthesis algorithm for that step, rather than merely changing a display value or taking effect only after a later trigger.
- The four tracks must remain independent: changing any of the six controls on one Perky Machines track must not alter the synthesis state of another track.

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
3. Decay, Tune, Param 1, Param 2, Mode, and Algo are all independently p-lockable per trig.
4. Per-trig Algo and Mode changes reach the correct synthesis engine/state before that trig is rendered.
5. Both stock Octatrack FX slots remain fully functional with the original stock effects available.
6. The implementation passes the project’s local source, emulator, memory-layout, realtime-budget, and firmware packaging gates before physical Octatrack testing.

This specification supersedes fixed-engine four-track audition mappings such as T1=Fold1, T2=Karplus, T5=Fold2, T6=Noise/Tone. Those mappings are useful development canaries only; they are not the final Perky Machines architecture.
