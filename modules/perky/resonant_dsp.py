"""Exact DSP source recipes for the v1.2.1 resonant bass/snare renderers.

Each arithmetic operation preserves the ARM low32 result. The initial recipe
uses the proven two-limb multiply kernel; timing qualification is independent.
No table bytes are embedded. Interpolation tables are direct u16 Y words.
"""
from dsp_source_layout import center_scratch
from pathlib import Path
import re
from dsp_u32 import Emitter
import resonator_compact as c
import resonant_bass_compact as bass
import resonant_snare_compact as snare

PERKY = Path(__file__).resolve().parent
INTERP_A, INTERP_B = 0x3000, 0x3200



def decay(e, base, output, *, sign_flip=True, constant=0):
    s = lambda off: e.state(base + off)
    value, count, sign, absolute = (e.var('d_' + name) for name in ('value', 'count', 'sign', 'abs'))
    e.mul(value, s(c.DECAY_MUL), s(c.DECAY_VALUE))
    e.shift(value, value, 12, signed=False)
    minimum_ok = e.label()
    e.compare(value, s(c.DECAY_MIN), 'bge', minimum_ok)
    e.assign(value, s(c.DECAY_MIN))
    e.mark(minimum_ok)
    e.assign(s(c.DECAY_VALUE), value)
    e.assign(count, s(c.DECAY_COUNT))
    e.assign(sign, s(c.DECAY_SIGN))
    count_done = e.label()
    e.compare(count, 0, 'ble', count_done)
    e.sub(count, count, 1)
    e.assign(s(c.DECAY_COUNT), count)
    e.compare(count, 0, 'bne', count_done)
    e.abs(absolute, sign)
    e.add(value, value, absolute)
    e.assign(s(c.DECAY_VALUE), value)
    e.mark(count_done)
    if sign_flip:
        positive = e.label()
        e.compare(sign, 0, 'bge', positive)
        e.sub(value, 0, value)
        e.mark(positive)
    if constant:
        no_constant = e.label()
        e.compare(count, 0, 'beq', no_constant)
        e.add(value, value, constant)
        e.mark(no_constant)
    e.assign(output, value)


def resonator(e, base, input_value):
    s = lambda off, width=32: e.state(base + off, width)
    clean = e.label()
    e.compare(s(c.RES_DIRTY, 16), 0, 'beq', clean)
    e.interpolation(s(c.RES_COEFF_B), s(c.RES_PITCH_A, 16), INTERP_A)
    e.interpolation(s(c.RES_COEFF_A), s(c.RES_PITCH_B, 16), INTERP_B)
    e.assign(s(c.RES_DIRTY, 16), 0)
    e.mark(clean)
    ca, cb, pos, vel, mod, scale, temp, filtered = (e.var('r_' + name) for name in
        ('ca', 'cb', 'pos', 'vel', 'mod', 'scale', 'temp', 'filtered'))
    e.assign(ca, s(c.RES_COEFF_A))
    e.assign(cb, s(c.RES_COEFF_B))
    e.assign(pos, s(c.RES_POSITION))
    e.assign(vel, s(c.RES_VELOCITY))
    e.assign(mod, s(c.RES_MOD))
    no_mod, small_pos = e.label(), e.label()
    e.compare(mod, 0, 'beq', no_mod)
    e.assign(scale, 0x80)
    e.compare(pos, 0x1000, 'ble', small_pos)
    e.sub(temp, pos, 0x800)
    e.shift(temp, temp, 3)
    e.add(ca, ca, temp)
    e.shift(scale, pos, 4)
    e.mark(small_pos)
    e.mul(temp, scale, mod)
    e.shift(temp, temp, 9)
    e.add(cb, cb, temp)
    e.mark(no_mod)
    e.assign(filtered, input_value)
    bypassed = e.label()
    e.compare(s(c.RES_BYPASS, 16), 0, 'bne', bypassed)
    e.mul(temp, vel, ca)
    e.shift(temp, temp, 15)
    e.sub(filtered, filtered, temp)
    e.mark(bypassed)
    e.mul(temp, vel, cb)
    e.shift(temp, temp, 15)
    e.add(pos, pos, temp)
    e.clamp(pos)
    e.assign(s(c.RES_POSITION), pos)
    e.sub(filtered, filtered, pos)
    e.mul(temp, cb, filtered)
    e.shift(temp, temp, 15)
    e.add(vel, vel, temp)
    e.clamp(vel)
    e.assign(s(c.RES_VELOCITY), vel)
    return s(c.RES_VELOCITY)


def snare_sample(e):
    first_drive, a, b, cv, first_mix, second_mix, d, random_value, tmp, mixed = (
        e.var(name) for name in ('first_drive', 'decay_a', 'decay_b', 'decay_c',
                                'first_mix', 'second_mix', 'decay_d', 'noise', 'tmp', 'mixed'))
    decay(e, snare.DECAY_A, a)
    decay(e, snare.DECAY_B, b, constant=0xA3D)
    e.add(first_drive, a, b)
    velocity1 = resonator(e, snare.RES1, first_drive)
    e.shift(first_mix, first_drive, 4)
    e.add(first_mix, velocity1, first_mix)
    decay(e, snare.DECAY_C, cv, constant=0x3333)
    velocity2 = resonator(e, snare.RES2, cv)
    e.shift(second_mix, cv, 4)
    e.add(second_mix, velocity2, second_mix)
    decay(e, snare.DECAY_D, d)
    e.emit('jsr pk_resonant_noise', 'asl #$8,a,a', 'move a1,a', 'asr #$8,a,a', 'asr #$10,a,a')
    e.save(random_value)
    velocity3 = resonator(e, snare.RES3, random_value)
    e.mul(mixed, second_mix, e.state(snare.MIX_SECOND))
    e.shift(mixed, mixed, 15)
    e.mul(tmp, e.state(snare.MIX_FIRST), first_mix)
    e.shift(tmp, tmp, 15)
    e.add(mixed, mixed, tmp)
    e.mul(tmp, velocity3, d)
    e.shift(tmp, tmp, 15)
    e.add(mixed, mixed, tmp)
    e.add(mixed, mixed, mixed)
    return mixed


