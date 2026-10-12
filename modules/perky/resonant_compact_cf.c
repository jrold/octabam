/* ARM-shaped Resonant object -> the compact renderer layout, in C.
 *
 * THE MISSING HALF OF PRODUCTION PARAMETER DELIVERY.
 *
 * The authentic v1.2.1 machine updates a Resonant voice on the CPU, per event:
 * `res_update_bass`/`res_update_snare` (exposed by cf_perky4.c, translated from
 * the ARM routines at 0x0802682C / 0x08026030) write the panel's TUNE, DECAY,
 * ENV and MIX into an ARM-shaped object. The DSP port renders from a COMPACT
 * layout instead, and until now the only thing that ever crossed between them was
 * a fixed template computed at a neutral panel setting -- so the instruments made
 * sound but ignored their knobs.
 *
 * This is the bridge. It is a deliberate line-by-line port of the models' own
 * `from_arm` (resonant_bass_compact.py / resonant_snare_compact.py) plus the
 * `copy_*_from_arm` helpers in resonator_compact.py, so the oracle for every
 * field is the renderer's own reader rather than a re-derivation.
 *
 * DELIBERATE OMISSION: the ARM object's pitch-table word at 0x34, which
 * `common_update` fills from the 4096-entry pitch table. `from_arm` never reads
 * that offset, and zeroing the table leaves the compact state bit-identical
 * (measured), so the 8 KiB table is not carried to the ColdFire. The only table
 * the update still needs is the 12-entry chromatic one.
 */
#include <stddef.h>
#include <stdint.h>

/* ---- the compact layouts, from the models ------------------------------- */
#define RC_ENV_STATE 0
#define RC_ENV_SHAPE 1
#define RC_ENV_FLAG4 2
#define RC_ENV_FLAG6 3
#define RC_ENV_TRIGGER 4
#define RC_ENV_VALUE 5
#define RC_ENV_HOLD 7
#define RC_ENV_ATTACK 9
#define RC_ENV_DECAY 10

#define RC_RES_DIRTY 0
#define RC_RES_PITCH_A 1
#define RC_RES_PITCH_B 2
#define RC_RES_COEFF_B 3
#define RC_RES_COEFF_A 5
#define RC_RES_MOD 7
#define RC_RES_BYPASS 9
#define RC_RES_POSITION 10
#define RC_RES_VELOCITY 12

#define RC_DECAY_MUL 0
#define RC_DECAY_COUNT 2
#define RC_DECAY_VALUE 4
#define RC_DECAY_SIGN 6
#define RC_DECAY_MIN 8

#define RC_BASS_WORDS 88
#define RC_SNARE_WORDS 101

/* ---- ARM-object and compact-layout addresses ---------------------------- */
typedef struct {
    unsigned words;         /* compact words for this family                 */
    unsigned noise, amp_env;
} rc_family;

typedef struct { int dirty, pitch_a, pitch_b, coeff_b, coeff_a, mod, bypass,
                 position, velocity; } rc_res_map;

#define RC_ENV_SRC 0x74
#define RC_NOISE_SRC 0x60

static const rc_res_map RC_TONE_MAP =
    {196, 198, 200, 208, 212, 204, 216, 220, 224};
static const rc_res_map RC_NOISE_MAP =
    {344, 346, 348, 356, 360, 352, 364, 368, 372};
static const rc_res_map RC_RES1_MAP =
    {248, 250, 252, 260, 264, 256, 268, 272, 276};
static const rc_res_map RC_RES2_MAP =
    {284, 286, 288, 296, 300, 292, 304, 308, 312};
static const rc_res_map RC_RES3_MAP =
    {320, 322, 324, 332, 336, 328, 340, 344, 348};

static unsigned r16(const uint8_t *p, unsigned o)
{ return (unsigned)p[o] | ((unsigned)p[o + 1] << 8); }

static uint32_t r32(const uint8_t *p, unsigned o)
{ return (uint32_t)r16(p, o) | ((uint32_t)r16(p, o + 2) << 16); }

static void w16(uint16_t *w, unsigned o, unsigned v)
{ w[o] = (uint16_t)v; }

