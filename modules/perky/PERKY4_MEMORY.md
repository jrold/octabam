# PERKY4 physical memory and modeled timing

> **HISTORICAL CHECKPOINT — not the current PERKY build.** The data and
> procedures below document their original experiment and have been retained
> unchanged for provenance. **PERKY4S** is the current working MKII firmware:
> two DSP voices (T1/T5), Fold1/Fold2/Simple/Complex, 12 retained stock FX.
> The current status and memory ledger are in
> [PERKY4S](PERKY4S_RELEASE.md). **Do not flash or continue this older
> experiment simply because it says "read first," "current," or "next step."**


The executable ledger is `out/perky/four/memory.json`, derived from final
assembled shards, their physical union, upload tables and guarded stock ranges.
`perky_four_memory.py` supplements the build ledger with exact occupancy and
free extents. Addresses below are half-open; counts are **24-bit DSP words**,
not ColdFire bytes. Each core has separate private P/X/Y. P/X/Y addresses in
`0x30000..0x40000` alias one physical shared window; common code is counted
once and core-owned code copies separately. Gaps are not a contiguous heap.

| Resource | PERKY3R | PERKY4 | Remaining |
|---|---:|---:|---:|
| Core A private P / safe capacity 774 | 704 | 759 | 15 in two extents |
| Core B private P / safe capacity 774 | 704 | 759 | 15 in two extents |
| Physical shared P / safe capacity 2,404 | 2,113 | 2,379 | 25 in five extents |
| Reachable P per core, including startup | 2,169 | 2,380 | Includes common shared helpers; not physical total |
| Low-Y upload from `0x7a5` | 2,093 | 2,093 | 46 trailing reserved free + 2 internal padding |
| Claimed private-X window `0x3800..0x3a68` | 418 | 418 | 198 in four extents |

The fourth wave occupies dormant state overlays, so identical X reservation
counts do not imply those overlays remain available for voices. The explicit
DSP guard admits only core position zero; T1/B and T5/A are the only PERKY
tracks. No additional voices fit by using this wave region as state.

Private-P free extents are A `0x1215..0x1222` (13), `0x1b56..0x1b58` (2);
B `0xfd5..0xfe2` (13), `0x1916..0x1918` (2). Startup clear costs 48 private-P
words per core and preserves safe shared tails while matching stock final
registers. Shared-P free extents are `0x33ffe..0x34000` (2),
`0x37eff..0x37f00` (1), `0x37ffd..0x38000` (3),
`0x3bff5..0x3c000` (11), `0x3fff8..0x40000` (8).
Safe-tail capacities remain 605/349/240/605/605; the mailbox
`0x37f00..0x37f10` is excluded. The JSON lists every shard and its address.

| Private X, identical layout on both cores | Words | Role |
|---|---:|---|
| `0x3800..0x383a` | 58 | Persistent common voice overlay; Complex needs 42 |
| `0x383a..0x38e6` | 172 | Fourth-wave unsigned int16 samples |
| `0x38e6..0x38e8` | 2 | Uploaded padding, protected reservation |
| `0x38e8..0x38ec` | 4 | Two reference uint32 RNG states |
| `0x38ec..0x38f2` | 6 | Admission/event staging and initialization markers |
| `0x3900..0x3964` | 100 | Sparse renderer scratch and cached base pitch |
| `0x3964..0x3975` | 17 | Control-rate pitch cache |
| `0x3975..0x3977` | 2 | Fold2 pitch temporaries |
| `0x3980..0x39a8` | 40 | Native-rate PCM FIFO |
| `0x39b0..0x39c1` | 17 | Native clock state |

X free extents: `0x38f2..0x3900` (14), `0x3977..0x3980` (9),
`0x39a8..0x39b0` (8), `0x39c1..0x3a68` (167). All scratch is core-private;
there is no shared cross-core RNG or voice state. The voice initializer clears
58 words, not the asset region; uploaded assets are independently verified.

| Low Y, identical layout on both cores | Words |
|---|---:|
| `0x7a5..0xaa5`: original three waves | 768 |
| `0xaa5..0xea5`: original envelope | 1,024 |
| `0xea5..0xef9`: original fourth-wave signed tail | 84 |
| `0xef9..0xefb`: internal free padding | 2 |
| `0xefb..0xf3e`: original pitch bank | 67 |
| `0xf3e..0xf3f`: alignment | 1 |
| `0xf3f..0xfd2`: native clock coefficient table | 147 |
| `0xfd2..0x1000`: trailing reserved free | 46 |

Stock local-Y FX data `0x1000..0xc000` (45,056/core) is protected. The four
stock shared FX buffer regions start at `0x30000`, `0x34000`, `0x38000`,
`0x3c000`, each length `0x3da3`; only their already-safe tails contain code.
Stock staging `0x30000..0x30048`, mailbox and other stock upload words remain
reserved. Retained stock P code and dispatch entries are checked byte for byte
against the user's image and executed with dirty RAM. All twelve retained
FX remain: Filter, Spatializer, Equalizer, DJ EQ, Phaser, Flanger, Chorus,
Comb, Delay, Spring, Dark and Lo-Fi. Plate/Compressor are the existing donors.

| Integrated native-clock test, worst modeled cycles | PERKY3R | PERKY4 |
|---|---:|---:|
| Fold Drum 1 | 15,975 | 16,257 |
| Fold Drum 2 | 21,398 | 21,983 |
| Simple Drum | 12,559 | 12,904 |
| Complex Drum | absent | 18,205 |
| Active interior engine transition | 21,534 | 22,119 |
| Unchanged development ceiling | 23,040 | 23,040 |

Raw Complex's independent seam reports 16,100 modeled cycles, including base
cache preparation and the test RNG dump; it is not the complete source price.
The earlier standalone 33,007 figure includes different infrastructure and
placement. The new complete-path numbers include the 48/44.1k relationship,
trim and continuation. Final per-core reports accompany the release. These
are emulator cycle-model prices, not measured hardware bus/fetch timing.

The ColdFire linked runtime, BSS and loader staging are separate byte-addressed
DRAM allocations, recorded in the final `platform/layout.json`; the UI adds
48 bytes of event/bank/Part latches and two guarded ROM detours. The final
linked runtime is 17,124 bytes, BSS 496 bytes and packed loader staging
5,656 bytes. The protected DRAM reservation has 10,463,176 bytes remaining
after staging; that is ColdFire storage, not DSP P/X/Y. The ledger also
lists every original static upload extent and every retained FX P extent.
No ColdFire
storage is credited to the DSP budget. Pickup removal's conditional ColdFire
census is documented separately and no resources are released in this image.
