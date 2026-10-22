"""placement_prepare and placement_segment fast paths in assembly, seams intact.

The frozen full-map oracle steps at the entry of placement_prepare and at the
entry and return of placement_segment (docs/contributing/TRAPS.md
#trap-observer-seams). Both symbols become assembly (modules/perky/cf_placement.s)
with the same arguments. The common cases run there: the unchanged-control
prepare (still calling placement_production_event, also a witness seam), and
a non-empty segment with tracing off, outside Acoustic Hats, that calls the
Wavetable, Slap or Noise/Tone renderer directly. Everything else jumps, with
the stack untouched, to the original C: placement_prepare_slow (made global)
and placement_segment_c (the renamed original segment).

The placement unit exports its struct layout as absolute symbols, and the
engine's tracks and assets pointer as addresses, so the assembly never
hard-codes an offset.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = (('pkplacementasm', ROOT / 'modules/perky/cf_placement.s'),)

LAYOUT = r'''
/* PKFM28: layout for modules/perky/cf_placement.s, exported as absolute symbols. */
#define PK_EXPORT(name,value) ".globl " #name "\n.set " #name ", %c" #value "\n"
__attribute__((used)) static void placement_export_layout(void)
{
    __asm__ volatile(
        ".globl placement_engine_tracks\n.set placement_engine_tracks, placement_engine+%c0\n"
        ".globl placement_engine_assets\n.set placement_engine_assets, placement_engine+%c1\n"
        PK_EXPORT(PK_TRACK_BYTES,2)
        PK_EXPORT(PK_TRACK_INITMASK,3) PK_EXPORT(PK_TRACK_ACTIVE_ALGO,4) PK_EXPORT(PK_TRACK_ACTIVE_MODE,5)
        PK_EXPORT(PK_TRACK_RNG_LOW,6) PK_EXPORT(PK_TRACK_RNG_HIGH,7) PK_EXPORT(PK_TRACK_WT,8)
        PK_EXPORT(PK_TRACK_SLAP,9)
        ::"i"(offsetof(pk4_engine,tracks)),"i"(offsetof(pk4_engine,assets)),"i"(sizeof(pk4_track)),
          "i"(offsetof(pk4_track,initialized_mask)),"i"(offsetof(pk4_track,active_algo)),
          "i"(offsetof(pk4_track,active_mode)),"i"(offsetof(pk4_track,rng_low)),"i"(offsetof(pk4_track,rng_high)),
          "i"(offsetof(pk4_track,wt)),"i"(offsetof(pk4_track,slap)));
    __asm__ volatile(
        PK_EXPORT(PK_TRACK_NT_SHARED,0) PK_EXPORT(PK_CTL_FOLD1,1) PK_EXPORT(PK_CTL_FOLD2,2)
        PK_EXPORT(PK_CTL_KARPLUS,3) PK_EXPORT(PK_CTL_NT_SHARED,4) PK_EXPORT(PK_CTL_RES_SNARE,5)
        PK_EXPORT(PK_CTL_NH,6) PK_EXPORT(PK_CTL_SD,7) PK_EXPORT(PK_CTL_CD,8) PK_EXPORT(PK_CTL_SLAP,9)
        ::"i"(offsetof(pk4_track,nt_shared)),"i"(offsetof(pk4_track,fold1_ctl)),"i"(offsetof(pk4_track,fold2_ctl)),
          "i"(offsetof(pk4_track,karplus_ctl)),"i"(offsetof(pk4_track,nt_shared_ctl)),
          "i"(offsetof(pk4_track,res_snare_ctl)),"i"(offsetof(pk4_track,nh_ctl)),"i"(offsetof(pk4_track,sd_ctl)),
          "i"(offsetof(pk4_track,cd_ctl)),"i"(offsetof(pk4_track,slap_ctl)));
    __asm__ volatile(
        PK_EXPORT(PK_CTL_WT,0) PK_EXPORT(PK_CTL_NT_M1,1) PK_EXPORT(PK_CONTROL_VALID,2)
        PK_EXPORT(PK_CONTROL_LAST_MODE,3) PK_EXPORT(PK_CONTROL_LAST_RAW,4) PK_EXPORT(PK_CLOCK_BYTES,5)
        PK_EXPORT(PK_CLOCK_PHASE,6) PK_EXPORT(PK_CLOCK_HAVE,7) PK_EXPORT(PK_CLOCK_CARRY,8)
        PK_EXPORT(PK_ASSETS_PITCH,9)
        ::"i"(offsetof(pk4_track,wt_ctl)),"i"(offsetof(pk4_track,nt_m1_ctl)),"i"(offsetof(pk4_control,valid)),
          "i"(offsetof(pk4_control,last_mode)),"i"(offsetof(pk4_control,last_raw)),"i"(sizeof(pk_cf_native_clock)),
          "i"(offsetof(pk_cf_native_clock,phase)),"i"(offsetof(pk_cf_native_clock,have)),
          "i"(offsetof(pk_cf_native_clock,carry)),"i"(offsetof(pk4_assets,pitch)));
    __asm__ volatile(
        PK_EXPORT(PK_ASSETS_ENV1,0) PK_EXPORT(PK_ASSETS_ENV2,1) PK_EXPORT(PK_ASSETS_WAVES,2)
        PK_EXPORT(PK_WAVE_BYTES,3) PK_EXPORT(PK_ASSETS_WT_BASE,4) PK_EXPORT(PK_ASSETS_WT_BANK,5)
        PK_EXPORT(PK_ALGO_NT,6) PK_EXPORT(PK_ALGO_SLAP,7) PK_EXPORT(PK_ALGO_WT,8) PK_EXPORT(PK_TRACK_COUNT_X,9)
        ::"i"(offsetof(pk4_assets,envelope1)),"i"(offsetof(pk4_assets,envelope2)),"i"(offsetof(pk4_assets,waves)),
          "i"(sizeof(placement_assets.waves[0])),"i"(offsetof(pk4_assets,wt_base)),"i"(offsetof(pk4_assets,wt_bank)),
          "i"(PK4_ALGO_NOISE_TONE),"i"(PK4_ALGO_SLAP),"i"(PK4_ALGO_WAVETABLE),"i"(PK4_TRACK_COUNT));
}
'''


def once(text, old, new):
    assert text.count(old) == 1, ('placement assembly transform anchor changed', old[:80])
    return text.replace(old, new, 1)


def transform(work, source_path):
    text = Path(source_path).read_text()
    text = once(text, 'static int __attribute__((noinline)) placement_prepare_slow(unsigned tr,const uint32_t *input,int trig)\n',
                'int __attribute__((noinline)) placement_prepare_slow(unsigned tr,const uint32_t *input,int trig);\n'
                'int __attribute__((noinline)) placement_prepare_slow(unsigned tr,const uint32_t *input,int trig)\n')
    text = once(text, 'int __attribute__((noinline)) placement_prepare(unsigned tr,const uint32_t *input,int trig)\n{',
                '/* PKFM28: the exported placement_prepare is assembly (cf_placement.s); this\n'
                ' * original stays only as a reference body. */\n'
                'int placement_prepare(unsigned tr,const uint32_t *input,int trig);\n'
                'int __attribute__((noinline)) placement_prepare_c(unsigned tr,const uint32_t *input,int trig);\n'
                'int __attribute__((noinline)) placement_prepare_c(unsigned tr,const uint32_t *input,int trig)\n{')
    text = once(text, 'int placement_segment(unsigned tr,uint32_t start,uint32_t end,unsigned trace_half)\n{',
                '/* PKFM28: the exported placement_segment is assembly (cf_placement.s), which\n'
                ' * jumps here for every case its fast path does not cover. */\n'
                'int placement_segment(unsigned tr,uint32_t start,uint32_t end,unsigned trace_half);\n'
                'int placement_segment_c(unsigned tr,uint32_t start,uint32_t end,unsigned trace_half);\n'
                'int placement_segment_c(unsigned tr,uint32_t start,uint32_t end,unsigned trace_half)\n{')
    text = text.rstrip('\n') + '\n' + LAYOUT
    target = Path(work) / 'placement-asm-seams.c'
    target.write_text(text)
    return target