static void w32(uint16_t *w, unsigned o, uint32_t v)
{ w[o] = (uint16_t)v; w[o + 1] = (uint16_t)(v >> 16); }

static void rc_env(uint16_t *w, unsigned dst, const uint8_t *raw, unsigned src)
{
    w[dst + RC_ENV_STATE]   = raw[src];
    w[dst + RC_ENV_SHAPE]   = raw[src + 1];
    w[dst + RC_ENV_FLAG4]   = raw[src + 4];
    w[dst + RC_ENV_FLAG6]   = raw[src + 6];
    w[dst + RC_ENV_TRIGGER] = raw[src + 7];
    w32(w, dst + RC_ENV_VALUE, r32(raw, src + 0x0C));
    w32(w, dst + RC_ENV_HOLD,  r32(raw, src + 0x10));
    w16(w, dst + RC_ENV_ATTACK, r16(raw, src + 0x20));
    w16(w, dst + RC_ENV_DECAY,  r16(raw, src + 0x22));
}

static void rc_noise(uint16_t *w, unsigned dst, const uint8_t *raw, unsigned src)
{
    w16(w, dst, r16(raw, src));
    w16(w, dst + 1, r16(raw, src + 2));
    w16(w, dst + 2, r16(raw, src + 0x10));
}

static void rc_res(uint16_t *w, unsigned dst, const uint8_t *raw,
                   const rc_res_map *m)
{
    w[dst + RC_RES_DIRTY]   = raw[m->dirty];
    w16(w, dst + RC_RES_PITCH_A, r16(raw, m->pitch_a));
    w16(w, dst + RC_RES_PITCH_B, r16(raw, m->pitch_b));
    w32(w, dst + RC_RES_COEFF_B, r32(raw, m->coeff_b));
    w32(w, dst + RC_RES_COEFF_A, r32(raw, m->coeff_a));
    w32(w, dst + RC_RES_MOD,     r32(raw, m->mod));
    w[dst + RC_RES_BYPASS]  = raw[m->bypass];
    w32(w, dst + RC_RES_POSITION, r32(raw, m->position));
    w32(w, dst + RC_RES_VELOCITY, r32(raw, m->velocity));
}

/* `_decay_map(base)`: mul, count, value, sign, min at base + 0,4,8,12,16. */
static void rc_decay(uint16_t *w, unsigned dst, const uint8_t *raw, unsigned base)
{
    w32(w, dst + RC_DECAY_MUL,   r32(raw, base));
    w32(w, dst + RC_DECAY_COUNT, r32(raw, base + 4));
    w32(w, dst + RC_DECAY_VALUE, r32(raw, base + 8));
    w32(w, dst + RC_DECAY_SIGN,  r32(raw, base + 12));
    w32(w, dst + RC_DECAY_MIN,   r32(raw, base + 16));
}

/* Resonant Bass: resonant_bass_compact.py `from_arm`, field for field. */
void pk_cf_res_compact_bass(const uint8_t *raw, uint16_t *w)
{
    unsigned i;
    for (i = 0; i < RC_BASS_WORDS; ++i) w[i] = 0;
    w[0] = raw[6];                                  /* VELOCITY */
    rc_env(w, 1, raw, RC_ENV_SRC);                  /* AMP_ENV  */
    rc_noise(w, 12, raw, RC_NOISE_SRC);             /* NOISE    */
    rc_res(w, 15, raw, &RC_TONE_MAP);               /* TONE_RES */
    w[29] = (uint16_t)r16(raw, 0xF0);               /* PITCH    */
    w32(w, 30, r32(raw, 0xE8));                     /* RESONATOR_STATE */
    w32(w, 32, r32(raw, 0xEC));                     /* RESONATOR_COEFF */
    rc_decay(w, 34, raw, 0xF8);                     /* DECAY_A  */
    rc_decay(w, 44, raw, 0x110);                    /* DECAY_B  */
    rc_decay(w, 54, raw, 0x128);                    /* DECAY_C  */
    rc_decay(w, 64, raw, 0x144);                    /* DECAY_LEVEL */
    rc_res(w, 74, raw, &RC_NOISE_MAP);              /* NOISE_RES */
}

