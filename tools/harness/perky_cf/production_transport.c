#include <sys/mman.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#define U8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define U16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define U32(a) (*(volatile uint32_t *)(uintptr_t)(a))
extern int pk_render(unsigned,unsigned,unsigned,unsigned);
void pk_stock_pool_open(void){abort();}
int pk_stock_validate(void *p){abort();}
int main(int argc,char **argv){
 for(unsigned i=0;i<3;i++){uintptr_t at=i==0?0x10000000u:i==1?0x46000000u:0x80000000u;unsigned size=i==0?0x200000u:i==1?0x4000000u:0x1000000u;void *p=mmap((void*)at,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON|MAP_FIXED,-1,0);if(p!=(void*)at){perror("mmap");return 2;}}
 U32(0x46c82456)=0x48000000;U8(0x100b14cf)=0;U32(0x800062a8)=0x80008000;
 for(unsigned t=0;t<8;t++){uintptr_t p=0x48000000u+0x8ed80u;U8(p+0x22+t)=1;U8(p+60+30*t)='P';U8(p+61+30*t)='K';U8(p+62+30*t)=1;}
 FILE *f=fopen(argv[1],"rb"),*g=fopen(argv[2],"wb");uint8_t row[14];unsigned n=0;
 while(fread(row,1,14,f)==14){unsigned t=row[12],trig=row[13],ping=n++&1u;for(unsigned k=0;k<6;k++)U16(0x80008000+2*k)=row[k]<<8;for(unsigned k=6;k<12;k++)U8(0x80000810+72*t+0x20+k-6)=row[k];U8(0x46104d0c+t)=trig?16:0;U32(0x80001c80)=0x80010000;assert(pk_render(t,ping,0,16)==0);volatile uint32_t *rec=(void*)(uintptr_t)(0x80001c90+ping*0xa80+336*t);assert(rec[0]==0x504b0000u);assert(rec[1]==(0x59310000u|trig));for(unsigned k=4;k<10;k++){fputc((rec[k]>>16)&255,g);fputc(rec[k]&255,g);}}
 fclose(f);fclose(g);return 0;
}
