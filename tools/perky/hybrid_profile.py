"""Decode CF-only hybrid profiles; no firmware or emulator is imported."""
import struct

def decode_profiler_dump(raw: bytes) -> dict:
    """Unpack `pk_hybrid_profiler` big-endian struct from ColdFire DRAM."""
    # 36 scalar/array uint32 fields before ring_write_idx, then ring_write_idx + 5*64 uint32s
    # Total uint32s = 49 + 1 + 320 = 370 (1480 bytes)
    if len(raw) % 4: raise ValueError("unaligned profiler dump")
    words = struct.unpack(f">{len(raw)//4}I", raw)
    (
        magic,
        version,
        profiler_enabled,
        cf_armed,
        dtim3_hz,
        read_overhead_ticks,
        frame_count,
        cf_active_frames,
        dsp_active_frames,
        cf_sample_count,
        active_voice_mask,
        active_cf_voices,
        active_dsp_voices,
        ui_tick_count,
        handoff_generation,
        handoff_pending_frames,
        deadline_misses_100pct,
        margin_exceeded_80pct,
        max_full_frame_ticks,
        max_cf_callback_ticks,
        max_cf_control_ticks,
        max_cf_render_ticks,
        max_cf_pack_ticks,
        max_dsp_callback_ticks,
        sum_full_lo,
        sum_full_hi,
        sum_cf_lo,
        sum_cf_hi,
        sum_ctrl_lo,
        sum_ctrl_hi,
        sum_rend_lo,
        sum_rend_hi,
        sum_pack_lo,
        sum_pack_hi,
        sum_dsp_lo,
        sum_dsp_hi,
    ) = words[:36]

    inst_calls = list(words[36:38])
    inst_trigs = list(words[38:40])
    inst_max_ticks = list(words[40:42])
    inst_max_ctrl_ticks = list(words[42:44])
    inst_max_rend_ticks = list(words[44:46])
    inst_max_pack_ticks = list(words[46:48])
    ring_write_idx = words[48]

    if magic != 0x504b4850 or version not in (1, 2):
        raise ValueError("unknown hybrid profiler magic/version")
    extra = words[369:]
    extension = {}
    if version == 2:
        if len(words) != 445 or dtim3_hz != 132000000:
            raise ValueError("invalid v2 profiler size/clock")
        extension = {
            'histogram_ticks_1024': list(extra[:64]),
            'period_min_ticks': extra[64], 'period_max_ticks': extra[65],
            'reset_max_ticks': extra[66], 'reset_count': extra[67],
            'readiness_faults': extra[68], 'snapshot_retries': extra[69],
            'wait_loop_max_ticks': list(extra[70:72]),
            'wait_loop_sum_ticks': [(extra[74+i] << 32) | extra[72+i] for i in range(2)],
            'full_frame_window': True,
        }

    def u64(lo, hi):
        return (hi << 32) | lo

    sum_full = u64(sum_full_lo, sum_full_hi)
    sum_cf = u64(sum_cf_lo, sum_cf_hi)
    sum_ctrl = u64(sum_ctrl_lo, sum_ctrl_hi)
    sum_rend = u64(sum_rend_lo, sum_rend_hi)
    sum_pack = u64(sum_pack_lo, sum_pack_hi)
    sum_dsp = u64(sum_dsp_lo, sum_dsp_hi)

    n = max(1, frame_count)
    t_to_us = 1e6 / float(dtim3_hz if dtim3_hz else 132_000_000)

    return {
        "extension": extension,
        "magic": hex(magic),
        "version": version,
        "profiler_enabled": bool(profiler_enabled),
        "cf_armed": bool(cf_armed),
        "dtim3_hz": dtim3_hz,
        "read_overhead_ticks": read_overhead_ticks,
        "read_overhead_us": round(read_overhead_ticks * t_to_us, 4),
        "frame_count": frame_count,
        "cf_active_frames": cf_active_frames,
        "dsp_active_frames": dsp_active_frames,
        "cf_sample_count": cf_sample_count,
        "active_voice_mask": hex(active_voice_mask),
        "active_cf_voices": active_cf_voices,
        "active_dsp_voices": active_dsp_voices,
        "ui_tick_count": ui_tick_count,
        "handoff_generation": handoff_generation,
        "deadline_misses_100pct": deadline_misses_100pct,
        "margin_exceeded_80pct": margin_exceeded_80pct,
        "dtim3_ticks": {
            "max_perky_service_ticks": max_full_frame_ticks,
            "max_cf_callback_ticks": max_cf_callback_ticks,
            "max_cf_control_ticks": max_cf_control_ticks,
            "max_cf_render_ticks": max_cf_render_ticks,
            "max_cf_pack_ticks": max_cf_pack_ticks,
            "max_dsp_callback_ticks": max_dsp_callback_ticks,
            "mean_perky_service_ticks": round(sum_full / n, 2),
            "mean_cf_callback_ticks": round(sum_cf / n, 2),
            "mean_cf_control_ticks": round(sum_ctrl / n, 2),
            "mean_cf_render_ticks": round(sum_rend / n, 2),
            "mean_cf_pack_ticks": round(sum_pack / n, 2),
            "mean_dsp_callback_ticks": round(sum_dsp / n, 2),
            "inst_calls": inst_calls,
            "inst_trigs": inst_trigs,
            "inst_max_ticks": inst_max_ticks,
            "inst_max_control_ticks": inst_max_ctrl_ticks,
            "inst_max_render_ticks": inst_max_rend_ticks,
            "inst_max_pack_ticks": inst_max_pack_ticks,
            "ring_write_idx": ring_write_idx,
        },
        "dtim3_us": {
            "max_full_frame_us": round(max_full_frame_ticks * t_to_us, 3),
            "max_perky_service_us": round(max_full_frame_ticks * t_to_us, 3),
            "max_cf_callback_us": round(max_cf_callback_ticks * t_to_us, 3),
            "max_cf_control_us": round(max_cf_control_ticks * t_to_us, 3),
            "max_cf_render_us": round(max_cf_render_ticks * t_to_us, 3),
            "max_cf_pack_us": round(max_cf_pack_ticks * t_to_us, 3),
            "max_dsp_callback_us": round(max_dsp_callback_ticks * t_to_us, 3),
            "mean_perky_service_us": round((sum_full / n) * t_to_us, 3),
            "mean_cf_callback_us": round((sum_cf / n) * t_to_us, 3),
            "mean_cf_control_us": round((sum_ctrl / n) * t_to_us, 3),
            "mean_cf_render_us": round((sum_rend / n) * t_to_us, 3),
            "mean_cf_pack_us": round((sum_pack / n) * t_to_us, 3),
            "mean_dsp_callback_us": round((sum_dsp / n) * t_to_us, 3),
            "inst_max_us": [round(x * t_to_us, 3) for x in inst_max_ticks],
            "inst_max_control_us": [round(x * t_to_us, 3) for x in inst_max_ctrl_ticks],
            "inst_max_render_us": [round(x * t_to_us, 3) for x in inst_max_rend_ticks],
            "inst_max_pack_us": [round(x * t_to_us, 3) for x in inst_max_pack_ticks],
        },
    }