/* Resonant Snare: resonant_snare_compact.py `from_arm`, field for field. It
 * carries NO 0xE8/0xEC word -- the snare's three resonators hold their own. */
void pk_cf_res_compact_snare(const uint8_t *raw, uint16_t *w)
{
    unsigned i;
    for (i = 0; i < RC_SNARE_WORDS; ++i) w[i] = 0;
    w[0] = raw[6];                                  /* VELOCITY */
    rc_env(w, 1, raw, RC_ENV_SRC);                  /* AMP_ENV  */
    rc_noise(w, 12, raw, RC_NOISE_SRC);             /* NOISE    */
    rc_res(w, 15, raw, &RC_RES1_MAP);               /* RES1     */
    rc_res(w, 29, raw, &RC_RES2_MAP);               /* RES2     */
    rc_res(w, 43, raw, &RC_RES3_MAP);               /* RES3     */
    rc_decay(w, 57, raw, 0x174);                    /* DECAY_A  */
    rc_decay(w, 67, raw, 0x18C);                    /* DECAY_B  */
    rc_decay(w, 77, raw, 0x1A4);                    /* DECAY_C  */
    rc_decay(w, 87, raw, 0x1BC);                    /* DECAY_D  */
    /* The two mix coefficients. They are NOT decay ramps and have no map of
     * their own; the first version of this port missed them entirely, which is
     * precisely the kind of omission the bit-exact comparison below exists to
     * catch. */
    w32(w, 97, r32(raw, 0x168));                    /* MIX_SECOND */
    w32(w, 99, r32(raw, 0x164));                    /* MIX_FIRST  */
}

/* ======================================================================== *
 *  The control law: common_update / update_bass / update_snare and the
 *  triggers, ported from resonant_control_update.py (itself the exact
 *  recovery of ARM 0x0802682C / 0x08026030 / 0x08024714 / 0x08024878).
 *
 *  This is what makes a knob audible. The bridge above only moves a state
 *  between two layouts; without this the state is whatever template was baked
 *  at a neutral panel setting.
 * ======================================================================== */

static uint16_t ru16(const uint8_t *p, unsigned o)
{ return (uint16_t)((unsigned)p[o] | ((unsigned)p[o + 1] << 8)); }

static void rput16(uint8_t *p, unsigned o, unsigned v)
{ p[o] = (uint8_t)v; p[o + 1] = (uint8_t)(v >> 8); }

static void rput32(uint8_t *p, unsigned o, uint32_t v)
{ rput16(p, o, (unsigned)v); rput16(p, o + 2, (unsigned)(v >> 16)); }

static int rs16(unsigned v)
{ v &= 0xFFFFu; return (v & 0x8000u) ? (int)v - 0x10000 : (int)v; }

/* simple_drum_control.smooth_control: (3*target + 5*old) >> 3, 32-bit wrap. */
static uint32_t rc_smooth_control(uint32_t old, uint32_t target)
{ return ((3u * target + 5u * old) & 0xFFFFFFFFu) >> 3; }

/* karplus_control_update.note_offset: the caller's twelve-entry table. */
static int rc_note_offset(unsigned note, const uint16_t *chromatic)
{
    const unsigned n = (note & 0xFFu) + 3u;
    const unsigned octave = n / 12u, step = n % 12u;
    return rs16((unsigned)chromatic[step] + (octave << 9));
}

/* simple_drum_control._time_parameter -- the ARM's own sequence, including the
 * `subs #1 / ubfx / subs #0x7f / uxth` tail, which is why the result is masked
 * to 16 bits at each step rather than computed as a plain formula. */
static unsigned rc_time_parameter(unsigned prepared)
{
    const unsigned q = 0x7FFFu + ((prepared & 0xFFFFu) << 2);
    const unsigned mantissa = (q & 0x0FFFu) + 0x1000u;
    const unsigned exponent = (q >> 12) & 0x0Fu;
    unsigned value = (exponent > 11u)
        ? (unsigned)((mantissa << (exponent - 12u)) & 0xFFFFu)
        : (unsigned)((mantissa >> (12u - exponent)) & 0xFFFFu);
    value = (value - 1u) & 0xFFFFFFFFu;
    value = (value >> 1) & 0x7FFFu;
    return (value - 0x7Fu) & 0xFFFFu;
}

