# DSP-B specialization and paired oscillator experiment — 20 October 2026

**Placement passes the local checks; two unchanged oscillator renderers on B
do not meet the existing conservative source allowance.** This is an opt-in
experiment on `perky-cf-dsp-hybrid`, authorized for this checkout. PERKY4S
remains the physical reference. This experiment produces no flash wrappers.

Source checkpoint: `4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus the
implementation recorded by the source hashes in the local placement report.
The compact [receipt](DSP_B_FEASIBILITY.json) contains hashes and measured
results, without firmware bytes. Full cases/logs remain under
`out/perky/hybrid/dsp-b-feasibility/`.

## Measured placement

The stock ordinary P upload ends at A:`0x1fdf`, B:`0x1d9f`, exclusive.
Those are upload facts, not proof of physical ownership up to `0x2000`.
The experimental installer keeps private appended records on their own
core and unions only physically shared records. Seven negative controls
reject cross-domain records, conflicting shared contents and overlaps.
Equal private addresses on different cores remain independent.

The assembled B allocation is:

| Kernel | Start | Words |
|---|---:|---:|
| Fold 1 | `0x1d9f` | 189 |
| Fold 2 | `0x1e5c` | 262 |
| Complex | `0x1f62` | 106 |
| Experimental upper guard | `0x1ffa` | 6 |

The three kernels use 557 of B's candidate 609 words. The interval
`0x1fcc..0x1ffa` contributes 46 unused words; the original donor allocation
also has four free words. The six-word guard is an experimental allowance,
**not a hardware-qualified guard length**.

A retains its 48-word startup clear helper and resumes stock source
handling. Its 722 oscillator words in private P and 766 core-owned shared
words are released from the executable ledger. Its removed donor bytes may
still contain unreachable old code. The experiment does not use or execute
A's 33-word upper tail.

Shared occupancy is **1,138 / 2,404 words**, including the original six-word
shared guard and a new 57-word B context-exchange helper. This leaves
**1,266 shared words free**. Without that exchange helper the specialization
would leave 1,323. Private donor space free on A is 726 words; adding its
unvalidated upper tail is a separate future decision.

The candidate's preboot loader reads both extended uploads back exactly at
RTOS handoff. All twelve retained FX code/dispatch bytes are preserved in
the uploads. A separate dirty-start port gate exercises each B oscillator
with the retained FX and reads back loaded private/shared P after PLAY.
Stock frame setup legitimately changes four packer-mask literals; the
gate checks their allowed values separately (see
[DSP self modification](../../../docs/firmware/DSP.md)).

These are local upload, execution and scoped ownership observations. Silicon
RAM ownership, prefetch behavior, long runs and contention remain unproved.

## Independent contexts and measured pair cost

The existing renderers use fixed X addresses. The experiment exchanges a
142-word context with a second bank at `X:0x39c1..0x3a4f`, exclusive:

| Context | Words |
|---|---:|
| Persistent synthesis state | 58 |
| RNG limbs | 4 |
| Event/admission/init bookkeeping reservation | 6 |
| Pitch cache | 17 |
| Native stereo PCM FIFO reservation | 40 |
| Native clock/segment bookkeeping reservation | 17 |

The 100-word renderer scratch and two Fold2 temporary words are shared
between sequential invocations. Total private X occupancy becomes
**560 / 616 words**, leaving 56. The bank is initialized by the test
harness; a production second-voice initializer is not installed.

The helper exchanges the contexts before and after the second source call.
It occupies real candidate shared P and its runtime cost is included. The
test dispatcher at `P:0x5000`, record fixtures and channel-capture work are
harness infrastructure outside the candidate's memory ledger. Each call
enters the complete production source seam, including the 48 kHz native
clock, event split and integration gain. Both calls use the admitted position
zero. **This is not production T2 dispatch.**

The fixed corpus contains 108 cases: four requested oscillator pairs × nine
mode pairs × three opposed control rows. Each runs 64 blocks, with all 16
trigger offsets and intervening release blocks: **6,912 paired blocks**.
Another **768 paired transitions / 2,304 blocks** change algorithms, modes
and controls inside a sounding frame, using distinct old/new tuples.
Both PCM channels and all 142 exchanged words match the corresponding
independent single-instance runs exactly. Four dirty-context cases also
match PCM and initialized state; dormant markers, reserved clock words and
unconsumed transient FIFO tails are not required to become zero.

| Fixed pair | Maximum paired modeled cycles | Maximum aligned sum of solo calls |
|---|---:|---:|
| Fold 1 + Fold 2 | 39,661 | 38,114 |
| Fold 1 + Complex | 35,264 | 33,717 |
| Simple + Fold 2 | 36,065 | 34,518 |
| Simple + Complex | 31,668 | 30,121 |

The observed exchange/capture overhead above the aligned solo sums is 1,547
cycles. The transition corpus peaks at 39,195 cycles. Each of the 108 fixed
cases has a maximum above the unchanged **23,040 modeled-cycle source
allowance**. These are executed emulator observations, not historical sums
substituted for paired measurements. The solo sums still include their own
entry harness work; they are not a new lower-bound theorem.

The independent existing sound oracles also pass at the relocated B PCs:
155 raw Complex cases / 2,480 blocks (432 original ARM-capture blocks),
18,432 four-engine native-clock blocks, 12 dirty initializations,
576 rejected-position blocks and 768 interior algorithm transitions.
Clock-converted PCM remains within the existing one-LSB tolerance to its
independent oracle; raw renderer state/PCM/RNG checks retain their original
exactness requirements.

## Decision and falsifiers

**Do not enable a second production oscillator on B from this result.**
The specialization is a useful program-space candidate, but unchanged paired
rendering fails the existing screening allowance. Even the observed worst
Fold 1/Fold 2 solo sum would need roughly 40% reduction to meet it. A
different renderer, measured budget justification or placement must be
demonstrated first. This does not prove physical failure: the model omits
silicon behavior, and its allowance includes a conservative margin/reserve.

The timing decision would be superseded by a correctness-qualified paired
implementation meeting the same allowance across an equal or broader corpus,
or by a separately justified replacement timing contract. The placement
claim would be falsified by private-tail upload/readback drift, unexpected
runtime writes, failed original-author PCM/state checks or physical prefetch
failure. A's unused tail remains a census-only candidate.

The next measured alternative is a selected ColdFire oscillator fallback,
priced with corrected target arithmetic and the complete native-clock
workload before building a cross-core PCM protocol. Restoring Acoustic Hats,
SRAM trials and DSP-A family ports remain subsequent work.

## Reproduction

Use this existing checkout and local toolchains/assets. All commands run
locally. A baseline with the preserved PERKY4S normal image, assembly,
platform files and appended-record ledger is required. The builder refuses
source drift and verifies that its default installer path reproduces that
baseline byte for byte before creating the specialization.

```sh
WORK=out/perky/hybrid/dsp-b-feasibility
mkdir -p "$WORK"
.venv/bin/python3 tools/verify/verify_perky_private_uploads.py
.venv/bin/python3 tools/perky/build_dsp_b_feasibility.py --work "$WORK"
.venv/bin/python3 tools/verify/verify_perky_dsp_b_pair.py --work "$WORK"
.venv/bin/python3 tools/verify/verify_perky_dsp_b_oracles.py --work "$WORK"
.venv/bin/python3 tools/verify/verify_perky_dsp_b_ownership.py \
  --work "$WORK" --project "$OT_PROJECT"
make check REMIX=perky-machine
```

The pair verifier exits successfully when correctness and measurement
completeness pass; read `timing_decision` in `pair-report.json` for the
feasibility outcome. A zero exit code does not mean that two voices fit.

The build-plumbing check for this change used a pre-edit local baseline,
with one job to avoid creating any worktree:

```sh
REFHASH_JOBS=1 scripts/refhash.sh save
# After editing:
REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check
```

All 24 configurations' artifacts and reports match. Re-saving after editing
would invalidate that before/after comparison. The ordinary repository
`make check` is a separate floor for the registered impulse remix; its
unavailable-project skips do not qualify this experimental full-machine
candidate. Candidate-specific evidence is listed above and in the receipt.
