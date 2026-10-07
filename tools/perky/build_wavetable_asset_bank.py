#!/usr/bin/env python3
"""Build lossless Wavetable asset bank locally, without committing firmware data.

This emits an address-independent bank and a footprint report, not an updater.
Every sample is round-tripped. Physical memory and DSP timing are not qualified.
"""
from pathlib import Path
import argparse,hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'modules/perky'))
import wavetable_asset_codec as codec
IDS=(0x080222a0,*(0x080327cc+i*0x1000 for i in range(48)))

def build(source,out,block=32):
    out.mkdir(parents=True,exist_ok=True)
    assets=[];payload=[];directory=[]
    # Four-word directory entries: original pointer low/high, descriptor start,
    # packed data start. First-delta width sits immediately before descriptors.
    base=len(IDS)*4
    for address in IDS:
        raw=(source/f'asset_{address:08x}.bin').read_bytes()
        assert len(raw)==4096,(address,len(raw))
        asset=codec.pack(struct.unpack('<2048h',raw),block)
        start=base+len(payload)
        directory.extend((address&65535,address>>16,start+1,start+1+len(asset.descriptors)))
        payload.extend(asset.words)
        assets.append({'address':hex(address),'first_width':asset.first_width,'blocks':len(asset.descriptors),'words':len(asset.words),'sha256':hashlib.sha256(raw).hexdigest(),'descriptor_start':start+1,'data_start':start+1+len(asset.descriptors)})
    words=directory+payload
    binary=b''.join(v.to_bytes(3,'little') for v in words)
    (out/'bank.bin').write_bytes(binary)
    report={'schema':'perky-wavetable-second-difference-v1','block_samples':block,'asset_count':len(IDS),'decoded_samples':len(IDS)*2048,'bank_words':len(words),'directory_words':len(directory),'sha256':hashlib.sha256(binary).hexdigest(),'qualification':'all samples exact host round-trip; DSP decoder and physical allocation pending','assets':assets}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'Wavetable bank: {len(IDS)} assets, {report["decoded_samples"]} exact samples, {len(words)} words including directory/guards; block={block}; physical placement and DSP timing pending')
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,default=ROOT/'out/perky/all-voice-assets');ap.add_argument('--out',type=Path,default=ROOT/'out/perky/wavetable-bank');ap.add_argument('--block',type=int,choices=(16,32,64),default=32);a=ap.parse_args();build(a.source,a.out,a.block)
