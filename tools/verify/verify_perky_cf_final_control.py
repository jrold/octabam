#!/usr/bin/env python3
"""Source gate for the locked final ColdFire Perky Machines control path."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT / "modules/perky/control_cf_final.c").read_text()

required = (
    '"DECAY", "TUNE", "PAR1", "PAR2", "MODE", "ALGO"',
    'put32(desc + 0x1c6, 0x00111111u)',
    'PK_FINAL_ALGO_COUNT 4u',
    '#include "cf_perky4.h"',
    'pk4_process_segment(',
    'pk4_encode_stock_segment(',
    'event_boundary = end == PK_FINAL_BLOCK_SAMPLES',
    'event_boundary ? src : (const uint8_t *)0',
    'pk_asset_pitch',
    'pk_asset_m1_wave',
    'case 0u: return 0;',
    'case 1u: return 1;',
    'case 4u: return 2;',
    'case 5u: return 3;',
    '"001 FOLD 1", "002 FOLD 2", "003 KARPLUS", "004 NOISE/TONE"',
)
for needle in required:
    if needle not in s:
        raise AssertionError(f"missing final-control contract: {needle}")

for bad in (
    '0x504b0000u', '0x59310000u', 'probe_glue', 'synthetic_control_map',
    'cf_machine_bridge.h', 'cf_voice_runtime', 'pk_cf_asset_',
):
    if bad in s:
        raise AssertionError(f"legacy/nonfinal transport leaked into final control: {bad}")

if 'for (unsigned i = 0; i < 6u; ++i)' not in s or 'src[i] = (uint8_t)(fp[i] >> 8)' not in s:
    raise AssertionError('final event segment does not consume first-page A..F staging')

print(
    'PERKY final CF control: PASS '
    '(SRC A-F locked; four tracks; four Algos; split-event p-lock staging; '
    'cf_perky4 -> stock source record; no DSP synth transport)'
)
