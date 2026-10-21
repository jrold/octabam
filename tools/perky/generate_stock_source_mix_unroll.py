"""Guarded unroll of the stock ISR's six/nine packed-source mixer bodies.

Load the author's instruction bodies from the user's stock image at build time.
All source/destination loads, stores and EMAC operations retain their order.
Only repeated loop-counter updates are removed for the two fixed stock counts.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = 0x40000400
SITE = dict(name='stock_source_mix', address=0x4000cc02, end=0x4000cc0e,
            continuation=0x4000cc26,
            sha256='5df8976ec96e668af92b4d900df2f337e40bbf2c38368976dc9c30b076bbba72')
BODY_END = 0x4000cc22
BODY_SHA256 = 'af1c05a91c7961d17f06626f81201837484edc0c40c5d96e49febb4380e3d6a4'


def expected_span(site=SITE):
    blob = (ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    body = blob[site['address']-BASE:BODY_END-BASE]
    assert hashlib.sha256(body).hexdigest() == BODY_SHA256, 'stock source mixer body drift'
    data = blob[site['address']-BASE:site['end']-BASE]
    assert hashlib.sha256(data).hexdigest() == site['sha256'], 'stock source mixer entry drift'
    return data


def generate(work):
    expected_span()
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    path = work/'stock-source-mix-unroll.s'
    stock = str(ROOT/'out/raw/section_3_MAIN_OS.bin')
    # Each body has only register, address-indirect and postincrement operands.
    # Its parallel MAC masked-load extension is retained verbatim.
    body = f' .incbin "{stock}",{SITE["address"]-BASE},{BODY_END-SITE["address"]}\n'
    text = '''/* Exact guarded6/9-body stock source mixer. No stack or scratch use. */
.text
.balign 2
.globl pk_stock_source_mix_unroll
.type pk_stock_source_mix_unroll,@function
pk_stock_source_mix_unroll:
 cmp.l #6,%d1
 beq .Lsource_six
 cmp.l #9,%d1
 bne pk_stock_source_mix_fallback_body
'''
    text += body * 9
    text += ''' sub.l #9,%d1
 jmp 0x4000cc26
.Lsource_six:
'''
    text += body * 6
    text += ''' subq.l #6,%d1
 jmp 0x4000cc26
.globl pk_stock_source_mix_fallback_body
pk_stock_source_mix_fallback_body:
'''
    text += body
    text += ''' subq.l #1,%d1
 bne pk_stock_source_mix_fallback_body
 jmp 0x4000cc26
.size pk_stock_source_mix_unroll,.-pk_stock_source_mix_unroll
'''
    path.write_text(text)
    return dict(path=str(path), sites=[dict(SITE, entry='pk_stock_source_mix_unroll', pad_to=12)],
                guard='d1==6 or d1==9', fallback='Byte-identical stock body and original counter recurrence',
                preserved='Source/destination access order, all registers, full CCR, raw EMAC; no stack use')
