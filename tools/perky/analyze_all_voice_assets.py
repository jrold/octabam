#!/usr/bin/env python3
"""Measure lossless random-access asset footprints from original ARM captures.

No extracted firmware assets are committed. This reports storage only, not
DSP decoder timing or a shipping memory allocation.
"""
from pathlib import Path
import argparse,hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[2]
from extract_noise_tone_tables import parse_container,find_m7

def pack_signed_blocks(samples,block=128):
    """One 24-bit descriptor/block: 19-bit word offset and 5-bit signed width.

    Each block starts on a word boundary; individual signed samples can be
    read with two adjacent 24-bit reads, without decoding preceding samples.
    """
    descriptors=[];words=[]
    for at in range(0,len(samples),block):
        values=samples[at:at+block]
        width=max(1,max((v if v>=0 else ~v).bit_length()+1 for v in values))
        assert width<=16 and len(words)<1<<19
        descriptors.append((width<<19)|len(words))
        bits=0;count=0
        for value in values:
            bits|=(value&((1<<width)-1))<<count;count+=width
            while count>=24:words.append(bits&0xffffff);bits>>=24;count-=24
        if count:words.append(bits)
    words.append(0) # final adjacent read guard
    for i,expected in enumerate(samples):
        descriptor=descriptors[i//block];width=descriptor>>19;offset=descriptor&((1<<19)-1)
        bit=(i%block)*width;word=offset+bit//24;shift=bit%24
        value=((words[word]|words[word+1]<<24)>>shift)&((1<<width)-1)
        if value&(1<<(width-1)):value-=1<<width
        assert value==expected,(i,value,expected)
    return descriptors,words

def pack_delta_blocks(samples,block=64):
    """One indexed signed anchor plus fixed-width first differences/block.

    Cache decoding is bounded to 64 samples. Final blocks are padded to make
    that bound independent of asset length. Storage fit is not a timing gate.
    """
    descriptors=[];words=[]
    for at in range(0,len(samples),block):
        values=list(samples[at:at+block]);values += [0]*(block-len(values))
        deltas=[values[i]-values[i-1] for i in range(1,block)]
        width=max(1,max((v if v>=0 else ~v).bit_length()+1 for v in deltas))
        assert width<=17 and len(words)<1<<19
        descriptors.append((width<<19)|len(words))
        bits=values[0]&65535;count=16
        for value in deltas:
            bits|=(value&((1<<width)-1))<<count;count+=width
            while count>=24:words.append(bits&0xffffff);bits>>=24;count-=24
        if count:words.append(bits)
    words.append(0)
    decoded=[]
    for descriptor in descriptors:
        width=descriptor>>19;offset=descriptor&((1<<19)-1);cursor=0
        def read(n):
            nonlocal cursor
            word=offset+cursor//24;shift=cursor%24
            result=((words[word]|words[word+1]<<24)>>shift)&((1<<n)-1);cursor+=n
            return result-(1<<n) if result&(1<<(n-1)) else result
        value=read(16);decoded.append(value)
        for _ in range(block-1):value+=read(width);decoded.append(value)
    assert tuple(decoded[:len(samples)])==tuple(samples)
    return descriptors,words

def analyze(image,fixtures,out):
    segment=find_m7(parse_container(image.read_bytes())[1]);assets={}
    # Complete 3x16 SURF pointer list read by update() at 0x080271c4.
    # Corner snapshots alone miss the intermediate tables selected by SURF.
    for address in struct.unpack('<48I',segment.read(0x080326d4,48*4)):
        assets[address]=(2048,'wavetable-surf-bank')
    for mode in range(1,4):
        raw=(fixtures/f'engine-12-mode-{mode}-corner-1/wrapper-window-before.bin').read_bytes()
        address,length=struct.unpack_from('<II',raw,0x2a80+0xf8)
        assets[address]=(length,f'acoustic-mode-{mode}')
        for engine in (2,5):
            for corner in range(3):
                raw=(fixtures/f'engine-{engine}-mode-{mode}-corner-{corner}/wrapper-window-before.bin').read_bytes()
                for offset in (0x100,0x104,0x108,0x10c):
                    address=struct.unpack_from('<I',raw,(0x2e8 if engine==2 else 0x31c)+offset)[0]
                    assets[address]=(2048,f'wavetable-{engine}-mode-{mode}-corner-{corner}')
    result=[];out.mkdir(parents=True,exist_ok=True)
    for address,(length,role) in sorted(assets.items()):
        raw=segment.read(address,2*length);values=struct.unpack(f'<{length}h',raw)
        descriptors,words=pack_signed_blocks(values)
        delta_descriptors,delta_words=pack_delta_blocks(values)
        packed=b''.join(v.to_bytes(3,'little') for v in descriptors+words)
        path=out/f'asset_{address:08x}.bin';path.write_bytes(raw)
        (out/f'asset_{address:08x}.packed.bin').write_bytes(packed)
        delta=b''.join(v.to_bytes(3,'little') for v in delta_descriptors+delta_words)
        (out/f'asset_{address:08x}.delta64.bin').write_bytes(delta)
        result.append({'address':hex(address),'role':role,'samples':length,'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'direct_words':(length*16+23)//24,'block_words':len(descriptors)+len(words),'delta64_words':len(delta_descriptors)+len(delta_words),'delta64_sha256':hashlib.sha256(delta).hexdigest(),'blocks':len(descriptors),'packed_sha256':hashlib.sha256(packed).hexdigest()})
    report={'firmware_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'schema':'perky-all-voice-asset-storage-v1','codec':'signed-width128; indexed adjacent24; exact host round-trip; DSP timing unqualified','assets':result,'totals':{'raw_bytes':sum(v['raw_bytes'] for v in result),'direct_words':sum(v['direct_words'] for v in result),'block_words':sum(v['block_words'] for v in result)}}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    for value in result:print(f'{value["role"]}: {value["samples"]} samples, direct {value["direct_words"]} words, indexed lossless {value["block_words"]} words, delta64 {value["delta64_words"]} words')
    print('TOTAL',report['totals'])
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('image',type=Path);ap.add_argument('--fixtures',type=Path,default=ROOT/'out/perky/engine-fixtures');ap.add_argument('--out',type=Path,default=ROOT/'out/perky/all-voice-assets');a=ap.parse_args();analyze(a.image,a.fixtures,a.out)
