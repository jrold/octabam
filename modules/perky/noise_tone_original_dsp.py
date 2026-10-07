"""Authentic shared and Waveform2 Noise/Tone DSP source recipes.

Standalone qualification compositions; production control/asset transport is
separate. Shared modes also supply Resonant Drums panel M3.
"""
from dsp_source_layout import center_scratch
import re
import noise_tone_compact as shared
import noise_tone_wave2_compact as w2
from dsp_u32 import Emitter
from resonant_dsp import PERKY


def finish(e, output, silent, next_sample, done):
    e.clamp(output, -32768, 32767)
    e.load(output)
    e.emit('asl #$10,a,a', 'move a1,x:(r0)+', 'move a1,x:(r0)+', 'bra ' + next_sample)
    e.mark(silent)
    e.emit('clr a', 'move a1,x:(r0)+', 'move a1,x:(r0)+')
    e.mark(next_sample)
    e.mark(done)
    e.emit('nop', 'rts')


def start(e, target, done):
    e.lines.append(target + ':')
    e.emit('move r5,a', 'add #>$80,a', 'move a1,r4', 'move r6,a',
           'move a1,x:(r5+$7e)', 'do n7,' + done, 'move x:(r5+$7e),r6')


def sample_result(e, dst):
    # Primitive ABI returns A1 only. Drop stale extension/fractional bits before
    # using the full accumulator to align that signed16 for the limb kernel.
    e.emit('move a1,a', 'asr #$10,a,a')
    e.save(dst)


def shared_source():
    e = Emitter()
    start(e, 'pk_original_noise_tone_voice', 'pkont_done')
    amp, noise, osc1, osc2, mix, accum, temp, output = (e.var('nt_' + name) for name in
        ('amp', 'noise', 'osc1', 'osc2', 'mix', 'accum', 'temp', 'output'))
    e.emit('lua (r6+$1),r6', 'jsr pk_noise_hat_envelope', 'move x:(r5+$7e),r6',
           f'move a1,{e.addr(amp)}', 'move a1,x:(r5+$60)', 'clr a', f'move a1,{e.addr(amp, 1)}',
           'jsr pk_ont_noise', 'move a1,x:(r5+$61)',
           'asl #$8,a,a', 'move a1,a', 'asr #$8,a,a')
    sample_result(e, noise)
    e.emit('jsr pk_ont_filter', 'lua (r6+$17),r7', 'jsr pk_simple_oscillator',
           'move a1,x:(r5+$62)')
    sample_result(e, osc1)
    e.emit('lua (r6+$1f),r7', 'jsr pk_simple_oscillator', 'move a1,x:(r5+$63)')
    sample_result(e, osc2)
    e.assign(mix, e.state(shared.MIX))
    general_mix, silent, next_sample = e.label(), e.label(), e.label()
    # Authentic prepared MIX is 0..4095. Preserve arbitrary u32 probe states
    # with the general limb path; the bounded path uses the qualified native
    # mixer without changing the PCM result or any renderer state.
    e.compare(mix, 0xFFF, 'bgt', general_mix, signed=False)
    e.emit('jsr pk_ont_mix', 'move a1,x:(r0)+', 'move a1,x:(r0)+', 'bra ' + next_sample)
    e.mark(general_mix)
    e.mul(accum, mix, noise)
    e.shift(accum, accum, 13)
    e.add(temp, osc1, osc2)
    e.shift(temp, temp, 4)
    e.sub(output, 0xFFF, mix)
    e.mul(temp, output, temp)
    e.shift(temp, temp, 9)
    e.add(accum, accum, temp)
    e.mul(output, accum, amp)
    e.shift(output, output, 16)
    e.mul(output, output, e.state(0, 16))
    e.shift(output, output, 8)
    finish(e, output, silent, next_sample, 'pkont_done')
    noise_source = '\npk_ont_noise:' + (PERKY / 'slap_voice.asm').read_text().split('\npk_slap_noise:', 1)[1]
    noise_source = noise_source.replace('pkslv_noise_refresh', 'pkont_noise_refresh')
    fields = {'d': 'c', 'e': 'd', 'f': 'e'}
    noise_source = re.sub(r'(r6\+\$)([0-9a-f]+)', lambda m: m[1] + fields.get(m[2], m[2]), noise_source)
    osc = (PERKY / 'simple_drum_oscillator.asm').read_text().split('\npk_simple_oscillator:', 1)[1]
    text = '\n'.join(e.lines) + noise_source + '\npk_simple_oscillator:' + osc
    # Keep bounded first/velocity registers live across both filter passes.
    filt = (PERKY / 'noise_tone_filter_native.asm').read_text()
    filt = filt.replace('pk_filter_probe', 'pk_ont_filter').replace('mpy x0,y1,a', 'move y0,n2\n move y1,y0\n mpy y0,x0,a\n move n2,y0')
    mix_source = (PERKY / 'noise_tone_mix_native.asm').read_text().replace('pk_mix_probe', 'pk_ont_mix')
    debug = mix_source.index('move a1,b\n and #>$00ffff,b\n move b1,x:(r5+$48)')
    clamp = mix_source.index('cmp #>$007fff,a', debug)
    mix_source = mix_source[:debug] + mix_source[clamp:]
    mix_source = mix_source.replace(' and #>$00ffff,a\n move a1,x:(r5+$47)\n', '')
    text += '\n' + filt + '\n' + mix_source
    for name in ('noise_hat_envelope.asm', 'noise_tone_math.asm'):
        text += '\n' + (PERKY / name).read_text()
    return center_scratch(text, 'pk_original_noise_tone_voice', variables=True), 0x80 + len(e.variables) * 2


