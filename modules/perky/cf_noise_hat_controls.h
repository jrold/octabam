/* Opt-in control settling optimization; include after the original nh_update.
 * nh_common_update feeds only its four smoothed words into the next pass.
 * The limb also feeds back P2 through +0x0a, one update behind the smoother.
 * Preserve that penultimate P2 before the surviving sixteenth derivation.
 * Keep that derivation BEFORE a trigger: it still uses the previous note.
 * The original trigger and seventeenth update then run in their old order.
 */
#ifndef PERKY_NOISE_HAT_CONTROLS_H
#define PERKY_NOISE_HAT_CONTROLS_H
uint32_t pk_nhf_enabled=1,pk_nhf_batches;
static void nh_settle_controls(uint8_t*s,unsigned fw,const uint32_t targets[4],const pk4_assets*a)
{
    size_t b=nh_limb(fw);
    common_smooth_many(s,targets,15);
    common_smooth_many(s+b,targets,15);
    w16(s,b+0x0a,(uint16_t)r32(s,b+0x28));
    nh_update(s,fw,targets,a);
    pk_nhf_batches++;
}
#endif