/* karplus_control_update._envelope_rate. MUL keeps only the low 32 bits before
 * LSR #12, and a zero denominator returns zero (the capture runtime has divide
 * traps disabled). */
static unsigned rc_envelope_rate(const uint8_t *raw, unsigned offset,
                                 unsigned parameter, int decay)
{
    const unsigned config = offset + (decay ? 0x1Cu : 0x18u);
    const uint32_t product =
        (48u * (uint32_t)(ru16(raw, config + 2) - 1u) * parameter) & 0xFFFFFFFFu;
    const uint32_t denominator =
        (48u * (uint32_t)(ru16(raw, config) + 1u) + (product >> 12)) & 0xFFFFFFFFu;
    return denominator == 0u ? 0u : (unsigned)(0xFFFFFu / denominator);
}

/* resonant_control_update._pitch_helper, 0x0802844C. */
static int rc_pitch_helper(unsigned index)
{
    const unsigned i = index < 0xFFFu ? index : 0xFFFu;
    return rs16((i * 3u + 0x800u) & 0xFFFFu);
}

/* karplus_control_update.common_update. `pitch` is not a parameter: its only
 * consumer writes object 0x34, which from_arm never reads. */
static void rc_common_update(uint8_t *raw, const uint32_t targets[4],
                             const uint16_t *chromatic)
{
    uint32_t prepared[4];
    unsigned i;
    unsigned tune, decay, p1, p2;
    int index;

    for (i = 0; i < 4u; ++i) {
        prepared[i] = rc_smooth_control(r32(raw, 0x1Cu + 4u * i), targets[i]);
        rput32(raw, 0x1Cu + 4u * i, prepared[i]);
    }
    tune = prepared[0] & 0xFFFFu;
    decay = prepared[1] & 0xFFFFu;
    p1 = prepared[2] & 0xFFFFu;
    p2 = prepared[3] & 0xFFFFu;

    index = rs16((int)tune - 0x800 + rc_note_offset(raw[7], chromatic));
    if (index < 0) index = 0;
    if (index > 4095) index = 4095;

    rput16(raw, 0xBA, (unsigned)index);
    rput16(raw, 0xBC, decay);
    rput16(raw, 0xBE, p1);
    rput16(raw, 0xC0, p2);
    /* 0x34 would hold pitch_at(index); deliberately left alone -- see above. */
    raw[0x7B] = (uint8_t)(ru16(raw, 8) <= decay ? 1 : 0);
    rput16(raw, 0x94, rc_envelope_rate(raw, 0x74,
                                       rc_time_parameter(ru16(raw, 0x0A)), 0));
    rput16(raw, 0x96, rc_envelope_rate(raw, 0x74,
                                       rc_time_parameter(decay), 1));
}

