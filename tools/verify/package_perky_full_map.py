#!/usr/bin/env python3
"""One immutable external handoff; never flash or overwrite a prior bundle."""
import argparse,hashlib,json,shutil,tempfile
from pathlib import Path
import measure_perky_full_map as f
ROOT=f.ROOT;W=f.W
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--destination',type=Path);a=p.parse_args()
 qpath=W/'QUALIFICATION.json';q=json.loads(qpath.read_text());assert q['status']=='PASS_LOCAL_FULL_MAP; MKII_ACCEPTANCE_PENDING' and not q['hardware_flashed'] and not q['physical_acceptance']
 for name,h in q['receipts'].items():assert sha(name)==h,('receipt changed',name)
 for name,h in q['source_sha256'].items():assert sha(ROOT/name)==h,('source changed',name)
 for artifact in q['artifacts'].values():assert sha(artifact['path'])==artifact['sha256']
 destination=(a.destination or ROOT.parent/f"PERKY_PKFM6_LOCAL_{q['artifacts']['main']['sha256'][:8]}").resolve()
 assert not destination.is_relative_to(ROOT),'handoff must stay outside the repository'
 assert not destination.exists() and not destination.with_suffix('.zip').exists(),'handoff destination already exists'
 project=json.loads((W/'HANDOFF_PROJECT.json').read_text());tree=W/'handoff/CARD_CONTENTS'
 for name,h in project['project_files'].items():assert sha(tree/name)==h
 assert sha(tree/'PERKYAH.DAT')==q['asset_file']['sha256']
 temporary=Path(tempfile.mkdtemp(prefix='.pkfm6-',dir=destination.parent))
 try:
  shutil.copytree(tree,temporary/'CARD_CONTENTS')
  card=Path(q['artifacts']['card']['path']);shutil.copy2(card,temporary/'CARD_CONTENTS'/card.name)
  midi=Path(q['artifacts']['midi']['path']);(temporary/'MIDI_ALTERNATIVE').mkdir();shutil.copy2(midi,temporary/'MIDI_ALTERNATIVE'/midi.name)
  for source,name in ((qpath,'QUALIFICATION.json'),(W/'PROFILE_BUILD.json','PROFILE_BUILD.json'),(W/'HANDOFF_PROJECT.json','HANDOFF_PROJECT.json'),(ROOT/'modules/perky/hybrid/FULL_MAP_QUALIFICATION.md','FULL_MAP_QUALIFICATION.md'),(ROOT/'modules/perky/hybrid/FULL_MAP_QUALIFICATION.json','FULL_MAP_QUALIFICATION.json')):shutil.copy2(source,temporary/name)
  peak=q['maximum'];readme=f'''# PERKY PKFM6 — one local candidate

All twelve PERKONS choices are present on T1/T2/T5/T6, with three modes each.
All fourteen stock effects remain available. This build passed the local
campaign; **physical MKII acceptance is pending**. PERKY4S remains the confirmed
hardware release. This bundle has not been flashed automatically.

| Track | ALGO 1 | ALGO 2 | ALGO 3 |
|---|---|---|---|
| T1 | Fold Drum 1 | Wavetable V1 | Simple Drum |
| T2 | Fold Drum 2 | Wavetable V2 | Complex Drum |
| T5 | Resonant | Slap | Karplus |
| T6 | Noise Hat | Noise/Tone | Acoustic Hats |

Noise Hat runs on DSP-A; the other choices run on ColdFire. SRC controls are
TUNE, DECAY, ALGO, PAR1, PAR2, MODE. The measured local worst ISR is
{peak['microseconds']:.3f} us / {peak['deadline_microseconds']:.3f} us, with
{peak['observed_reserve_microseconds']:.3f} us observed reserve and no deadline
misses. This is not a physical timing guarantee or 20% whole-CPU margin.

## Install once

1. Keep your existing projects and confirmed rollback installer. Copy the
   contents of `CARD_CONTENTS` to your CF card. This adds the new `PERKYF6` SET,
   the OS `.bin`, and `/PERKYAH.DAT`. Keep other OS `.BIN` files outside the card
   root during this upgrade so the stock scanner selects this candidate.
2. Use your established card OS UPGRADE procedure, then restart and confirm the
   **PKFM6** tag. The card wrapper is {q['artifacts']['card']['bytes']:,} bytes,
   within the stock limit. `MIDI_ALTERNATIVE` contains the same image for your
   established MIDI procedure; choose one upgrade path.
3. Load SET **PERKYF6**, project **RIG**. Leave transport stopped briefly for
   initial asset loading. Acoustic Hats requires `/PERKYAH.DAT`; it stays silent
   until the UI task verifies the file. The file is loaded once into RAM and
   introduces no source-time file reads.

This is a PK/2 mapping. Older PK/1 projects are not silently converted. Use the
fresh supplied SET for this check; explicit new-machine creation initializes
the new mapping's defaults.

## One consolidated MKII session

Record main audio and judge panel response while playing the supplied project
for roughly ten minutes. A1 is WT/WT + Slap + metallic Hat with four STATIC
tracks, dense controls/LFOs and all fourteen effects. Move the fader and enable
the scene endpoints with the normal scene controls; edit the SRC parameters.

Play A2 (Noise/Tone), A3 (Acoustic Hats) and A4 (Fold1/Fold2 + Resonant + Hat).
Bank B patterns 1–4 walk the 243 algorithm/mode tuples: let each complete one
64-step cycle. These are patterns in this same image, not more firmware tests.
Return to A1, change Part 1 → 3 → 1, and STOP/START once. Save the demo, restart
the unit and check that the selections reload. Keep the original new
`PKH2*.PRF` files written after STOP, the audio recording and the installed tag
together; source-matched decoding uses `PROFILE_BUILD.json`.

Acceptance means no clicks/dropouts/stall, all tracks/FX audible, responsive
controls, correct changes/reload, and no physical deadline misses in the
matching captures. One successful flash alone is not that acceptance.

## Identity

MAIN SHA256: `{q['artifacts']['main']['sha256']}`

Card SHA256: `{q['artifacts']['card']['sha256']}`

Asset SHA256: `{q['asset_file']['sha256']}`

`BUNDLE.json` pins every supplied file. The qualification documents record
measured scopes and limitations. Raw MAIN/ELF images are retained in the local
build evidence; the supplied upgrade wrappers are the installation artifacts.
'''
  (temporary/'README.md').write_text(readme)
  files={str(p.relative_to(temporary)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(temporary.rglob('*')) if p.is_file()}
  bundle=dict(status='LOCAL_CANDIDATE; SINGLE_MKII_ACCEPTANCE_SESSION_PENDING',version=q['version'],main_sha256=q['artifacts']['main']['sha256'],qualification_sha256=sha(qpath),hardware_flashed=False,files=files)
  (temporary/'BUNDLE.json').write_text(json.dumps(bundle,indent=2)+'\n')
  for name,row in files.items():assert sha(temporary/name)==row['sha256']
  temporary.rename(destination)
 except Exception:shutil.rmtree(temporary,ignore_errors=True);raise
 archive=Path(shutil.make_archive(str(destination),'zip',root_dir=destination.parent,base_dir=destination.name))
 result=dict(status='PACKAGED_LOCAL_CANDIDATE_NOT_FLASHED',directory=str(destination),archive=str(archive),archive_sha256=sha(archive),bundle_sha256=sha(destination/'BUNDLE.json'),qualification_sha256=sha(qpath),source_sha256=sha(Path(__file__)))
 (W/'PACKAGE.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
