#!/usr/bin/env python3
"""Direct installed-AU regression. Captures stay ignored; source has no assets.

macOS AudioUnit API -> independent PerkyBits public ARM controls/native PCM
-> actual ColdFire producer record -> placed shipping DSP controls/renderer.
No fitted alignment, gain, or expected PCM from the shipping implementation.
"""
import argparse, hashlib, json, os, struct, subprocess, sys
from pathlib import Path
import numpy as np
def write_wav(path, rate, samples):
 data=np.asarray(samples,dtype='<f4').tobytes();channels=samples.shape[1]
 fmt=struct.pack('<HHIIHH',3,channels,rate,rate*channels*4,channels*4,32)
 path.write_bytes(b'RIFF'+struct.pack('<I',36+len(data))+b'WAVEfmt '+struct.pack('<I',16)+fmt+b'data'+struct.pack('<I',len(data))+data)
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
import verify_perky_three_audio as a
import verify_perky_light2_src_page as cf
import build_four_payload as production
import complex_drum_compact as compact
import complex_drum_production as geometry
import simple_drum_control as control

IDS=(3571704,95459258,1152055620,1152055621)
FW=Path(os.environ.get('PERKONS_FIRMWARE','/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'))
NATIVE=Path(os.environ.get('PERKYBITS_SOURCE','/Users/jrold/Downloads/perkybits'))
COMPONENT=Path('/Library/Audio/Plug-Ins/Components/PerkyBits.component/Contents/MacOS/PerkyBits')
OUT=ROOT/'out/perky/au-regression'
# Low/high tuning, complete decay extremes, PAR1/PAR2 isolation, pitch envelope.
CORNERS=((0,0,0,0),(64,64,64,64),(127,127,127,127),(16,96,0,0),
         (16,96,127,0),(96,8,16,127),(32,127,96,16),(64,64,32,0),
         (64,64,96,127))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd):subprocess.run(list(map(str,cmd)),cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
def tools():
 OUT.mkdir(parents=True,exist_ok=True)
 run(['clang++','-std=c++17',ROOT/'tools/harness/perky_au_capture.cpp','-framework','AudioToolbox','-framework','CoreFoundation','-o',OUT/'capture'])
 src=NATIVE/'Source';u=NATIVE/'build-local/_deps/unicorn-build'
 common=['clang++','-std=c++20','-O2','-I'+str(src),'-I'+str(u.parent/'unicorn-src/include')]
 external=[src/'FirmwareImage.cpp',src/'PerkonsM7.cpp',src/'PerkonsVoices.cpp',*sorted(src.glob('NativeV121*.cpp')),ROOT/'out/perky/engine-fixtures/cacheinfo.o',u/'libunicorn.a',u/'libarm-softmmu.a',u/'libunicorn-common.a','-lpthread','-lm']
 for driver,exe in [('au_control_reference.cpp','native'),('capture_control_sweep.cpp','sweep')]:
  run([*common,ROOT/'tools/harness/perky_cf'/driver,*external,'-o',OUT/exe])
 run([OUT/'sweep',FW,ROOT/'out/perky/au/control-sweep.bin',5,0,'sweep',45])
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--capture',action='store_true');ap.add_argument('--baseline',action='store_true',help='require the preserved PERKY4 mismatch');ap.add_argument('--isolate',choices=('tune','modulation','sustain'));ap.add_argument('--baseline-case',type=int,default=0);ap.add_argument('--seconds',type=int,default=4,choices=(4,));args=ap.parse_args()
 tag=a.TAG;out=OUT/(tag+'-baseline'+('-'+args.isolate if args.isolate else '') if args.baseline else tag);out.mkdir(parents=True,exist_ok=True)
 if args.capture:
  version=subprocess.check_output(['plutil','-extract','CFBundleShortVersionString','raw','-o','-',str(COMPONENT.parent.parent/'Info.plist')],text=True).strip()
  assert version=='0.2.0',('unqualified installed AU version',version)
  tools()
 capture_manifest=OUT/'capture-manifest.json'
 if args.capture:
  capture_manifest.write_text(json.dumps({'version':'0.2.0','component_sha256':sha(COMPONENT),'firmware_sha256':sha(FW),'host_sha256':sha(OUT/'capture'),'capture_source_sha256':sha(ROOT/'tools/harness/perky_au_capture.cpp'),'gain':1,'format':'stereo float32; no normalization/effects'},indent=2)+'\n')
 receipt=json.loads(capture_manifest.read_text());assert receipt['firmware_sha256']==sha(FW),'reference firmware changed'
 cases=[(m,k) for m in range(3) for k in CORNERS]
 metadata=[]
 # Events are inside host blocks and include long-tail control changes. The AU
 # consumes one smoother update per host block; shipping's existing immediate
 # smoother schedule is separately tested, not silently treated as identical.
 events=OUT/'events.tsv'
 event_rows=[(7207,144,45,127),(19003,176,22,112),(33017,176,23,8),
             (45011,144,45,64),(69013,176,20,96),(85001,176,21,16),(120007,144,45,127)]
 if args.capture:events.write_text(''.join(' '.join(map(str,r))+'\n' for r in event_rows))
 event_results=[]
 for mode in range(3):
  p=OUT/f'events-mode-{mode+1}'
  if args.capture:
   cmd=[OUT/'capture','--firmware',FW,'--out',p.with_suffix('.f32'),'--midi',events,'--set',848820802,5,'--set',3357091,mode/2]
   for id in IDS:cmd+=['--set',id,2048/4095]
   run(cmd);run([OUT/'native',FW,mode,*([2048]*4),p.with_suffix('.pcm'),1,events])
   write_wav(p.with_suffix('.wav'),48000,np.fromfile(p.with_suffix('.f32'),'<f4').reshape(-1,2))
  au=np.fromfile(p.with_suffix('.f32'),'<f4').reshape(-1,2);native=np.fromfile(p.with_suffix('.pcm'),'<i2')
  assert np.array_equal(au[:,0]*32768,native),(mode,'AU/native retriggers/sustained CC')
  event_results.append({'mode_display':mode+1,'initial_controls':[2048]*4,'events':event_rows,'audio_sha256':sha(p.with_suffix('.f32')),'samples_exact':len(native),'scope':'actual AU/native public dynamic path; shipping update cadence has separate integration gates'})
 for i,(mode,knobs) in enumerate(cases):
  target=tuple(control.panel_to_target(v) for v in knobs);p=OUT/f'case-{i:02d}'
  if args.capture:
   cmd=[OUT/'capture','--firmware',FW,'--out',p.with_suffix('.f32'),'--seconds',args.seconds,'--set',848820802,5,'--set',3357091,mode/2]
   for id,v in zip(IDS,target):cmd+=['--set',id,v/4095]
   run(cmd);write_wav(p.with_suffix('.wav'),48000,np.fromfile(p.with_suffix('.f32'),'<f4').reshape(-1,2));run([OUT/'native',FW,mode,*target,p.with_suffix('.pcm'),1])
  au=np.fromfile(p.with_suffix('.f32'),'<f4').reshape(-1,2)
  native=np.fromfile(p.with_suffix('.pcm'),'<i2');assert len(native)==len(au)==48000*args.seconds
  assert np.max(np.abs(au))>0.001,(i,'actual AU output must be audible')
  assert np.array_equal(au[:,0],au[:,1]),(i,'AU stereo')
  assert np.array_equal(au[:,0]*32768,native),(i,'actual AU/native full decay')
  metadata.append({'case':i,'mode_display':mode+1,'firmware_mode':(1,0,2)[mode],'OT_controls':knobs,'AU_public_controls':target,'rate':48000,'note':45,'chromatic':False,'midi_velocity':127,'firmware_velocity':255,'trigger_sample':0,'seconds':args.seconds,'host_block':256,'prime_blocks':0,'gain':1,'declick':False,'audio_sha256':sha(p.with_suffix('.f32')),'reference_state_sha256':sha(p.with_suffix('.pcm.state'))})
 cf.CONTROL=ROOT/'modules/perky/control_four_candidate.c';cf.WORK=out/'controls';cf.ALGO_COUNT=4;cf.ALGO_ENGINE=(0,3,2,5)
 rows=cf.execute([cf.Case(f'au{i}',track=(0,4)[i%2],part=i%4,ping=0,trig=1,algo=3,mode=m,knobs=k,dirty=125,hidden=10) for i,(m,k) in enumerate(cases)])
 if args.baseline and not args.isolate:
  old=out/'control.c';old.write_bytes(subprocess.check_output(['git','show','11f0165f:modules/perky/control_four_candidate.c'],cwd=ROOT));cf.CONTROL=old
  rows=cf.execute([cf.Case(f'au{i}',track=(0,4)[i%2],part=i%4,ping=0,trig=1,algo=3,mode=m,knobs=k,dirty=125,hidden=10) for i,(m,k) in enumerate(cases)])
  import types
  baseline=types.ModuleType('preserved_perky4');baseline.__file__=str(ROOT/'tools/perky/build_four_payload.py')
  exec(compile(subprocess.check_output(['git','show','11f0165f:tools/perky/build_four_payload.py'],cwd=ROOT),baseline.__file__,'exec'),baseline.__dict__)
  production.build=baseline.build
 c=a.c;c.OUT=out/'dsp';c.OUT.mkdir(parents=True,exist_ok=True);c.build_host();c.CYCLE_METER=True
 source,_=production.build(out/'payload',native_clock=True);initial=c.words(out/'payload/state_init.words');tables=c.words(out/'payload/tables.words')
 wrapper='''pk_controlled_voice_exec:
        move #>$200,r6
        move #>$3900,r5
        move #>$4f8,r4
        move #>$ffffff,m0
        move #>$ffffff,m1
        move #>$ffffff,m2
        move #>$ffffff,m3
        move #>$ffffff,m4
        move #>$ffffff,m5
        move #>$ffffff,m6
        move #>$5,a
        move a1,x:>$39bf
        move x:>$3976,a
        tst a
        bne p4au_run
        jsrl pk_three_common_controls
        jsrl pk_complex_mod_update
        jsrl pk_simple_base
        jsrl pk_three_common_trigger
        move #>$1,a
        move a1,x:>$3976
p4au_run:
        move #$0,r0
        jsrl pk_complex_production_voice
        rts
'''
 if args.baseline and not args.isolate:wrapper=wrapper.replace('        jsrl pk_complex_mod_update\n','')
 binary,entry=a.at_production_addresses(wrapper+source.replace('@CONT@','$000400'))
 fresh=(ROOT/'out/perky/engine-fixtures/engine-6-mode-1-corner-0/wrapper-window-pre-trigger.bin').read_bytes()[0x1f8:0x338]
 def data(path,state,table):
  path.write_text('X 200 '+' '.join(f'{v:06x}' for v in state)+'\nX 3900 '+' '.join(['000000']*118)+'\nX 3964 00ffff '+' '.join(['000000']*16)+'\nX 500 '+' '.join(f'{v:06x}' for v in record)+'\nX 383a '+' '.join(f'{v:06x}' for v in initial[58:230])+'\nY 7a5 '+' '.join(f'{v:06x}' for v in table)+'\n');return []
 c.write_data=data;maxcycles=0;summary=[]
 for i,(mode,knobs) in enumerate(cases):
  if args.baseline and i!=args.baseline_case:continue
  case=cf.Case(f'au{i}',track=(0,4)[i%2],part=i%4,ping=0,trig=1,algo=3,mode=mode,knobs=knobs,dirty=125,hidden=10)
  words=cf.record_words(rows['rows'],i,case)
  record=[v for w in words[4:] for v in ((w>>16)&65535,w&65535)]
  if args.isolate=='tune':
   tune=min(((record[0]<<8)|record[1])+768,4095);record[0:2]=[tune>>8,tune&255]
  elif args.isolate=='modulation':record[9]=254
  elif args.isolate=='sustain':record[8]&=3
  audio,states,_=c.run(binary,entry,f'au-{i:02d}',geometry.from_original(compact.CompactComplexDrum.from_arm(fresh).words)+[0]*22,tables,[(tuple([0]*12),-1)]*(args.seconds*48000//16))
  got=np.array(c.flatten(audio));want=np.fromfile(OUT/f'case-{i:02d}.pcm','<i2')
  diff=got.astype(float)-want;err=float(np.sqrt(np.mean(diff*diff)));peak=int(np.max(np.abs(diff)))
  summary.append({'case':i,'rms_error_lsb':err,'peak_error_lsb':peak,'equal_samples':int(np.sum(got==want)),'samples':len(want)})
  (out/'comparisons.json').write_text(json.dumps(summary,indent=2)+'\n')
  if args.baseline and peak:
   assert err>100,(tag,i,'baseline mismatch too small')
   print(f'[PASS] preserved PERKY4 mismatch reproduced against actual AU: {summary[-1]}');return
  assert peak==0,(tag,i,'shipping/AU',summary[-1])
  maxcycles=max(maxcycles,max(map(int,(c.OUT/f'au-{i:02d}.meter').read_text().split())))
 assert not args.baseline,'baseline unexpectedly matches AU'
 # Direct output-rate comparison through the actual source entry and clock.
 # AU float32 linear interpolation has roundoff; DSP coefficients are Q23 and
 # stores floor. <=2 Q23 source LSB is an arithmetic bound, not an audio fit.
 integrated=[]
 if not args.baseline:
  wrapper=a.seam.WRAPPER
  begin=wrapper.index('        move #>$000100,r1');end=wrapper.index('        move r4,x:>$209',begin)
  wrapper=wrapper[:begin]+wrapper[end:]
  wrapper=wrapper.replace('        move r4,x:>$209','        move #>$4080,a\n        move a1,x:>$20b\n        move r4,x:>$209',1)
  wrapper=wrapper.replace('        move b1,x:(r4+$3)','        or #>$030000,b\n        move b1,x:(r4+$3)')
  binary,entry=a.at_production_addresses(wrapper+source.replace('@CONT@','$000400'))
  symbols={v[0]:int(v[1],16) for v in map(str.split,binary.with_suffix('.sym').read_text().splitlines()) if len(v)==2}
  def clock_data(path,state,table):
   path.write_text('X 3800 '+' '.join(f'{v:06x}' for v in state)+'\nX 3900 '+' '.join(['000000']*118)+'\n'
     +'X 500 03504b 030000 035931 030000 030000 030000 030000 030000 '+' '.join(f'{v|0x030000:06x}' for v in record)+'\n'
     +'X 418 000000\nX 20b 004080\nP 400 0bf080 '+f'{symbols["pkse_finish"]:06x}'+' 00000c\nY 7a5 '+' '.join(f'{v:06x}' for v in table)+'\n'
     +'X 3964 00ffff '+' '.join(['000000']*16)+'\nX 39b0 '+' '.join(['000000']*17)+'\n')
   return state[232:236]
  c.write_data=clock_data
  for mode in range(3):
   for corner in range(3):
    i=mode*len(CORNERS)+corner;knobs=CORNERS[corner];target=[control.panel_to_target(v) for v in knobs];p=OUT/f'clock-{mode+1}-{corner}'
    if args.capture:
     cmd=[OUT/'capture','--firmware',FW,'--rate',44100,'--out',p.with_suffix('.f32'),'--set',848820802,5,'--set',3357091,mode/2]
     for id,v in zip(IDS,target):cmd+=['--set',id,v/4095]
     run(cmd);write_wav(p.with_suffix('.wav'),44100,np.fromfile(p.with_suffix('.f32'),'<f4').reshape(-1,2))
    case=cf.Case(f'au{i}',track=(0,4)[i%2],part=i%4,ping=0,trig=1,algo=3,mode=mode,knobs=knobs,dirty=125,hidden=10)
    words=cf.record_words(rows['rows'],i,case);record=[v for w in words[4:] for v in ((w>>16)&65535,w&65535)]
    audio,_,_=c.run(binary,entry,f'clock-{mode+1}-{corner}',initial,tables,[(tuple([0]*12),0)]+[(tuple([0]*12),-1)]*(176400//16-1))
    got=np.array(c.flatten(audio));want=np.fromfile(p.with_suffix('.f32'),'<f4').reshape(-1,2)[:,0].astype(float)*(1<<20)
    assert len(got)==len(want)==176400
    diff=got-want;peak=float(np.max(np.abs(diff)));rms=float(np.sqrt(np.mean(diff*diff)))
    assert peak<=2,(tag,mode,corner,'actual AU/output clock/trim',peak,rms)
    integrated.append({'mode_display':mode+1,'OT_controls':knobs,'AU_public_controls':target,'native_rate':48000,'output_rate':44100,'trim':0.125,'samples':len(got),'peak_error_source_Q23_lsb':peak,'rms_error_source_Q23_lsb':rms,'tolerance_source_Q23_lsb':2,'AU_capture_sha256':sha(p.with_suffix('.f32'))})
 report={'schema':'perky-direct-au-v1','component_version':receipt['version'],'component_sha256':receipt['component_sha256'],'firmware_sha256':sha(FW),'native_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=NATIVE,text=True).strip(),'source_parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'modules/perky/control_four_candidate.c',ROOT/'tools/perky/build_four_payload.py',ROOT/'tools/perky/source_clock.py')},'placed_DSP_binary_sha256':sha(binary),'core':tag,'conditions':metadata,'comparisons':summary,'dynamic_AU_native':event_results,'integrated_AU_clock_trim':integrated,'worst_raw_cycles':maxcycles,'normalized':False,'status':'direct AU/native/ColdFire/placed DSP native PCM exact; physical hardware pending'}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(f'[PASS] actual PerkyBits AU / core {tag}: {len(cases)} four-second complete decays; {len(cases)*48000*args.seconds} samples exact; actual CF records and placed shipping controls/renderer; worst raw cycles {maxcycles}')
if __name__=='__main__':main()
