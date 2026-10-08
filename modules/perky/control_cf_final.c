/* Final Perky Machines ColdFire source-machine integration.
 *
 * Locked SRC page:
 *   A DECAY / B TUNE / C PARAM1 / D PARAM2 / E MODE / F ALGO
 *
 * Four independent voices live on OT tracks 1,2,5,6 (zero-based 0,1,4,5).
 * The native PĒRKONS renderers run on ColdFire and publish ordinary stock
 * unity-rate source segments.  No DSP synth hook, DSP code replacement, FX
 * memory claim, or FX dispatch change is used by this final architecture.
 */
#define pk_defaults pk_defaults_cf_legacy
#define pk_admit_track pk_admit_track_cf_legacy
#define page_for page_for_cf_legacy
#define pk_track_page pk_track_page_cf_legacy
#define pk_ui_tick pk_ui_tick_cf_legacy
#define pk_render pk_render_cf_legacy
#define pk_engine_select pk_engine_select_cf_legacy
#define pk_engine_draw pk_engine_draw_cf_legacy
#define pk_engine_open pk_engine_open_cf_legacy
#define pk_engine_left pk_engine_left_cf_legacy
#define pk_engine_right pk_engine_right_cf_legacy
#include "control.c"
#undef pk_engine_right
#undef pk_engine_left
#undef pk_engine_open
#undef pk_engine_draw
#undef pk_engine_select
#undef pk_render
#undef pk_ui_tick
#undef pk_track_page
#undef page_for
#undef pk_admit_track
#undef pk_defaults
#include "cf_perky4.h"
#define PK_FINAL_DECAY 0u
#define PK_FINAL_TUNE 1u
#define PK_FINAL_PARAM1 2u
#define PK_FINAL_PARAM2 3u
#define PK_FINAL_MODE 4u
#define PK_FINAL_ALGO 5u
#define PK_FINAL_ALGO_COUNT 4u
#define PK_FINAL_NOTE 45u
#define PK_FINAL_VELOCITY 255u
#define PK_FINAL_BLOCK_SAMPLES 16u
extern const uint8_t pk_asset_pitch[];
extern const uint8_t pk_asset_chromatic[];
extern const uint8_t pk_asset_envelope1[];
extern const uint8_t pk_asset_envelope2[];
extern const uint8_t pk_asset_m1_wave[];
extern const uint8_t pk_asset_wave0[];
extern const uint8_t pk_asset_wave1[];
extern const uint8_t pk_asset_wave2[];
extern const uint8_t pk_asset_wave3[];
const uint8_t pk_defaults[12] = {64,64,64,64,0,0,0,0,0,0,0,0};
static pk4_engine pk_final_engine;
static uint32_t pk_final_bank;
static uint8_t pk_final_part;
static uint8_t pk_final_engine_ready;
static const pk4_assets pk_final_assets = {.pitch=pk_asset_pitch,.chromatic=pk_asset_chromatic,.envelope1=pk_asset_envelope1,.envelope2=pk_asset_envelope2,.waves={{0x080222a0u,pk_asset_wave0},{0x080224a0u,pk_asset_wave1},{0x080226a0u,pk_asset_wave2},{0x080228a0u,pk_asset_wave3}},.m1_wave=pk_asset_m1_wave,.m1_wave_address=0x080310e0u};
static int pk_final_voice_index(unsigned track){switch(track){case 0u:return 0;case 1u:return 1;case 4u:return 2;case 5u:return 3;default:return -1;}}
static void pk_final_reset_runtime_if_needed(void){const uint32_t bank=U32(BANK);const uint8_t part=U8(PART_IDX)&3u;if(!pk_final_engine_ready||pk_final_bank!=bank||pk_final_part!=part){pk4_init(&pk_final_engine,&pk_final_assets);pk_final_bank=bank;pk_final_part=part;pk_final_engine_ready=1u;}}
static uint32_t pk_final_page(void){static const char *const names[6]={"DECAY","TUNE","PAR1","PAR2","MODE","ALGO"};(void)page_for_cf_legacy(DEFAULT_ENGINE);text(desc+0x41,"PERKY MACH",13);for(unsigned i=0;i<6u;++i){text(desc+0x4e+6u*i,names[i],6);desc[0x96+i]=pk_defaults[i];put32(desc+0xa2+4u*i,0);put32(desc+0xd2+4u*i,i<PK_FINAL_MODE?128u:(i==PK_FINAL_MODE?3u:PK_FINAL_ALGO_COUNT));put32(desc+0x102+4u*i,i>=PK_FINAL_MODE?MODE_FORMATTER:0);put32(desc+0x132+4u*i,i==PK_FINAL_MODE?MODE_WIDGET:0);put32(desc+0x162+4u*i,0);}put32(desc+0x1c2,0);put32(desc+0x1c6,0x00111111u);pk_desc_p=(uint32_t)(uintptr_t)(desc+0x38);return pk_desc_p;}
unsigned pk_admit_track(const volatile uint8_t *part,unsigned track){(void)part;return pk_final_voice_index(track)>=0;}
uint32_t pk_track_page(const volatile uint8_t *type_ptr){(void)type_ptr;return pk_final_page();}
void pk_ui_tick(void){U32(0x400d5f38u+PERKY_ROW*4u)=pk_final_page();}
int pk_render(unsigned track,unsigned ping,unsigned start,unsigned end){volatile uint32_t*cursor;volatile uint16_t*fp;uint8_t src[6];int16_t pcm[PK_FINAL_BLOCK_SAMPLES];uint32_t record[4u+2u*PK_FINAL_BLOCK_SAMPLES];uint32_t longs;unsigned count;int voice;int trig;int event_boundary;(void)ping;voice=pk_final_voice_index(track);if(track>=8u||voice<0||!signed_track(part_base(),track))return((int(*)(unsigned,unsigned,unsigned,unsigned))0x40004008u)(track,ping,start,end);if(end<start||end>PK_FINAL_BLOCK_SAMPLES)return 0;count=end-start;cursor=(volatile uint32_t*)(uintptr_t)U32(0x80001c80u);event_boundary=end==PK_FINAL_BLOCK_SAMPLES;if(event_boundary){fp=(volatile uint16_t*)(uintptr_t)U32(0x800062a8u);for(unsigned i=0;i<6u;++i)src[i]=(uint8_t)(fp[i]>>8);if(src[PK_FINAL_MODE]>2u)src[PK_FINAL_MODE]=2u;if(src[PK_FINAL_ALGO]>=PK_FINAL_ALGO_COUNT)src[PK_FINAL_ALGO]=0u;}pk_final_reset_runtime_if_needed();trig=(U8(0x46104d0cu+track)&16u)!=0u;if(!pk4_process_segment(&pk_final_engine,(unsigned)voice,event_boundary?src:(const uint8_t*)0,event_boundary,trig,PK_FINAL_VELOCITY,PK_FINAL_NOTE,pcm,count)){for(unsigned i=0;i<count;++i)pcm[i]=0;}longs=pk4_encode_stock_segment(record,pcm,count);if(!longs)return 0;for(uint32_t i=0;i<longs;++i)cursor[i]=record[i];U32(0x80001c80u)=(uint32_t)(uintptr_t)(cursor+longs);++pk_render_calls;if(trig&&event_boundary)++pk_hits;return 0;}
static uint32_t pk_final_engine_bank;static unsigned pk_final_engine_part;static unsigned pk_final_engine_track;static const char *const pk_final_engine_labels[]={"001 FOLD 1","002 FOLD 2","003 KARPLUS","004 NOISE/TONE"};
void pk_engine_select(unsigned algo){unsigned offset;if(algo>=PK_FINAL_ALGO_COUNT||U32(BANK)!=pk_final_engine_bank||(U8(PART_IDX)&3u)!=pk_final_engine_part||U8(0x100b14ccu)!=pk_final_engine_track||!pk_selected_source())return;offset=source_offset(pk_final_engine_track,PK_FINAL_ALGO);part_base()[offset]=(uint8_t)algo;U8(0x100a4eceu+PART_STRIDE*pk_final_engine_part+offset)=(uint8_t)algo;U8(pk_final_engine_bank+0x95048u)|=(uint8_t)(1u<<pk_final_engine_part);U8(0x100b145eu)|=(uint8_t)(1u<<pk_final_engine_part);U32(pk_final_engine_bank+0x9b332u)=1u;U32(0x100f8598u)=1u;((void(*)(void))0x40027e00u)();pk_ui_tick();((void(*)(void))0x4004d948u)();}
static void pk_final_algo0(void){pk_engine_select(0u);}static void pk_final_algo1(void){pk_engine_select(1u);}static void pk_final_algo2(void){pk_engine_select(2u);}static void pk_final_algo3(void){pk_engine_select(3u);}
unsigned pk_engine_draw(void){const uint32_t window=U32(0x460e5e30u);if(!window||U32(0x460e5e2cu)!=(uint32_t)(uintptr_t)pk_final_engine_labels)return 0u;void*surface=(void*)(uintptr_t)(window+0x24u);((void(*)(void*))0x4003567cu)(surface);const int height=(int)U32(window+0x28u);for(unsigned row=0;row<PK_FINAL_ALGO_COUNT;++row){const int y=height-23-7*(int)row;((void(*)(uint32_t,void*,int,int,int,const char*))0x40012bd8u)(0x400ba876u,surface,5,y,-1,pk_final_engine_labels[row]);if(row==U32(0x460e5e40u))((void(*)(void*,int,int,int,int,int))0x40012254u)(surface,3,y-1,(int)U32(window+0x24u)-5,y+5,-1);}U32(0x46c7c72cu)=1u;return 1u;}
void pk_engine_open(void){static void(*const handlers[])(void)={pk_final_algo0,pk_final_algo1,pk_final_algo2,pk_final_algo3};if(!pk_selected_source()||U32(0x460e5e30u))return;pk_final_engine_bank=U32(BANK);pk_final_engine_part=U8(PART_IDX)&3u;pk_final_engine_track=U8(0x100b14ccu);((void(*)(uint32_t,unsigned,unsigned))0x4007ec60u)(0x460e5e38u,6u,PK_FINAL_ALGO_COUNT);((void(*)(uint32_t,unsigned))0x4007edb0u)(0x460e5e38u,part_base()[source_offset(pk_final_engine_track,PK_FINAL_ALGO)]%PK_FINAL_ALGO_COUNT);U32(0x460e5e28u)=(uint32_t)(uintptr_t)handlers;U32(0x460e5e2cu)=(uint32_t)(uintptr_t)pk_final_engine_labels;U32(0x460e5e34u)=0u;{const uint32_t window=((uint32_t(*)(int,int,int,int,int,uint32_t))0x4005829cu)(110,64,-1,0,1,0x4006d754u);U32(0x460e5e30u)=window;if(!window)return;((void(*)(uint32_t,const char*,unsigned))0x400570b8u)(window,"\xab MACHINE:PERKY",0u);((void(*)(uint32_t))0x40031494u)(0x400ce0c4u);pk_engine_draw();}}
void pk_engine_left(void){if(!U32(0x460e5e30u)||U32(0x460e5e2cu)!=(uint32_t)(uintptr_t)pk_final_engine_labels)return;((void(*)(void))0x4006d754u)();pk_stock_pool_open();((void(*)(void))0x4007893cu)();}
void pk_engine_right(unsigned key,unsigned value){if(U32(0x460e70e0u)&&!U32(0x460e739au)&&U32(0x460e738eu)==PERKY_ROW&&pk_selected_source()){((void(*)(void))0x400789e4u)();pk_engine_open();return;}((void(*)(unsigned,unsigned))0x4007909cu)(key,value);}
