"""Exact Acoustic Hats DSP recipe, with a qualification-only sample bank.

The sample base is supplied at scratch +$74. It is not a shipping allocation:
the complete assets require a separately qualified physical streaming backend.
"""
from dsp_source_layout import center_scratch
import acoustic_hats_compact as h
from acoustic_float_dsp import kernels
from dsp_u32 import Emitter
from resonant_dsp import PERKY


def sample(e, destination, index):
    e.load(index, signed=False)
    e.emit('asl #$10,a,a', 'move a1,n1', 'move x:(r5+$74),r1',
           'move (r1)+n1', 'move y:(r1),a', 'asl #$8,a,a', 'move a1,a',
           'asr #$8,a,a', 'asr #$10,a,a')
    e.save(destination)


def source():
    e = Emitter()
    e.lines.append('pk_acoustic_voice:')
    e.emit('move r5,a', 'add #>$80,a', 'move a1,r4',
           'move r6,a', 'move a1,x:(r5+$7e)', 'do n7,pkac_samples_done',
           'move x:(r5+$7e),r6', 'lua (r6+$2),r6', 'jsr pk_noise_hat_envelope',
           'move x:(r5+$7e),r6')
    amp = e.var('ac_amp')
    e.emit(f'move a1,{e.addr(amp)}', 'clr a', f'move a1,{e.addr(amp, 1)}')
    index, length, next_index, fraction, mask, shift, hold, interpolated = (e.var('ac_' + name) for name in
        ('index', 'length', 'next_index', 'fraction', 'mask', 'shift', 'hold', 'interpolated'))
    current, nxt, complement, weighted, temp, scaled, advance, previous, filtered, output = (
        e.var('ac_' + name) for name in ('current', 'next', 'complement', 'weighted', 'temp', 'scaled',
                                       'advance', 'previous', 'filtered', 'output'))
    silent, next_sample = e.label(), e.label()
    e.assign(index, e.state(h.INDEX))
    e.assign(length, e.state(h.SAMPLE_LENGTH))
    e.compare(index, length, 'bge', silent, signed=False)
    e.assign(fraction, e.state(h.FRACTION))
    e.assign(mask, e.state(h.MASK))
    e.assign(shift, e.state(h.SHIFT, 16))
    e.assign(hold, e.state(h.HOLD))
    refresh, interpolation_done = e.label(), e.label()
    e.compare(hold, 0, 'beq', refresh)
    e.sub(hold, hold, 1)
    e.assign(interpolated, ('r5', 0x72, 32))
    e.emit('bra ' + interpolation_done)
    e.mark(refresh)
    sample(e, current, index)
    e.add(next_index, index, 1)
    e.assign(nxt, 0)
    no_next = e.label()
    e.compare(next_index, length, 'bge', no_next, signed=False)
    sample(e, nxt, next_index)
    e.mark(no_next)
    e.mul(weighted, fraction, nxt)
    e.sub(complement, mask, fraction)
    e.mul(temp, complement, current)
    e.add(interpolated, weighted, temp)
    e.add(temp, shift, 1)
    e.shift(interpolated, interpolated, temp)
    e.assign(('r5', 0x72, 32), interpolated)
    e.assign(hold, e.state(h.HOLD_RELOAD))
    e.mark(interpolation_done)
    e.mul(scaled, interpolated, amp)
    e.shift(scaled, scaled, 15)
    e.assign(e.state(h.HOLD), hold)
    e.add(temp, fraction, e.state(h.INCREMENT))
    e.shift(advance, temp, shift, signed=False)
    e.add(index, index, advance)
    e.assign(e.state(h.INDEX), index)
    e.bits(fraction, temp, mask)
    e.assign(e.state(h.FRACTION), fraction)

    clean_history, history_ready = e.label(), e.label()
    e.compare(e.state(h.FILTER_DIRTY, 16), 0, 'beq', clean_history)
    e.assign(e.var('fp_int_in'), e.state(h.FILTER_INT))
    e.emit('jsr pk_acoustic_int_to_float')
    e.assign(previous, e.var('fp_bits_out'))
    e.assign(e.state(h.FILTER_DIRTY, 16), 0)
    e.emit('bra ' + history_ready)
    e.mark(clean_history)
    e.assign(previous, e.state(h.FILTER_FLOAT))
    e.mark(history_ready)
    # Multiplying signed zero by 0.98 preserves it. The envelope-scaled input
    # is signed17, exactly representable as float: adding either signed zero
    # and converting back leaves that integer unchanged. This common path
    # avoids software float work without changing any stored IEEE754 bit.
    nonzero_history, float_ready = e.label(), e.label()
    e.bits(temp, previous, 0x7FFFFFFF)
    e.compare(temp, 0, 'bne', nonzero_history)
    e.assign(e.state(h.FILTER_FLOAT), previous)
    e.assign(filtered, scaled)
    e.emit('bra ' + float_ready)
    e.mark(nonzero_history)
    e.assign(e.var('fp_bits_in'), previous)
    e.emit('jsr pk_acoustic_float_decay')
    e.assign(e.state(h.FILTER_FLOAT), e.var('fp_bits_out'))
    e.assign(e.var('fp_int_in'), scaled)
    e.emit('jsr pk_acoustic_int_to_float')
    e.assign(e.var('fp_add_b'), e.var('fp_bits_out'))
    e.assign(e.var('fp_add_a'), previous)
    e.emit('jsr pk_acoustic_float_add')
    e.assign(e.var('fp_bits_in'), e.var('fp_bits_out'))
    e.emit('jsr pk_acoustic_float_to_int')
    e.assign(filtered, e.var('fp_int_out'))
    e.mark(float_ready)
    e.assign(e.state(h.FILTER_INT), filtered)
    e.compare(e.state(h.MUTE, 16), 0, 'bne', silent)
    e.mul(output, filtered, e.state(h.VELOCITY, 16))
    e.shift(output, output, 8)
    e.clamp(output, -32768, 32767)
    e.load(output)
    e.emit('asl #$10,a,a', 'move a1,x:(r0)+', 'move a1,x:(r0)+', 'bra ' + next_sample)
    e.mark(silent)
    e.emit('clr a', 'move a1,x:(r0)+', 'move a1,x:(r0)+')
    e.mark(next_sample)
    e.mark('pkac_samples_done')
    e.emit('nop', 'rts')
    kernels(e)
    text = ('; Acoustic Hats exact DSP candidate; sample base at scratch+$74.\n'
            + '\n'.join(e.lines) + '\n' + (PERKY / 'noise_hat_envelope.asm').read_text()
            + (PERKY / 'noise_tone_math.asm').read_text())
    return center_scratch(text, 'pk_acoustic_voice', variables=True), 0x80 + len(e.variables) * 2
