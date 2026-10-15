# Hardware request WITHHELD — Goal 2 incomplete

**Do not flash the recovered PKHYB2P. There is no approved flash hash.**
The model missed its 362.811791 us deadline once in a 4,000-frame diagnostic
(maximum 370.796992 us). Initialization and full-frame hardware profiling
also fail qualification. `PHASE2.md` explains the stopping gate.

Preserved, unqualified evidence only:

| Artifact under `out/perky/hybrid/probe/` | SHA256 — NOT approved for flashing |
|---|---|
| `mainos_PKHYB2P.bin` | `df77a52a56941f1fbb6a97f3cfdc118cf03596b87c22b6389717ee1fe8e6c582` |
| `OCTATRACK_PKHYB2P.bin` | `fa222e0bdb3a54dba617e03902300bda93cece2368a9cc55495d00af60db5f40` |
| `OCTATRACK_OS1.40C_PKHYB2P.syx` | `7beb8da5069a77d85c6a6d10a882ac111bb85fc995014a5c64a9ad1f3bc085f3` |

The current `pk_hybrid_prof_export` RAM symbol and emulator `--mem-dump` are
not a qualified silicon extraction procedure. Do not infer full-frame
headroom from their callback sums. A later probe must establish a real
132 MHz DTIM3 full-frame measurement, wrap handling, coherent export outside
the callback, and measured read/probe overhead. Frozen DSP bytes must remain
identical; the existing CF METER DSP insert cannot simply be added.

Only after local correctness, source reproducibility and timing review pass,
issue a new uniquely identified probe with its exact MAIN/card/MIDI hashes
and an executable hardware extraction procedure. Then request:

- MKII: V1/V1, V1/V2, V2/snare, V1/bass, snare/snare, bass/snare and
  third/third, at least two minutes each; worst combination at least 30 minutes.
- T1/T5 native DSP synths and T2/T6 independent CF synths active together;
  T3/T4/T7/T8 playing samples. Busy retained FX, including Dark on both cores,
  dense six-control locks/retriggers, LFOs/scenes, family/mode changes and
  long decays. Include delayed first trigger and actual Bank/Part changes.
- Profiler-on/off and CF armed/disarmed comparisons, zero stalls/dropouts or
  deadline misses, and measured worst full CF frame service including overhead
  <=290.249433 us (80%). A margin failure requires review; remove no FX.

Rollback evidence remains unchanged:

- PERKY4S MAIN SHA256:
  `be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
- `out/OCTATRACK_PERKY4S.bin` SHA256:
  `bc9367ec56b2f310f733d0808a88e74e44da32b63f9483468af09760f7ac8fa9`.
- Factory `downloads/extracted/OCTATRACK_OS1.40C.syx` SHA256:
  `0a8d2d2b35c2cc78fa338576adc1af0cbc094cef973255103165c73edd87f2b6`.

For a future approved physical run: stop at a stall, dropout or missed deadline;
retain the exact probe hash, profiler output and workload/project settings.
Use the established manual rollback procedure before further experiments.
No automatic flash, boot or update is authorized. Goal 3 remains blocked until
actual MKII results for a qualified exact probe are validated.
