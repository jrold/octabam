"""Exact PERKY4 occupancy supplement; claims retain their protected reservations."""
import json
import all_fx_layout as L

def gaps(spans,used):
    result=[]
    for lo,hi in spans:
        cursor=lo
        for a,b in sorted(used):
            if b<=lo or a>=hi:continue
            assert cursor<=a and b<=hi,(hex(cursor),hex(a),hex(b),hex(hi))
            if cursor<a:result.append([cursor,a])
            cursor=b
        if cursor<hi:result.append([cursor,hi])
    return result

def supplement(work):
    path=work/'memory.json';m=json.loads(path.read_text())
    m['schema']='perky4-physical-memory-v1'
    shared=m['physical_shared_p']
    shared['free_extents']=gaps(L.SAFE_SHARED_P_SPANS,[(r['start'],r['start']+r['length']) for r in shared['extents']])
    assert sum(b-a for a,b in shared['free_extents'])==shared['free']==6
    for tag,c in m['cores'].items():
        local=[(r['start'],r['start']+r['length']) for r in c['p_shards'] if r['start']<0x30000]
        c['private_p']={'capacity':sum(b-a for a,b in L.local_p_spans(tag)),
                        'words':sum(b-a for a,b in local),
                        'free_extents':gaps(L.local_p_spans(tag),local)}
        assert c['private_p']['words']==770
        c['private_p']['free']=sum(b-a for a,b in c['private_p']['free_extents'])
        assert c['private_p']['free']==4
        c['private_x_occupancy']=[
            [0x3800,58,'persistent voice state; Complex uses 42, common overlay reserves 58'],
            [0x383a,172,'fourth waveform, unsigned int16'],
            [0x38e6,2,'uploaded padding; protected reservation'],
            [0x38e8,4,'two reference RNG uint32 limbs'],
            [0x38ec,6,'event offset, engine-init markers, admission staging'],
            [0x3900,100,'shared sparse renderer scratch, including pitch base cache'],
            [0x3964,17,'control-rate pitch cache'],[0x3975,2,'Fold2 pitch temporaries'],
            [0x3980,40,'native PCM FIFO'],[0x39b0,17,'native clock state']]
        assert sum(n for a,n,label in c['private_x_occupancy'])==418
        assert sum(b-a for a,b in c['private_x_free'])==198
        c['low_y_occupancy']=[[0x7a5,768,'three direct waves'],[0xaa5,1024,'envelope'],
            [0xea5,84,'fourth waveform tail'],[0xef9,2,'internal padding'],
            [0xefb,67,'pitch'],[0xf3e,1,'pitch alignment'],[0xf3f,147,'160/147 interpolation coefficients']]
        assert sum(n for a,n,label in c['low_y_occupancy'])==2093
        c['low_y_internal_free']=[[0xef9,0xefb]]
        for r in c['ranges']:
            if r['start']==0x3800:r['what']='PERKY voice, fourth-wave X segment, padding and RNG reservation'
            if r['space']=='y' and r['start']==0x7a5:r['what']='PERKY authentic waves, envelope, pitch and native clock; includes 46 trailing reserved free words'
    import ab_records as A
    from remix import stock
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    raw=(root/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    for tag,c in m['cores'].items():
        address,length=A.PAYLOAD_A if tag=='A' else A.PAYLOAD_B
        records,_=A.records(raw,address,length)
        c['stock_static_upload_records']=[{'space':'PXY'[sp],'start':a,'words':n} for sp,a,n,off in records]
        c['retained_stock_fx_private_p']={name:[a,n] for name,(a,n) in stock.p_spans(tag).items()
                                         if name not in ('PLATE REV','COMPRESSOR')}
    platform=json.loads((work/'platform/layout.json').read_text())
    m['ColdFire_DRAM_bytes']={'base':platform['base'],'runtime_end':platform['runtime_end'],
        'runtime_bytes':platform['runtime_end']-platform['base'],
        'bss_end':platform['bss_end'],'bss_bytes':platform['bss_end']-platform['runtime_end'],
        'stage':platform['stage'],'stage_end':platform['stage_end'],
        'packed_stage_bytes':platform['stage_end']-platform['stage'],
        'reserved_ceiling':platform['ceiling'],'remaining_after_stage_bytes':platform['ceiling']-platform['stage_end'],
        'loader':platform['loader'],'ui_event_latches_bytes':48}
    m['units']='24-bit DSP addressable words; serialized uploads use three bytes/word; no CF bytes combined with DSP words'
    path.write_text(json.dumps(m,indent=2)+'\n')
