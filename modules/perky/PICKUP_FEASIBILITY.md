# Pickup removal — Phase 2 feasibility audit

Pickup remains fully enabled. This is a read-only census of the user's 1.40C,
not a removal implementation. Reproduce with `tools/perky/audit_pickup.py`;
the generated ledger records the exact input hash. No firmware bytes are saved
in this document or committed by that tool.

The modest candidate savings are **ColdFire storage**. They do not enlarge the
DSP's private P, X or Y, or its shared physical window. No Pickup-specific DSP
allocation was established, so the budget credits **zero DSP words**.
The stock ColdFire source dispatch at `0x400d6434` sends STATIC, FLEX and
Pickup to the same `0x40004008` renderer. Removing that renderer would remove
ordinary sampling; it is excluded from the census.

| Candidate | Half-open ColdFire address range | Bytes | Usability |
|---|---|---:|---|
| Pickup page descriptor | `0x400d362c..0x400d37be` | 402 | One contiguous ROM region, conditional on retiring all descriptor references and defining old-project behavior |
| Pickup membership/cleanup helpers | `0x40097204..0x400972fa` | 246 | Two routines plus alignment; retaining two 2-byte RTS entry stubs leaves 242 bytes in separate extents of 138 and 104 |
| Total identified candidates | two separate regions | 648 gross / 644 after stubs | Not one contiguous allocation; zero bytes currently released |

The helper functions inspect machine id 4 and update the Pickup membership
mask at `0x46c7ff3e`. They are called from the **shared** assignment routine
`0x400972fc` and reset routine `0x40097460`; those callers cannot be harvested.
Replacing them with stubs is a conditional experiment, not a proven safe
removal. Projects containing existing Pickup assignments, transitions out of
Pickup and the membership mask need explicit migration/rejection tests first.

The descriptor is 402 bytes (`E+0x192`), ending at the next descriptor's E.
Its public P pointer is `E+0x38 = 0x400d3664`. Counting to the next public
pointer would incorrectly add 56 bytes of the **LFO** descriptor. Machine
chooser entries, renderer pointers, strings and bitmap pointers have further
callers and stable raw id indices. They are not counted as extra free caves.
In particular, the stock P bitmap is still needed by the PERKY display hook.

| Preserved resource | Quantified footprint | Reclaim credited |
|---|---:|---:|
| Eight general voice records (`0x800049d8`, stride 168) | 1,344 bytes | 0; shared transport/status/AMP ABI |
| Recorder objects 128–135 (`0x100b14f0`, stride 1,096) | 8,768 bytes | 0; track recording and FLEX recorder-buffer playback |
| Eight recorder control records (stride 44) | 352 bytes | 0; shared recorder scheduler |
| Audio arena at `0x40a955e0`, 14,602 × 6,144-byte pages | 89,720,832 bytes | 0; shared samples and dynamic recorders |
| DSP P/X/Y and shared-window allocations | separate DSP address spaces | 0 words identified as safely recoverable |

Dynamic pages are allocated on demand and depend on project recorder settings.
There is no fixed Pickup-only SDRAM pool to add to this table. Turning Pickup
off does not justify reclaiming the eight recorder rows or the audio arena.
The shared recorder writer `0x400068e4`, unpacker `0x400072f2`, EMAC mixer
`0x40007680`, packer `0x40007826`, trigger scheduler and buffer allocator stay.
See [the recorder architecture](../../docs/firmware/RECORDER.md) and
[the measured DRAM placement](../../docs/contributing/PLACEMENT.md).

The identified savings do not address PERKY's DSP P constraint and are small
compared with its existing ColdFire DRAM platform. Pickup removal is therefore
not a useful prerequisite for this release. A separately authorized milestone
could audit all callers and specialize the two helpers, retain raw machine ids,
and define old-project behavior. Its gates must cover Pickup assignment removal
and transitions, project/Part save and reload, recorder trigs, all recording
sources, live sampling, FLEX playback of buffers 128–135, dynamic allocation,
transport/tempo and ordinary machine chooser/labels. Hardware recorder testing
would remain necessary. A full exclusivity proof might find other fragments;
this census does not claim a complete removable Pickup code size.
