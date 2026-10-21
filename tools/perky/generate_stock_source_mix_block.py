"""Exact fixed stock16-group mixer, retaining every original data operation."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=0x40000400
SITE=dict(name='stock_source_mix_block',address=0x4000cbfa,end=0x4000cc02,
          continuation=0x4000cc62,
          sha256='d286fa73df577957e2edd2fc9df1e957bdf224e5e3d0bc2ea9c89af06f684540')
BLOCK_SHA256='f50e53baf46b94381358b47323d80cf1784718496ad74296836f58f3bb4fb039'


def expected_span(site=SITE):
    data=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    block=data[site['address']-BASE:site['continuation']-BASE]
    assert hashlib.sha256(block).hexdigest()==BLOCK_SHA256,'stock fixed mixer block drift'
    span=data[site['address']-BASE:site['end']-BASE]
    assert hashlib.sha256(span).hexdigest()==site['sha256'],'stock fixed mixer entry drift'
    return span


def generate(work):
    expected_span();work=Path(work);work.mkdir(parents=True,exist_ok=True)
    stock=str(ROOT/'out/raw/section_3_MAIN_OS.bin')
    def include(a,e):return f' .incbin "{stock}",{a-BASE},{e-a}\n'
    body=include(0x4000cc02,0x4000cc22)
    text='''/* Original span sets16 groups and alternates6/9 fields. A paired
 * loop removes only counter/parity dispatch. All data/MAC operations retain
 * their original order, including aliased source/destination accesses. */
.text
.balign 2
.globl pk_stock_source_mix_block
.type pk_stock_source_mix_block,@function
pk_stock_source_mix_block:
 moveq #16,%d0
.Lmix_pair:
 movea.l %a4,%a1
 mvz.w (%a3)+,%d4
 moveq #6,%d1
'''
    text+=body*6
    text+=''' subq.l #6,%d1
 movea.l %a5,%a1
 moveq #9,%d1
'''
    text+=body*9
    text+=''' sub.l #9,%d1
 subq.l #2,%d0
 beq .Lmix_last
'''
    text+=include(0x4000cc36,0x4000cc50)
    text+=''' bra .Lmix_pair
.Lmix_last:
'''
    text+=include(0x4000cc52,0x4000cc62)
    text+=''' jmp 0x4000cc62
.size pk_stock_source_mix_block,.-pk_stock_source_mix_block
'''
    path=work/'stock-source-mix-block.s';path.write_text(text)
    return dict(path=str(path),sites=[dict(SITE,entry='pk_stock_source_mix_block',pad_to=8)],
                invariant='Stock span itself assigns16 groups and6/9 fields; no caller assumption or count guard',
                preserved='Every data access and MAC operation in order; all D/A registers, full CCR and raw EMAC')
