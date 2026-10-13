#!/usr/bin/env python3
"""Compose the three-engine repair profile; never package a flash image.

Historical four-engine builders remain available as differential controls.
Only the Fold renderers' sample/hold RNG is retained from Noise/Tone.
"""
from pathlib import Path
import hashlib, json, re, sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'modules/perky'), str(ROOT/'tools/perky')]
import build_fold_candidate as historical
import fold_drum2_compact as fold2
import fold_drum_compact as fold1
import fold_rng_source
import source_clock
import three_segment_source
HISTORICAL_BUILD = historical.build


def piece(name, body):
    return f'; ===== BEGIN {name} =====\n{body}\n; ===== END {name} =====\n'


FOLD2_ENTRY = '''pks_fold2_entry:
        jsrl pk_multi_fold2_init
        jsrl pk_fold2_apply_controls
        move #>$3900,r5
        move #>$ffffff,m0
        move #>$ffffff,m1
        move #>$ffffff,m2
        move #>$ffffff,m3
        move #>$ffffff,m4
        move #>$ffffff,m5
        move #>$ffffff,m6
        move #$0,r0
        move #>$10,a
        move a1,x:>$38ec
        move x:(r4+$3),a
        and #>$ffff,a
        tst a
        beq p3f2_event_ready
        move x:>$20c,a
        tst a
        blt p3f2_event_ready
        cmp #>$10,a
        bge p3f2_event_ready
        move a1,x:>$38ec
p3f2_event_ready:
        jsrl pk_simple_base
        ; cVoice::update (ARM 0x080247dc..e0) writes pitch[rawPitch]
        ; into oscillator A's increment, even when B is currently primary.
        move x:>$3975,a
        move a1,x:(r6+$4)
        clr a
        move a1,x:(r6+$5)
        move x:>$38ec,a
        cmp #>$10,a
        beq p3f2_full
        tst a
        beq p3f2_retrigger
        move a1,n7
        jsrl pk_fold2_voice
p3f2_retrigger:
        jsrl pk_three_fold2_trigger
        move #>$10,a
        move x:>$38ec,x0
        sub x0,a
        move a1,n7
        jsrl pk_fold2_voice
        bra pks_continue
p3f2_full:
        move #>$10,n7
        jsrl pk_fold2_voice
        bra pks_continue
'''

# Direct translation of ARM 0x08024878, 0x08028774 and 0x08024e0c.
# The executable original-ARM contract gate owns the state differential.
FOLD2_TRIGGER = '''pk_three_fold2_trigger:
        move #>$1,a
        move a1,x:(r6+$a)
        move a1,x:(r6+$11)
        move a1,x:(r6+$15)
        move a1,x:(r6+$1c)
        clr a
        move a1,x:(r6+$1a)
        move a1,x:(r6+$1b)
        move a1,x:(r6+$2b)
        move x:(r6+$32),a
        tst a
        beq p3f2_reset_b
        clr a
        move a1,x:(r6+$2)
        move a1,x:(r6+$3)
        move a1,x:(r6+$32)
        bra p3f2_fade
p3f2_reset_b:
        clr a
        move a1,x:(r6+$22)
        move a1,x:(r6+$23)
        move #>$1,a
        move a1,x:(r6+$32)
p3f2_fade:
        move x:(r6+$30),a
        move a1,x:(r6+$31)
        ; The original trigger is followed by cVoice::update. A prefix render
        ; can change oscillator A's increment before the primary swap; apply
        ; this mandatory update AFTER the swap, including an interior trig.
        move x:>$3975,a
        move a1,x:(r6+$4)
        clr a
        move a1,x:(r6+$5)
        rts
'''


