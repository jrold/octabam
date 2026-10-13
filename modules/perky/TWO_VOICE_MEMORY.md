# PERKY two-voice memory ledger

Current four-engine candidate. Half-open extents; addresses and sizes are DSP words.

A serves T5–T8; B serves T1–T4. Only T5/A and T1/B are admitted PERKY voices.

The aliased shared P/X/Y code is byte-identical on both cores and occupies one physical backing memory. Private code has payload-specific addresses. Shared shards never call private P.

| Code shard | A start | B start | Words |
|---|---:|---:|---:|
| synth_seam_glue.asm | `0x01000` | `0x00dc0` | 386 |
| synthetic_control_map.asm | `0x01182` | `0x00f42` | 106 |
| noise_tone_voice_xstate_glue.asm | `0x3fe7c` | `0x3fe7c` | 86 |
| noise_tone_math.asm | `0x33da3` | `0x33da3` | 299 |
| noise_tone_filter.asm | `0x3bf22` | `0x3bf22` | 133 |
| noise_tone_oscillator_packed.asm | `0x3bda3` | `0x3bda3` | 194 |
| noise_tone_envelope_packed7.asm | `0x37e9a` | `0x37e9a` | 91 |
| noise_tone_envelope.asm | `0x3fda3` | `0x3fda3` | 130 |
| noise_tone_mix.asm | `0x3bfa7` | `0x3bfa7` | 89 |
| simple_drum_voice.asm | `0x3fed2` | `0x3fed2` | 80 |
| simple_drum_envelope.asm | `0x37da3` | `0x37da3` | 247 |
| simple_drum_frequency.asm | `0x3ffb8` | `0x3ffb8` | 31 |
| simple_drum_oscillator.asm | `0x37f10` | `0x37f10` | 237 |
| simple_drum_delta.asm | `0x01aa4` | `0x01864` | 162 |
| pk_multi_noise_init | `0x3ff22` | `0x3ff22` | 78 |
| pk_multi_simple_init | `0x011ec` | `0x00fac` | 54 |
| fold_drum_voice.asm | `0x3be65` | `0x3be65` | 189 |
| fold_drum2_voice.asm | `0x33ece` | `0x33ece` | 262 |
| pk_tone_candidate_voice | `0x33fd4` | `0x33fd4` | 38 |
| pk_multi_fold_init | `0x3ff70` | `0x3ff70` | 72 |
| pk_multi_fold2_init | `0x3fe25` | `0x3fe25` | 87 |
| stock startup clear preserving code tails | `0x01222` | `0x00fe2` | 48 |

P totals per core: **3,051 renderer/seam words + 48 reserved startup words = 3,099**. Private P: 756/774; shared P: 2,343/2,404. **79 words headroom** (18 private, 61 shared). Reserved startup size includes its padding.

| Space / region | Both cores | Ownership / alias |
|---|---|---|
| X `0x3800..0x38ec` | 236 words | Persistent compact voice state, envelope caches, RNG |
| X `0x38ec..0x38f2` | 6 words | Event offset, admission latch and four engine markers |
| X `0x3900..0x3964` | 100 words | Source-render scratch |
| X `0x3964..0x3975` | 17 words | Control-rate pitch cache |
| X `0x38f2..0x3900`, `0x3975..0x3a68` | 257 free words | Measured private-X gap; no new claims |
| Y `0x07a5..0x0f3f` | 1,946 words | Packed static tables; exact upload bytes checked |
| Y `0x0f3f..0x1000` | 193 free words | Below stock FX arena |
| Y `0x1000..0xc000` | 45,056 words | Stock local FX arena, preserved |
| Shared `0x30000..0x3ffff` | P/X/Y aliases across both cores | FX2 buffers, mailbox, and listed code tails |
| Shared `0x37f00..0x37f10` | 16 words | Stock mailbox; excluded from code |

Stock shared FX buffer claims: `[0x30000,0x33da3)`, `[0x34000,0x37da3)`, `[0x38000,0x3bda3)`, `[0x3c000,0x3fda3)`. The tail boundary follows the existing measured maximum stock write offset `0x3da2`; it is also exercised by the new runtime FX gate.

Free P extents, after every shard and startup reservation:

- A: `0x01b46..0x01b58` (18), `0x33ffa..0x34000` (6), `0x37ef5..0x37f00` (11), `0x37ffd..0x38000` (3), `0x3ffd7..0x40000` (41)
- B: `0x01906..0x01918` (18), `0x33ffa..0x34000` (6), `0x37ef5..0x37f00` (11), `0x37ffd..0x38000` (3), `0x3ffd7..0x40000` (41)

Preserved stock FX: **Lo-Fi, Spring Reverb, Dark Reverb, Filter, Spatializer, EQ, DJ EQ, Phaser, Flanger, Chorus, Comb, Delay**. Spring/Dark/Delay retain their stock FX2-only chooser placement. Both choosers omit **Plate Reverb and Compressor**; both sacrificed IDs dispatch to the stock null stub.

Private P uses only Plate/Compressor extents: A `[0x1000,0x1252)`, `[0x1aa4,0x1b58)`; B `[0x0dc0,0x1012)`, `[0x1864,0x1918)`. Every other stock P word and dispatch entry is compared against the user’s stock image. Stock Delay is ColdFire-owned and is kept by the remix.

Stock startup is guarded and replaced only at A `P:0x40..0x4a` and B `P:0x40..0x4b`. Local Y and all stock-owned shared words still clear exactly. B includes the builder’s relocated mailbox geometry (`Y:0x3f00..0xc000`, shared `0x37f00..0x40000`). The existing continuation and mailbox staging remain after the private clear call.

Executable proofs: `verify_perky_p_records.py`, `verify_perky_fragment_clear.py`, `verify_perky_fragmented_image.py`, `verify_perky_fragmented_fx.py`. Generated complete ledger/provenance live under `out/perky/fragmented/`; no firmware words are committed.
