#!/usr/bin/env python3
"""Join image-bound stock workloads without confusing IRQ and ACK scopes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def percentile(histogram, fraction):
    count=sum(n for _,n in histogram)
    threshold=max(1, int((count-1)*fraction)+1)
    cumulative=0
    for ticks,n in sorted(histogram):
        cumulative+=n
        if cumulative>=threshold:
            return ticks/132.0
    raise AssertionError('empty elapsed histogram')


def summarize(paths):
    rows=[];receipts={};running=False
    for path in paths:
        report=json.loads(path.read_text())
        running |= report['status']=='RUNNING'
        for file,digest in report['inputs'].items():
            assert sha(file)==digest, 'matrix input drift: '+file
        receipts[str(path)]=sha(path)
        for item in report['rows']:
            if 'result' not in item:
                if item['status']=='LOCALLY_FAILING':
                    rows.append(dict(name=item['name'],status='LOCALLY_FAILING',error=item['error']))
                continue
            result=item['result']
            for file,digest in result['inputs'].items():
                assert sha(file)==digest, 'row input drift: '+file
            images=[Path(p) for p in result['inputs'] if Path(p).name.startswith('mainos_')]
            assert len(images)==1
            build=json.loads((images[0].parent/'BUILD.json').read_text())
            assert sha(images[0])==build['artifacts']['mainos']['sha256']
            r=dict(name=item['name'],version=build['version'],image_sha256=sha(images[0]),
                   source_id=build['hybrid_source_id'],kind=item['kind'],scenario=item['scenario'],pair=item['pair'],
                   status='REQUIRES_PHYSICAL_HARDWARE_CONFIRMATION',local_status=item['status'],
                   requested_transport_frames=result['frames'],stock_tracks=item['stock_tracks'],cf_tracks=item['cf_tracks'],
                   interior_firmware_timer_us=result['dtim3_profiler']['dtim3_us'],
                   per_voice_callback_calls=result['dtim3_profiler']['dtim3_ticks']['inst_calls'],
                   perky_ui_publications=result['dtim3_profiler']['ui_tick_count'],
                   ack_CPU_work=result['ot_emu']['cf_ack_interval'],card=result['ot_emu']['playback_card'],
                   source_audio=result['audio_verification'],matrix_receipt=str(path))
            if 'executed_full_ISR' in result:
                work=result['executed_full_ISR']
                for file,digest in work['reports'].items():
                    assert sha(file)==digest, 'observer report drift'
                elapsed=work['elapsed_timer'];histogram=elapsed['histogram_ticks']
                assert elapsed['samples']==work['total_completed_frames']==sum(n for _,n in histogram)
                r['full_ISR_CPU_us']=dict(mean=work['mean_cycles']/264.0,maximum=work['maximum_us'],
                                         modeled_deadline_misses=work['duration_misses'])
                r['observed_elapsed_ISR_us']=dict(mean=elapsed['sum_ticks']/elapsed['samples']/132.0,
                    maximum=elapsed['max_ticks']/132.0,**{name:percentile(histogram,q) for name,q in
                        [('p50',.5),('p95',.95),('p99',.99),('p99_9',.999)]},scope=elapsed['scope'])
                r['total_completed_IRQ_frames']=work['total_completed_frames']
                r['startup_frames']=work['startup_frames']
                r['terminal_uncompleted_saved_A7_prefix']=work['terminal_uncompleted_saved_A7_prefix']
                r['private_peak_bytes']=work['private_peak_bytes']
                stack=json.loads(Path(next(p for p in work['reports'] if Path(p).name=='executed-stack.json')).read_text())
                r['observed_task_instructions']={t['task']:t['instructions'] for t in stack['stacks']}
                r['queue_max']=stack['sys_queue_max'];r['panel_ring_max']=stack['panel_ring_max']
            rows.append(r)
    increments=[]
    for dual in rows:
        if dual.get('scenario')!='F' or 'full_ISR_CPU_us' not in dual:continue
        for first_scenario,voice,other in [('B',0,1),('B6',1,0)]:
            matches=[r for r in rows if r.get('version')==dual['version'] and r.get('kind')==dual['kind']
                     and r.get('scenario')==first_scenario and r['pair'][voice]==dual['pair'][voice]
                     and r['requested_transport_frames']==dual['requested_transport_frames'] and 'full_ISR_CPU_us' in r]
            if not matches:continue
            first=matches[0]
            zeros=[r for r in rows if r.get('version')==dual['version'] and r.get('kind')==dual['kind']
                   and r.get('scenario')=='A' and r['requested_transport_frames']==dual['requested_transport_frames']
                   and 'full_ISR_CPU_us' in r]
            inc=dict(version=dual['version'],kind=dual['kind'],pair=dual['pair'],first_voice_track=2 if voice==0 else 6,
                     added_voice_track=2 if other==0 else 6,
                     added_voice_mean_full_ISR_us=dual['full_ISR_CPU_us']['mean']-first['full_ISR_CPU_us']['mean'],
                     scope='Difference of matched mean total executed ISR work; differences of maxima are not marginal costs.')
            if zeros:
                inc['first_voice_mean_full_ISR_us']=first['full_ISR_CPU_us']['mean']-zeros[0]['full_ISR_CPU_us']['mean']
            increments.append(inc)
    return dict(schema='octabam.perky.stock-resource-summary.v1',status='IN_PROGRESS' if running else 'COMPLETED_INPUT_MATRICES',
        generated_utc=datetime.now(timezone.utc).isoformat(),receipts=receipts,rows=rows,marginal_voice_costs=increments,
        limits=['Short rows exercise the stated inputs; they do not establish silicon safety.',
                'Architectural request counts and modeled CPU cycles do not measure cache misses or physical SDRAM/card/DMA contention.',
                'Elapsed percentiles use the enclosing host timer window before executed RTE; CPU totals separately include its cost.',
                'Task instructions and UI publication counts do not measure input latency or prove hardware responsiveness.'])


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--matrix',type=Path,action='append',required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();result=summarize([p.resolve() for p in args.matrix])
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],len(result['rows']),'rows,',len(result['marginal_voice_costs']),'marginal comparisons')
