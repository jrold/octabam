#!/usr/bin/env python3
"""Read-only Pickup resource census from the user's stock MAIN OS.

Candidates are conditional ColdFire regions, not allocations released by this
audit. General recorder/FLEX memory and every DSP allocation remain reserved.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def audit(stock):
    raw=Path(stock).read_bytes();base=0x40000400
    def u32(a):return int.from_bytes(raw[a-base:a-base+4],'big')
    renderer=[u32(0x400d6434+4*i) for i in range(5)]
    assert renderer[0]==renderer[1]==renderer[4]==0x40004008, 'stock source dispatch drift'
    pages=[u32(0x400d5f38+4*i) for i in range(5)]
    assert pages[4]==0x400d3664,'Pickup descriptor pointer drift'
    return {'stock_MAIN_OS_sha256':hashlib.sha256(raw).hexdigest(),
            'source_dispatch':[hex(a) for a in renderer],
            'descriptor':{'space':'ColdFire ROM','start':0x400d362c,'end':0x400d37be,'bytes':402,
                          'usable_contiguous_bytes_if_all_references_retired':402},
            'membership_helpers':{'space':'ColdFire ROM','start':0x40097204,'end':0x400972fa,'bytes':246,
                                  'functions':[[0x40097204,0x4009728e],[0x40097290,0x400972fa]],
                                  'conditional_reclaim_with_two_RTS_stubs':242,
                                  'usable_contiguous_extents_after_stubs':[[0x40097206,0x40097290],[0x40097292,0x400972fa]]},
            'conditional_census_total_bytes':648,'conditional_net_bytes_after_stubs':644,
            'released_by_this_audit_bytes':0,
            'safe_DSP_P_X_Y_reclaim_words':0,
            'shared_track_records':{'voices':8,'stride_bytes':168,'total_bytes':1344,'reclaim_bytes':0},
            'shared_recorder_objects':{'ids':[128,135],'count':8,'stride_bytes':1096,'total_bytes':8768,'reclaim_bytes':0},
            'shared_recorder_controls':{'count':8,'stride_bytes':44,'total_bytes':352,'reclaim_bytes':0},
            'shared_audio_arena':{'base':0x40a955e0,'pages':14602,'page_bytes':6144,'bytes':89720832,'reclaim_bytes':0},
            'chooser_tables':'Keep raw ids and table entries; deleting an entry alone does not create a safe cave.',
            'shared_routines':'0x40004008 renderer, 0x400068e4 recorder writer, 0x400072f2 unpack, 0x40007680 mix, 0x40007826 pack remain.',
            'status':'feasibility census only; no Pickup removal; no whole-program exclusivity proof or hardware removal qualification'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stock',type=Path,default=ROOT/'out/raw/section_3_MAIN_OS.bin')
    ap.add_argument('--out',type=Path,default=ROOT/'out/perky/four/pickup-feasibility.json')
    args=ap.parse_args();result=audit(args.stock)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print('Pickup audit: 648 conditional ColdFire bytes in two regions; 0 DSP words; 0 recorder/FLEX bytes reclaimed; no firmware changes')


if __name__=='__main__':main()