/* resonant_control_update.update_bass. */
void pk_cf_res_update_bass(uint8_t *b, const uint32_t targets[4],
                           const uint16_t *chromatic)
{
    unsigned obj8, decay, p1, p2;
    int32_t r1, r3;
    uint32_t r2;
    unsigned index;

    rc_common_update(b, targets, chromatic);
    obj8 = ru16(b, 8);
    decay = ru16(b, 0xBC);
    p1 = ru16(b, 0xBE);
    p2 = ru16(b, 0xC0);
    b[0xD8] = (uint8_t)(decay > obj8 ? 1u : 0u);        /* TONE.bypass */
    r2 = 0;
    if (decay > obj8) {
        r2 = (uint32_t)((p1 << 4) & 0xFFFFu);
        /* b[0xC4] untouched in this branch */
    } else {
        r1 = (int32_t)((0xFFFu - decay) & 0xFFFFFFFFu);
        b[0xC4] = 1;                                     /* TONE.resonator dirty */
        rput32(b, 0x144, (uint32_t)((decay >> 10) + 0xFFCu));
        r3 = (int32_t)(((uint32_t)r1 * (uint32_t)r1) & 0xFFFFFFFFu);
        r3 = (int32_t)((uint32_t)r3 >> 8);
        r3 = (int32_t)(((uint32_t)r1 * (uint32_t)r3) & 0xFFFFFFFFu);
        r3 = (int32_t)((uint32_t)r3 >> 14);
        r3 = (int32_t)((0x7F80u - (uint32_t)r3) & 0xFFFFFFFFu);
        rput16(b, 0xC8, (unsigned)r3);                   /* TONE.pitch_b */
        r2 = 0;
    }
    rput16(b, 0x154, r2);                                /* DECAY_LEVEL.min */
    index = ru16(b, 0xBA);
    r1 = b[0x158];                                       /* NOISE.resonator dirty */
    r3 = (int32_t)(((uint32_t)index * 7u) >> 3);
    r3 &= 0xFFFF;
    rput16(b, 0xF0, (unsigned)((uint32_t)r3 + 0xC00u));  /* pitch */
    r3 = rs16((unsigned)((uint32_t)r3 + 0x2400u));
    if (r1 == 0) {
        r1 = (rs16(ru16(b, 0x15A)) - r3) != 0 ? 1 : 0;
    }
    rput16(b, 0x15A, (unsigned)r3);                      /* NOISE.pitch_a */
    r3 = (int32_t)(((uint32_t)p2 * (uint32_t)p2) >> 8);
    r3 &= 0xFFFF;
    rput16(b, 0x17C, p1);
    rput32(b, 0xEC, 0xC1E8u);
    b[0x158] = (uint8_t)(r1 ? 1u : 0u);
    r3 = (int32_t)(((uint32_t)r3 * (uint32_t)r3) & 0xFFFFFFFFu);
    rput32(b, 0xCC, (uint32_t)r3 >> 24);
}

/* resonator_compact.copy_env_to_arm's trigger, i.e. fold_control_update._env_trigger. */
static void rc_env_trigger(uint8_t *b, unsigned base)
{
    b[base + 0x10] = 1;
    b[base] = 1;
    if (b[base + 8])
        rput32(b, base + 0x0C, 0);
}

void pk_cf_res_trigger_bass(uint8_t *b, unsigned velocity, unsigned note)
{
    unsigned v = velocity < 1u ? 1u : (velocity > 255u ? 255u : velocity);
    b[6] = (uint8_t)v;
    if (note) b[7] = (uint8_t)(note > 127u ? 127u : note);
    rc_env_trigger(b, 0x74);
    rput32(b, 0x11C, 0xFFFFCA3Du);
    rput32(b, 0x104, 0x00043333u);
    rput32(b, 0x12C, (r32(b, 0x124) + 1u) & 0xFFFFFFFFu);
    rput32(b, 0xFC, (r32(b, 0xF4) + 1u) & 0xFFFFFFFFu);
    rput32(b, 0x114, (r32(b, 0x10C) + 1u) & 0xFFFFFFFFu);
    rput32(b, 0x150, (uint32_t)(((unsigned)ru16(b, 0x17C) << 4) & 0xFFFFu));
    rput32(b, 0x134, 0x4650u);
    rput32(b, 0x148, (r32(b, 0x140) + 1u) & 0xFFFFFFFFu);
}

/* resonant_control_update.update_snare. Its `dirty` idiom is not a typo: the
 * existing dirty bit is KEPT, and only recomputed when it was clear -- the
 * resonator re-reads its pitch when either the pitch moved or it was already
 * dirty. */
