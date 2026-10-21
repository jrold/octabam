#ifndef PK_FULL_MAP_CARD_ASSETS_H
#define PK_FULL_MAP_CARD_ASSETS_H
#include <stdint.h>
/* One immutable, versioned file. UI task only; one 4096-byte chunk per tick.
 * Audio reads the buffers only after the final CRC check publish OK.
 * The loaded NO cookie cannot be mistaken for readiness after poisoned BSS.
 */
extern uint8_t pk_placement_closed[],pk_placement_open[],pk_placement_ride[];
uint32_t fma_ready=0x41484e4fu;
int32_t fma_status=0;
static uint32_t fma_object[6],fma_iobuf[1024],fma_header[4];
static unsigned fma_asset,fma_offset,fma_crc,fma_retry;
static void fma_reset(void)
{fma_ready=0x41484e4fu;fma_status=0;fma_asset=fma_offset=fma_retry=0;fma_crc=0xffffffffu;}

static unsigned fma_crc_step(unsigned crc,const uint8_t*p,unsigned n)
{
 static const unsigned table[16]={0,0x1db71064,0x3b6e20c8,0x26d930ac,0x76dc4190,0x6b6b51f4,0x4db26158,0x5005713c,0xedb88320,0xf00f9344,0xd6d6a3e8,0xcb61b38c,0x9b64c2b0,0x86d3d2d4,0xa00ae278,0xbdbdf21c};
 while(n--){crc^=*p++;crc=(crc>>4)^table[crc&15];crc=(crc>>4)^table[crc&15];}
 return crc;
}
__attribute__((noinline)) void fma_tick(void)
{
 typedef int(*Open)(void*,const char*,const char*,void*,unsigned);
 typedef int(*Read)(void*,void*,unsigned);typedef int(*Close)(void*);
 Open open=(Open)0x40016864u;Read read=(Read)0x40016564u;Close close=(Close)0x4001677cu;
 static const unsigned sizes[]={20202,172800,259106};
 uint8_t*const targets[]={pk_placement_closed,pk_placement_open,pk_placement_ride};
 if(fma_ready==0x41484f4bu)return;
 if(!(*(volatile uint32_t*)0x46c8240eu))return;
 /* Never start card loading while transport is running. Once opened, finish
  * its bounded chunks; no file calls, waits or IRQ masking occur in audio. */
 if(fma_status!=1){
  if(*(volatile uint32_t*)0x800065b8u==1u)return;
  if(fma_retry){fma_retry--;return;}fma_retry=250;
  for(unsigned i=0;i<6;i++)fma_object[i]=0;
  if(open(fma_object,"/PERKYAH.DAT","r",fma_iobuf,sizeof(fma_iobuf))<0){fma_status=-1;return;}
  if(read(fma_object,fma_header,16)!=1||fma_header[0]!=0x504b4148u||fma_header[1]!=1||fma_header[2]!=452108||fma_header[3]!=FMA_EXPECTED_CRC){close(fma_object);fma_status=-2;return;}
  fma_asset=fma_offset=0;fma_crc=0xffffffffu;fma_status=1;
 }
 unsigned n=sizes[fma_asset]-fma_offset;if(n>4096)n=4096;
 uint8_t*dst=targets[fma_asset]+fma_offset;
 if(read(fma_object,dst,n)!=1){close(fma_object);fma_status=-3;return;}
 fma_crc=fma_crc_step(fma_crc,dst,n);fma_offset+=n;
 if(fma_offset==sizes[fma_asset]){fma_asset++;fma_offset=0;}
 if(fma_asset==3){
  int ended=close(fma_object);
  if((fma_crc^0xffffffffu)!=FMA_EXPECTED_CRC){fma_status=-4;return;}
  if(ended<0){fma_status=-5;return;}
  __asm__ volatile("":::"memory");fma_ready=0x41484f4bu;fma_status=2;
 }
}
#endif
