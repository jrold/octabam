/* Exact compression of the ORIGINAL boot-time pristine bytes. No synthesis
 * invariants or hardcoded initializer values are assumed. Dense initializers
 * fall back to the full copy. All patches cover complete in-bounds words. */
#define PK_PROD_SPARSE_MAX 96u
typedef struct {uint32_t offset,value;} pk_prod_patch;
typedef struct {unsigned count;pk_prod_patch patch[PK_PROD_SPARSE_MAX];} pk_prod_sparse;
static pk_prod_sparse pk_prod_sparse_slap[4],pk_prod_sparse_hat[4];
extern void pk_prod_zero_patch(void*,unsigned,const pk_prod_patch*,unsigned);
static void prod_sparse_build(pk_prod_sparse*d,const void*src,unsigned n)
{
 typedef uint32_t __attribute__((may_alias)) word;
 const word*p=src;d->count=0;
 for(unsigned i=0;i<n/4;i++)if(p[i]){
  if(d->count==PK_PROD_SPARSE_MAX){d->count=PK_PROD_SPARSE_MAX+1;return;}
  pk_prod_patch*q=&d->patch[d->count++];q->offset=4*i;q->value=p[i];
 }
}
__attribute__((noinline)) void pk_prod_sparse_restore(void*dst,const void*src,unsigned n,const pk_prod_sparse*d)
{
 if(d->count>PK_PROD_SPARSE_MAX){pk_prod_copy(dst,src,n);return;}
 pk_prod_zero_patch(dst,n,d->patch,d->count);
 uint8_t*out=dst;const uint8_t*in=src;
 for(unsigned i=n&~3u;i<n;i++)out[i]=in[i];
}
