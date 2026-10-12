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