def build(out, *, native_clock=False):
    out = Path(out)
    source, fresh = HISTORICAL_BUILD(out)
    ready = source.index('pks_voice_ready:')
    entry = source.index('pks_fold_entry:', ready)
    source = source[:ready] + '''pks_voice_ready:
        move x:(r4+$13),a
        and #>$ff,a
        tst a
        beq pks_fold_entry
        cmp #>$3,a
        beq pks_fold2_entry
        cmp #>$2,a
        beq pks_simple_entry
        bra pks_silence
''' + source[entry:]
    old = 'pks_fold2_entry:\n        jsrl pk_multi_fold2_init\n        bra pks_tone_common\n'
    assert source.count(old) == 1
    source = source.replace(old, FOLD2_ENTRY)
    # Split only at explicit branch destinations. No piece falls through a
    # relocation boundary: dispatch branches to an entry and every event path
    # branches to pks_continue. The stock return is a separate small shard.
    source = source.replace('pks_fold_entry:', '; ===== END synth_seam_glue.asm =====\n; ===== BEGIN pk_three_controls =====\npks_fold_entry:', 1)
    source = source.replace('pks_silence:', '; ===== END pk_three_controls =====\n; ===== BEGIN pk_three_finish =====\npks_silence:', 1)
    # The original final marker now belongs to the return/silence shard.
    original_end = source.rindex('; ===== END synth_seam_glue.asm =====')
    source = source[:original_end]+source[original_end:].replace('; ===== END synth_seam_glue.asm =====','; ===== END pk_three_finish =====',1)
    source = '; PERKY3_CORE_OWNED\n'+source
    retired = ('synthetic_control_map.asm', 'noise_tone_voice_xstate_glue.asm',
               'noise_tone_filter.asm', 'noise_tone_oscillator_packed.asm',
               'noise_tone_envelope_packed7.asm', 'noise_tone_envelope.asm',
               'noise_tone_mix.asm', 'pk_multi_noise_init')
    for name in retired:
        pattern = r'; ===== BEGIN '+re.escape(name)+r' =====.*?; ===== END '+re.escape(name)+r' =====\n?'
        source, count = re.subn(pattern, '', source, flags=re.S)
        assert count == 1, name
    noise = (ROOT/'modules/perky/noise_tone_voice_native_xstate.asm').read_text().split('\npknv_noise:', 1)[1]
    source += piece('fold_rng_glue', 'pknv_noise:'+noise)
    source += piece('fold_drum2_seam.asm', (ROOT/'modules/perky/fold_drum2_seam.asm').read_text())
    source += piece('pk_three_fold2_trigger', FOLD2_TRIGGER)
    # Fold2's frequency-high temporary used scratch +0x64, exactly the pitch
    # cache tag at X:0x3964. A later low-pitch p-lock could therefore hit a
    # stale cache row. Keep the 100-word scratch boundary and park this one
    # temporary beside the separately claimed raw-pitch word.
    start=source.index('; ===== BEGIN fold_drum2_voice.asm =====')
    end=source.index('; ===== END fold_drum2_voice.asm =====',start)
    body,count=re.subn(r'x:\(r5\+\$64\)', 'x:>$3976',source[start:end])
    assert count==2,'Fold2 high-frequency temporary census'
    source=source[:start]+body+source[end:]
    noise_step='pk_noise_step:'+source.split('\npk_noise_step:',1)[1].split('; ===== END noise_tone_math.asm =====',1)[0]
    source,count=re.subn(r'; ===== BEGIN noise_tone_math.asm =====.*?; ===== END noise_tone_math.asm =====',piece('noise_tone_math.asm',fold_rng_source.generate()+noise_step),source,flags=re.S)
    assert count==1
    # Removing Noise/Tone releases enough low Y for all three ORIGINAL waves
    # as direct u16 words. Eliminate per-sample unpacking without changing any
    # waveform, interpolator arithmetic, phase transition or envelope.
    reader='''pksdo_read_s16:
        move #>$0007a5,r1
        move x0,n1
        move y:(r1+n1),a
        rts
'''
    source,count=re.subn(r'pksdo_read_s16:.*?(?=; ===== END simple_drum_oscillator.asm =====)',reader,source,flags=re.S)
    assert count==1
    env_reader='''pksde_read_u16:
        move #>$000aa5,r1
        move x0,n1
        move y:(r1+n1),a
        rts
'''
    source,count=re.subn(r'pksde_read_u16:.*?(?=; ===== END simple_drum_envelope.asm =====)',env_reader,source,flags=re.S)
    assert count==1
    source=source.replace('        cmp     #>$24a0,a\n        beq     pksdo_wave3\n','')
    source,count=re.subn(r'pksdo_wave3:.*?(?=pksdo_unknown_wave:)', '',source,flags=re.S)
    assert count==1
    # Expose the exact pre-frequency-converter table value to Fold2's update.
    needle = '        asr     x0,a,a\n        move    a1,x0\n        move    #>$00bb80,y0'
    assert source.count(needle) == 1
    source = source.replace(needle, '        asr     x0,a,a\n        move    a1,x:>$3975\n        move    a1,x0\n        move    #>$00bb80,y0')
    # Fold2 starts from the PRE-trigger object, not an already-swapped post-hit
    # object whose envelopes were merely zeroed. The first trig owns that swap.
    raw = (ROOT/'out/perky/engine-fixtures/engine-4-mode-1-corner-0/wrapper-window-pre-trigger.bin').read_bytes()[0xc4:0xc4+0x134]
    words = fold2.FoldDrum2.from_arm(raw).words
    init = '''pk_multi_fold2_init:
        move x:>$418,a
        lsr #$5,a
        move a1,n1
        move #>$38ee,r1
        move x:(r1+n1),b
        cmp #>$d,b
        beq p3f2_initialized
        move #>$d,a
        move a1,x:(r1+n1)
        move r6,r1
        clr a
        do #>$3a,p3f2_zero
        move a1,x:(r1)+
p3f2_zero:
        nop
'''
    for i, value in enumerate(words):
        if value: init += f'        move #>${value:06x},a\n        move a1,x:(r6+${i:x})\n'
    init += 'p3f2_initialized:\n        rts\n'
    source, count = re.subn(r'; ===== BEGIN pk_multi_fold2_init =====.*?; ===== END pk_multi_fold2_init =====', piece('pk_multi_fold2_init',init), source, flags=re.S)
    assert count == 1
    raw1 = (ROOT/'out/perky/engine-fixtures/engine-1-mode-1-corner-0/wrapper-window-pre-trigger.bin').read_bytes()[0xc4:0xc4+0xf4]
    fresh = fold1.FoldDrum1.from_arm(raw1).words
    init1 = init[:init.index('p3f2_zero:\n')+len('p3f2_zero:\n        nop\n')]
    init1 = init1.replace('pk_multi_fold2_init','pk_multi_fold_init').replace('#>$d,','#>$c,').replace('p3f2_initialized','p3f1_initialized').replace('p3f2_zero','p3f1_zero')
    for i,value in enumerate(fresh):
        if value: init1 += f'        move #>${value:06x},a\n        move a1,x:(r6+${i:x})\n'
    init1 += 'p3f1_initialized:\n        rts\n'
    source,count = re.subn(r'; ===== BEGIN pk_multi_fold_init =====.*?; ===== END pk_multi_fold_init =====',piece('pk_multi_fold_init',init1),source,flags=re.S)
    assert count == 1
    if native_clock:
        for label in ('pk_three_fold2_trigger',):
            source=source.replace(label+':\n',label+':\n        jsrl pk_clock_reset\n',1)
        for label in ('pk_multi_simple_init','pk_multi_fold_init','pk_multi_fold2_init'):
            start=source.index(label+':');end=source.index('; ===== END',start)
            body=source[start:end]
            body,count=re.subn(r'(?m)^(\s*move r6,r1\n)',r'        jsrl pk_clock_reset\n\1',body,count=1)
            assert count==1,label
            source=source[:start]+body+source[end:]
        source,count=re.subn(r'        move    #\$0,r0\n        do      #\$20,pks_scaled_output.*?pks_scaled_output:\n        nop\n',
                            '        ; Clock adapter already applied the exact integration gain.\n',source,flags=re.S)
        assert count==1,'double integration trim'
        source=three_segment_source.compose(source,piece)
        source+=piece('pk_source_clock_prepare',source_clock.PREPARE)
        source+=piece('pk_source_clock_finish',source_clock.FINISH)
    source = historical.multi.source.noise.force_long_local_jsr(source)
    # dsp_asm interprets a numeric Bcc/BRA operand as a DISPLACEMENT, while
    # a symbolic operand is a target address. Record each branch PC so the
    # shard rewriter can preserve that distinction across piece boundaries.
    lines=[];branch=0
    for line in source.splitlines():
        if re.match(r'^\s*b(?:ra|cc|cs|eq|ne|ge|gt|le|lt|pl|mi|vc|vs|hs|lo)\s+[A-Za-z_]',line):
            lines.append(f'p3site{branch:05d}:');branch+=1
        lines.append(line)
    source='\n'.join(lines)+'\n'
    (out/'multi.asm').write_text(source)
    (out/'three.asm').write_text(source)
    # Direct waves occupy the retired noise and packed-wave region. Keep
    # envelope and pitch-bank addresses so their already-qualified arithmetic
    # and decoding are unchanged. Generated proprietary tables stay in out/.
    values = [int(v,16) for v in (out/'tables.words').read_text().split()]
    import struct
    wave_words=[]
    for address in (0x080222a0,0x080226a0,0x080228a0):
        words=struct.unpack('<256h',(ROOT/f'out/perky/simple-drum-assets/wave_{address:08x}.bin').read_bytes())
        wave_words.extend(v&0xffffff for v in words)
    env_words=list(struct.unpack('<2048H',(ROOT/'out/perky/simple-drum-assets/envelope1.bin').read_bytes()))[:1024]
    values[:1878]=wave_words+env_words+[0]*(1878-len(wave_words)-len(env_words))
    if native_clock:
        assert 0x7a5+len(values)==source_clock.COEFFICIENTS
        values+=source_clock.coefficient_words()
    (out/'tables.words').write_text('\n'.join(f'{v:06x}' for v in values)+'\n')
    raw_tables = b''.join(v.to_bytes(3,'little') for v in values)
    (out/'tables.bin').write_bytes(raw_tables)
    layout = json.loads((out/'layout.json').read_text())
    layout['sha256'] = hashlib.sha256(raw_tables).hexdigest()
    layout['total_words']=len(values)
    layout['retired_noise_wave_words'] = 683
    layout['banks']['simple_waves']=0x7a5
    layout['banks']['simple_envelope']=0xaa5
    layout['direct_wave_words']=768
    layout['direct_envelope_words']=1024
    layout['free_y_words']=[[0xea5,0xefb]]
    layout['noise_provenance'] = 'retired; RNG helper only for Fold transients'
    layout['extra_x_claim'] = [0x3975,2,'Fold2 raw pitch table value and frequency-high temporary']
    if native_clock:
        layout['source_clock']={'base_word':source_clock.BASE,'words':17,
                                'native_rate':48000,'output_rate':44100,
                                'buffer_word':source_clock.BUFFER,'buffer_words':40}
    (out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    return source, fresh


if __name__ == '__main__': build(ROOT/'out/perky/three')
