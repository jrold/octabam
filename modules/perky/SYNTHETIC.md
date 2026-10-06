# PERKY synthetic development fixtures

`tools/perky/fabricate_noise_tone_fixtures.py` creates deterministic fixtures
that have the same geometry and record shape required by the Noise/Tone port.
They exist so renderer, storage and control-analysis work can continue without
checking PĒRKONS firmware data into this repository.

They are **not measurements of a PĒRKONS HD-01** and must never be used as a
claim about its actual tables or panel-control curves.

The fabricated table set contains:

- two 2,048-entry little-endian u16 envelope curves;
- four 256-entry little-endian s16 wave tables;
- a 0x120-byte prepared-state-shaped blob carrying four synthetic wave
  addresses at the offsets used by the validated native Noise/Tone renderer.

The fabricated control capture uses the real probe's JSONL record schema and
is explicitly marked `synthetic: true`. It exercises:

- all four control ownership paths;
- 17 update/smoothing snapshots per anchor;
- velocity and note trigger deltas;
- pairwise records for the analyzer's interaction path.

The values are deterministic stand-ins, not the original firmware's `update()`
law.

`tools/verify/verify_perky_synthetic_fixtures.py` regenerates everything into a
temporary directory and refuses drift in geometry, control ownership or the
current exact memory plan.

Current synthetic memory canary under the <=15-add envelope decode policy:

- live voice state + shared RNG: 168 private X words per core;
- four densely packed wave tables: 683 private Y words;
- envelope 1: 646 private Y words;
- envelope 2: 646 private Y words;
- exact table total: 1,975 private Y words;
- measured private-Y budget used by the planner: 2,139 words;
- synthetic margin: 164 words.

Those numbers prove the **layout strategy** can work for smoothly varying
curves. They do not prove that the real PĒRKONS envelope tables have the same
compressibility; the real extractor/analyzer remains the final gate for that.