void pk_cf_res_update_snare(uint8_t *b, const uint32_t targets[4],
                            const uint16_t *chromatic)
{
    unsigned obj8, decay, p1, p2, v;
    int r0, r3;
    unsigned dirty;

    rc_common_update(b, targets, chromatic);
    obj8 = ru16(b, 8);
    decay = ru16(b, 0xBC);
    p1 = ru16(b, 0xBE);
    p2 = ru16(b, 0xC0);
    v = decay > obj8 ? 1u : 0u;
    b[0x10C] = (uint8_t)v;                               /* RES1.bypass */
    b[0x130] = (uint8_t)v;                               /* RES2.bypass */
    if (decay > obj8) {
        rput32(b, 0x1CC, (uint32_t)((p2 << 4) & 0xFFFFu));   /* DECAY_D.min */
    } else {
        b[0xF8] = 1;                                          /* RES1.dirty */
        rput16(b, 0xFC, 0x6FFFu + decay);                     /* RES1.pitch_b */
        rput16(b, 0x120, 0x6784u + decay);                    /* RES2.pitch_b */
        b[0x11C] = 1;                                         /* RES2.dirty */
        rput32(b, 0x1BC, (uint32_t)((decay >> 10) + 0xFFCu)); /* DECAY_D.mul */
    }
    r0 = rc_pitch_helper(ru16(b, 0xBA));
    dirty = b[0xF8];
    if (dirty == 0u)
        dirty = (rs16(ru16(b, 0xFA)) - r0) != 0 ? 1u : 0u;
    /* BOTH SPACINGS COME OFF THE SAME `r3`. The reference computes
     * `r2 = _s16(r3 + 0x600)` and then `r3 = _s16(r3 + 0x1800)` -- the second
     * from the ORIGINAL, not from r2. Writing it as two successive mutations of
     * one variable gives r3 + 0x1E00 instead, which is wrong by exactly 0x600
     * and shows up in RES3.pitch_a's high byte. Found by this gate. */
    /* `r3` stays UNSIGNED here, exactly as the reference has it: it is
     * `r0 & MASK16` and only becomes signed inside `_s16`, separately, for each
     * of the two spacings. Sign-extending it up front shifts both by the sign
     * bit, which is the same class of mistake as mutating it. */
    r3 = r0 & 0xFFFF;
    b[0xF8] = (uint8_t)dirty;
    rput16(b, 0xFA, (unsigned)r3);
    {
        const int r2 = rs16((unsigned)((uint32_t)r3 + 0x600u));
        dirty = b[0x11C];
        if (dirty == 0u)
            dirty = (rs16(ru16(b, 0x11E)) - r2) != 0 ? 1u : 0u;
        b[0x11C] = (uint8_t)dirty;
        rput16(b, 0x11E, (unsigned)r2);
    }
    r3 = rs16((unsigned)((uint32_t)r3 + 0x1800u));
    dirty = b[0x140];
    if (dirty == 0u)
        dirty = (rs16(ru16(b, 0x142)) - r3) != 0 ? 1u : 0u;
    b[0x140] = (uint8_t)dirty;
    rput16(b, 0x142, (unsigned)r3);
    rput32(b, 0x164, (uint32_t)((0x55F0u - (p1 << 2)) & 0xFFFFFFFFu)); /* MIX_FIRST */
    rput32(b, 0x168, (uint32_t)((0x55F0u + (p1 << 2)) & 0xFFFFFFFFu)); /* MIX_SECOND */
    rput16(b, 0x16C, p2);
}

void pk_cf_res_trigger_snare(uint8_t *b, unsigned velocity, unsigned note)
{
    unsigned v = velocity < 1u ? 1u : (velocity > 255u ? 255u : velocity);
    b[6] = (uint8_t)v;
    if (note) b[7] = (uint8_t)(note > 127u ? 127u : note);
    rc_env_trigger(b, 0x74);
    rput32(b, 0x198, 0xFFFF8000u);
    rput32(b, 0x180, 0x00078000u);
    rput32(b, 0x178, (r32(b, 0x170) + 1u) & 0xFFFFFFFFu);
    rput32(b, 0x190, (r32(b, 0x188) + 1u) & 0xFFFFFFFFu);
    rput32(b, 0x1A8, (r32(b, 0x1A0) + 1u) & 0xFFFFFFFFu);
    rput32(b, 0x1C0, (r32(b, 0x1B8) + 1u) & 0xFFFFFFFFu);
    rput32(b, 0x1B0, 0x3333u);
    rput32(b, 0x1C8, (uint32_t)((rs16(ru16(b, 0x16C)) << 4) & 0xFFFFFFFFu));
}
