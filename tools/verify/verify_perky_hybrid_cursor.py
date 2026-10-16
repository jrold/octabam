#!/usr/bin/env python3
"""Compare callback-visible source RAM when cursor and fixed slot overlap."""
import argparse
import hashlib
import json
from pathlib import Path
import verify_perky_hybrid_runtime as runtime

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(work, reference):
    image=work/'probe/mainos_PKHYB2P.bin';elf=work/'probe/platform/runtime.elf'
    oldimage=reference/'mainos_PKHYB2P.bin';oldelf=reference/'platform/runtime.elf'
    inputs={str(p):sha(p) for p in (image,elf,oldimage,oldelf,Path(__file__),
        Path(runtime.__file__),Path(runtime.g.__file__))}
    current,ns=runtime.machine(image,elf,True)
    original,os=runtime.machine(oldimage,oldelf)
    machines=((current.uc,ns),(original.uc,os))
    memory_hash=hashlib.sha256();state_hash=hashlib.sha256();calls=0
    n=runtime.sizes(elf)['pk_hybrid_voices']
    current_sizes, original_sizes = runtime.sizes(elf), runtime.sizes(oldelf)
    offsets=(-192,-128,-16,0,16,120,144,156,160,176,336)
    for split in range(17):
        for track in (1,5):
            for ping in (0,1):
                for offset in offsets:
                    fixed=0x80001c90+ping*0xa80+336*track
                    for u,symbols in machines:
                        vals=(43,101,2,27,93,0 if track==1 else 1)
                        for k,v in enumerate(vals):u.mem_write(0x80008000+2*k,(v<<8).to_bytes(2,'big'))
                        u.mem_write(0x46104d0c+track,b'\x10')
                    for start,end,actual_ping in ((0,split,ping^1),(split,16,ping)):
                        cursor=fixed+offset
                        actual_fixed=0x80001c90+actual_ping*0xa80+336*track
                        for u,symbols in machines:
                            u.mem_write(cursor,b'\xa5'*160)
                            u.mem_write(actual_fixed,b'\x5a'*336)
                            runtime.w32(u,0x80001c80,cursor)
                            runtime.g.emu._call(u,symbols['pk_render'],(track,actual_ping,start,end))
                        # Compare all source slots, reservation pointer, trailing
                        # words and neighboring RAM at each callback boundary.
                        now=bytes(current.uc.mem_read(0x80001c40,0x1900))
                        old=bytes(original.uc.mem_read(0x80001c40,0x1900))
                        assert now==old,('source RAM',split,track,ping,offset,start,end)
                        state=runtime.canonical_state(current.uc,ns,current_sizes)
                        assert state==runtime.canonical_state(original.uc,os,original_sizes),('state/RNG',calls)
                        assert current.uc.reg_read(runtime.g.emu.UC_M68K_REG_D0)==original.uc.reg_read(runtime.g.emu.UC_M68K_REG_D0)
                        memory_hash.update(now);state_hash.update(state);calls+=1
    assert inputs=={p:sha(Path(p)) for p in inputs},'input drift'
    report={'status':'PASS_EXACT_CALLBACK_MEMORY_STATE_RNG','callbacks':calls,
        'split_offsets':17,'tracks':[1,5],'pings':[0,1],'cursor_offsets_bytes':offsets,
        'compared_source_RAM_bytes_per_callback':0x1900,
        'source_memory_sha256':memory_hash.hexdigest(),'state_RNG_sha256':state_hash.hexdigest(),
        'inputs':inputs}
    (work/'CURSOR_EXACT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--reference',type=Path,default=runtime.ROOT/'out/perky/hybrid/private-stack/probe')
    a=ap.parse_args();run(a.work.resolve(),a.reference.resolve())
