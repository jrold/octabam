#include "cf_pcm_rice.h"
volatile uint32_t decode_status;
uint32_t packed_bytes;
void bench_decode(void){const pk_cf_rice_target targets[2]={{2048,(int16_t*)0x45100000u},{98304,(int16_t*)0x45101000u}};decode_status=(uint32_t)pk_cf_rice_unpack_le((const uint8_t*)0x45000000u,packed_bytes,targets,2);}
