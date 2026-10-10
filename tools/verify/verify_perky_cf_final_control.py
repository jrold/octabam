#!/usr/bin/env python3
"""Source gate for the locked final ColdFire Perky Machines control path."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT / "modules/perky/control_cf_final.c").read_text()

required = (
    '"TUNE", "DECAY", "ALGO", "PRM1", "PRM2", "MODE"',
    'put32(desc + 0x1c6, 0x00111111u)',
    'PK_FINAL_ALGO_COUNT 6u',
    '#include "cf_perky4.h"',
    'pk4_process_segment(',
    'pk4_encode_stock_segment(',
    'event_boundary = end == PK_FINAL_BLOCK_SAMPLES',
    'event_boundary ? engine_src : (const uint8_t *)0',
    'engine_src[0] = src[PK_FINAL_DECAY]',
    'engine_src[1] = src[PK_FINAL_TUNE]',
    'engine_src[4] = src[PK_FINAL_MODE]',
    'engine_src[5] = src[PK_FINAL_ALGO]',
    'pk_final_trigger_latch[voice] = 1u',
    'trig = event_boundary && pk_final_trigger_latch[voice]',
    'PK_FINAL_SLOT_BASE 0x80001c90u',
    'PK_FINAL_SLOT_BYTES 336u',
    'PK_FINAL_PING_BYTES 0xa80u',
    'pk_final_fixed_slot(unsigned track, unsigned ping)',
    'PK_FINAL_SLOT_BASE + (ping & 1u) * PK_FINAL_PING_BYTES',
    '+ PK_FINAL_SLOT_BYTES * track',
    'pk_final_frame_pcm[4][PK_FINAL_BLOCK_SAMPLES]',
    'pk_final_frame_pcm[voice][start + i] = pcm[i]',
    'cursor_longs = 4u + 2u * count',
    'cursor[i] = 0u',
    'record = pk_final_fixed_slot(track, ping)',
    'record[pre_longs + i] = encoded[i]',
    'pre_longs + post_longs != 40u',
    'pk_asset_pitch',
    'pk_asset_m1_wave',
    'case 0u: return 0;',
    'case 1u: return 1;',
    'case 4u: return 2;',
    'case 5u: return 3;',
    'PK_FINAL_RUNTIME_COLD 0x504b434fu',
    'PK_FINAL_RUNTIME_READY 0x504b5244u',
    'pk_final_runtime_cookie != PK_FINAL_RUNTIME_READY',
    'pk_final_runtime_cookie = PK_FINAL_RUNTIME_READY',
    'old PERKY four-item',
)
for needle in required:
    if needle not in s:
        raise AssertionError(f"missing final-control contract: {needle}")

for bad in (
    '0x504b0000u', '0x59310000u', 'probe_glue', 'synthetic_control_map',
    'cf_machine_bridge.h', 'cf_voice_runtime', 'pk_cf_asset_',
    '"001 FOLD 1"', '"002 FOLD 2"', '"003 KARPLUS"', '"004 NOISE/TONE"',
):
    if bad in s:
        raise AssertionError(f"legacy/nonfinal transport or engine browser leaked into final control: {bad}")

if 'for (unsigned i = 0; i < 6u; ++i)' not in s or 'src[i] = (uint8_t)(fp[i] >> 8)' not in s:
    raise AssertionError('final event segment does not consume first-page A..F staging')

# A regression to the old broken integration wrote the encoded PCM payload to
# the moving source-builder cursor itself. The measured stock path uses that
# cursor only to reserve span and commits the completed track record at the
# fixed per-track/ping DMA slot. Reject direct encoded-payload cursor writes.
if 'cursor[i] = encoded[i]' in s or 'cursor[i] = record[i]' in s:
    raise AssertionError('encoded PCM leaked back onto moving cursor instead of fixed stock slot')

print(
    'PERKY final CF control: PASS '
    '(SRC A-F=TUNE/DECAY/ALGO/PRM1/PRM2/MODE; four tracks; four Algos; '
    'split-event p-lock staging; trigger latched across callback halves; '
    'moving cursor reservation + measured fixed track-slot PCM commit; '
    'redundant engine browser disabled)'
)