def bass_sample(e):
    a, b, drive, ignored, pitch, quarter, inp, delta, level, random_value, temp, mixed = (
        e.var(name) for name in ('decay_a', 'decay_b', 'drive', 'ignored', 'pitch', 'quarter',
                                'input', 'delta', 'level', 'noise', 'tmp', 'mixed'))
    decay(e, bass.DECAY_A, a, sign_flip=False)
    positive_a, no_constant = e.label(), e.label()
    e.compare(e.state(bass.DECAY_B + c.DECAY_COUNT), 0, 'bge', positive_a)
    e.sub(a, 0, a)
    e.mark(positive_a)
    e.compare(e.state(bass.DECAY_B + c.DECAY_COUNT), 0, 'beq', no_constant)
    e.add(a, a, 1 << 14)
    e.mark(no_constant)
    decay(e, bass.DECAY_B, b)
    e.add(drive, a, b)
    decay(e, bass.DECAY_C, ignored, sign_flip=False)
    e.assign(pitch, e.state(bass.PITCH, 16))
    no_offset = e.label()
    e.compare(e.state(bass.DECAY_C + c.DECAY_COUNT), 0, 'beq', no_offset)
    e.add(pitch, pitch, 0x880)
    e.mark(no_offset)
    # Pitch addition narrows to u16 before comparing against the cached pitch.
    e.emit('clr a', f'move a1,{e.addr(pitch, 1)}')
    unchanged_pitch = e.label()
    e.compare(e.state(bass.TONE_RES + c.RES_PITCH_A, 16), pitch, 'beq', unchanged_pitch)
    e.assign(e.state(bass.TONE_RES + c.RES_PITCH_A, 16), pitch)
    e.assign(e.state(bass.TONE_RES + c.RES_DIRTY, 16), 1)
    e.mark(unchanged_pitch)
    velocity = resonator(e, bass.TONE_RES, drive)
    e.shift(quarter, drive, 4)
    e.add(inp, velocity, quarter)
    e.sub(delta, inp, e.state(bass.RESONATOR_STATE))
    decay(e, bass.DECAY_LEVEL, level)
    e.mul(temp, e.state(bass.RESONATOR_COEFF), delta)
    e.shift(temp, temp, 15)
    e.add(mixed, e.state(bass.RESONATOR_STATE), temp)
    e.assign(e.state(bass.RESONATOR_STATE), mixed)
    e.emit('jsr pk_resonant_noise', 'asl #$8,a,a', 'move a1,a', 'asr #$8,a,a', 'asr #$10,a,a')
    e.save(random_value)
    noise_vel = resonator(e, bass.NOISE_RES, random_value)
    e.mul(temp, noise_vel, level)
    e.shift(temp, temp, 16)
    e.add(mixed, mixed, temp)
    e.add(temp, mixed, mixed)
    e.add(mixed, mixed, temp)
    return mixed


def source(family):
    assert family in ('bass', 'snare')
    e = Emitter()
    e.lines.append(f'pk_resonant_{family}_voice:')
    e.emit('move r5,a', 'add #>$80,a', 'move a1,r4',
           'move r6,a', 'move a1,x:(r5+$7e)', 'do n7,pkr_samples_done',
           'move x:(r5+$7e),r6', 'lua (r6+$1),r6', 'jsr pk_noise_hat_envelope',
           'move x:(r5+$7e),r6')
    mixed = bass_sample(e) if family == 'bass' else snare_sample(e)
    output = e.var('output')
    e.mul(output, mixed, e.state(0, 16))
    e.shift(output, output, 8)
    e.clamp(output, -32768, 32767)
    e.load(output)
    e.emit('asl #$10,a,a', 'move a1,x:(r0)+', 'move a1,x:(r0)+')
    e.mark('pkr_samples_done')
    e.emit('nop', 'rts')
    noise = '\npk_resonant_noise:' + (PERKY / 'slap_voice.asm').read_text().split('\npk_slap_noise:', 1)[1]
    noise = noise.replace('pkslv_noise_refresh', 'pkr_noise_refresh')
    fields = {'d': 'c', 'e': 'd', 'f': 'e'}
    noise = re.sub(r'(r6\+\$)([0-9a-f]+)', lambda m: m[1] + fields.get(m[2], m[2]), noise)
    text = ('; Exact v1.2.1 resonant ' + family + ' DSP recipe; direct interpolation tables.\n'
            + '\n'.join(e.lines) + noise + (PERKY / 'noise_hat_envelope.asm').read_text()
            + (PERKY / 'noise_tone_math.asm').read_text())
    return center_scratch(text, f'pk_resonant_{family}_voice', variables=True), 0x80 + len(e.variables) * 2
