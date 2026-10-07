#!/usr/bin/env python3
"""Generate original ARM qualification fixtures for all 12 families locally.

Wrapper windows are memory snapshots, not compact state declarations.
No firmware-derived state or audio is committed. Uses the user's own native
reference sources and previously built Unicorn libraries without downloads.
"""
from pathlib import Path
import argparse,hashlib,json,platform,subprocess
ROOT=Path(__file__).resolve().parents[2]
V121_SHA256='adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6'

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('firmware',type=Path);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--unicorn-build',type=Path,required=True);ap.add_argument('--out',type=Path,default=ROOT/'out/perky/engine-fixtures');a=ap.parse_args()
    if hashlib.sha256(a.firmware.read_bytes()).hexdigest()!=V121_SHA256:
        raise SystemExit('ARM capture requires the pinned PĒRKONS v1.2.1 image; trigger wrapper addresses are version-specific')
    a.out.mkdir(parents=True,exist_ok=True);src=a.source/'Source';u=a.unicorn_build
    sources=[ROOT/'tools/harness/perky_cf/capture_engines.cpp',src/'FirmwareImage.cpp',src/'PerkonsM7.cpp',src/'PerkonsVoices.cpp',*sorted(src.glob('NativeV121*.cpp'))]
    exe=a.out/'capture'
    extra=[]
    if platform.system()=='Darwin' and platform.machine()=='arm64':
        # The workspace may deny sysctl cache discovery. Unicorn then reads
        # CTR_EL0, which traps on Apple CPUs. Use its existing conservative
        # 64-byte fallback via a locally compiled object; leave dependencies intact.
        us=u.parent/'unicorn-src'
        cache=(us/'qemu/util/cacheinfo.c').read_text()
        old='    arch_cache_info(&isize, &dsize);'
        assert cache.count(old)==1
        cache=cache.replace(old,'    /* Darwin fallback avoids protected CTR_EL0. */')
        patched=a.out/'cacheinfo.c';patched.write_text(cache)
        obj=a.out/'cacheinfo.o'
        includes=[u.parent.parent,us/'glib_compat',us/'qemu',us/'qemu/include',us/'include',us/'qemu/tcg',us/'qemu/tcg/aarch64']
        subprocess.run(['cc','-O2','-DNDEBUG','-std=gnu11','-D_GNU_SOURCE','-DUNICORN_HAS_ARM',*[f'-I{x}' for x in includes],'-c',str(patched),'-o',str(obj)],check=True)
        extra=[str(obj)]
    subprocess.run(['c++','-std=c++20','-O2','-I'+str(src),'-I'+str(u.parent/'unicorn-src/include'),*map(str,sources),*extra,str(u/'libunicorn.a'),str(u/'libarm-softmmu.a'),str(u/'libunicorn-common.a'),'-lpthread','-lm','-o',str(exe)],check=True)
    subprocess.run([str(exe),str(a.firmware),str(a.out)],check=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest={'firmware_sha256':sha(a.firmware),'source_sha256':{str(p.relative_to(a.source)) if p.is_relative_to(a.source) else str(p.relative_to(ROOT)):sha(p) for p in sources},'files':{str(p.relative_to(a.out)):sha(p) for p in sorted(a.out.rglob('*.bin'))}}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