def wave2_source():
    e = Emitter()
    start(e, 'pk_noise_tone_wave2_voice', 'pkntw_done')
    amp, phase, lookup, current, index, fraction, first, second, temp, output = (
        e.var('tw_' + name) for name in ('amp', 'phase', 'lookup', 'current', 'index',
                                        'fraction', 'first', 'second', 'temp', 'output'))
    e.emit('lua (r6+$2),r6', 'jsr pk_noise_hat_envelope', 'move x:(r5+$7e),r6',
           f'move a1,{e.addr(amp)}', 'clr a', f'move a1,{e.addr(amp, 1)}')
    e.assign(phase, e.state(w2.PHASE))
    no_reduction = e.label()
    e.compare(phase, e.state(w2.REDUCTION), 'ble', no_reduction, signed=False)
    e.sub(phase, phase, e.state(w2.REDUCTION))
    e.mark(no_reduction)
    e.add(phase, phase, e.state(w2.INCREMENT))
    no_wrap = e.label()
    e.compare(phase, 0x100000, 'ble', no_wrap)
    e.sub(phase, phase, 0x100000)
    e.assign(e.state(w2.CURRENT), e.state(w2.NEXT))
    e.mark(no_wrap)
    e.assign(e.state(w2.PHASE), phase)
    e.assign(lookup, phase)
    no_offset = e.label()
    e.compare(e.state(w2.OFFSET), 0, 'beq', no_offset)
    e.add(lookup, lookup, e.state(w2.OFFSET))
    e.compare(lookup, 0x100000, 'ble', no_offset)
    e.sub(lookup, lookup, 0x100000)
    e.mark(no_offset)
    e.shift(index, lookup, 9, signed=False)
    e.bits(index, index, 0x7FF)
    e.bits(fraction, lookup, 0x1FF)
    e.assign(current, e.state(w2.CURRENT))
    wave_b, table_ready = e.label(), e.label()
    e.compare(current, ('r5', 0x78, 32), 'bne', wave_b)
    e.emit('move x:(r5+$76),a', 'move a1,x:(r5+$75)', 'bra ' + table_ready)
    e.mark(wave_b)
    e.emit('move x:(r5+$77),a', 'move a1,x:(r5+$75)')
    e.mark(table_ready)
    for dst in (first, second):
        e.load(index, signed=False)
        e.emit('asl #$10,a,a', 'move a1,n1', 'move x:(r5+$75),r1',
               'move (r1)+n1', 'move y:(r1),a', 'asl #$8,a,a', 'move a1,a', 'asr #$8,a,a')
        sample_result(e, dst)
        if dst == first:
            e.add(index, index, 1)
            e.bits(index, index, 0x7FF)
    e.sub(temp, second, first)
    e.mul(temp, temp, fraction)
    e.shift(temp, temp, 9)
    e.add(output, first, temp)
    e.mul(output, output, amp)
    e.shift(output, output, 17)
    e.mul(output, output, e.state(0, 16))
    e.shift(output, output, 8)
    silent, next_sample = e.label(), e.label()
    e.compare(e.state(w2.MUTE, 16), 0, 'bne', silent)
    finish(e, output, silent, next_sample, 'pkntw_done')
    text = '\n'.join(e.lines)
    for name in ('noise_hat_envelope.asm', 'noise_tone_math.asm'):
        text += '\n' + (PERKY / name).read_text()
    return center_scratch(text, 'pk_noise_tone_wave2_voice', variables=True), 0x80 + len(e.variables) * 2
