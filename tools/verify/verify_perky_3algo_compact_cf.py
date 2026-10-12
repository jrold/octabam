#!/usr/bin/env python3
"""The ColdFire's ARM -> compact conversion, proved against the renderer's own reader.

WHY THIS EXISTS. The authentic v1.2.1 machine updates a Resonant voice on the CPU
per event: the ARM routines at 0x0802682C / 0x08026030 write the panel's TUNE,
DECAY, ENV and MIX into an ARM-shaped object, and `cf_perky4.c` carries those in C.
The DSP port renders from a COMPACT layout. Until now the only thing that crossed
between them was a fixed template computed at a NEUTRAL panel setting, so the
instruments sounded but ignored their knobs.

`modules/perky/resonant_compact_cf.c` is the bridge. Its oracle is not a
re-derivation: it is compared, word for word, against the models' own `from_arm`,
which is the code the RENDERER uses to read a state -- so a field the port drops
and a field the renderer needs cannot cancel out.

THE COMPARISON IS WORTH HAVING. The first hand-written version of the port had two
errors: the snare's decay blocks were transcribed at the wrong offsets, and the two
mix coefficients (`MIX_FIRST`/`MIX_SECOND`, object 0x164/0x168 -> compact 97/99)
were MISSING entirely. Both compiled clean. Both were caught here within one run.

WHAT IT COVERS: both families, 400 states each, over randomized TUNE/DECAY/ENV/MIX
targets (0..4095), randomized velocity and note, and a 70/30 split of triggered and
untriggered objects -- so the paths that only a trigger writes are exercised too.
"""
from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "modules/perky")]

OUT = ROOT / "out/perky/dsp-3algo/compact-cf"
SRC = ROOT / "modules/perky/resonant_compact_cf.c"
ASSETS = ROOT / "out/perky/res-assets"
TRIALS = 400


def die(m: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-compact-cf: " + m)


def main() -> None:
    import resonant_bass_compact as bass
    import resonant_control_update as rcu
    import resonant_snare_compact as snare

    if not (ASSETS / "pitch.bin").is_file() or not (ASSETS / "chromatic.bin").is_file():
        die(f"missing the shared PĒRKONS tables in {ASSETS.relative_to(ROOT)} -- "
            f"build outputs of the perky-optimize worktree, not committed")
    pitch = (ASSETS / "pitch.bin").read_bytes()
    chrom = (ASSETS / "chromatic.bin").read_bytes()

    OUT.mkdir(parents=True, exist_ok=True)
    main_c = OUT / "probe.c"
    main_c.write_text(
        '#include <stdio.h>\n#include <stdint.h>\n#include <stdlib.h>\n'
        'void pk_cf_res_compact_bass(const uint8_t*, uint16_t*);\n'
        'void pk_cf_res_compact_snare(const uint8_t*, uint16_t*);\n'
        'int main(int argc,char**argv){\n'
        '    (void)argc;\n'
        '    const int bass = atoi(argv[1]);\n'
        '    const unsigned n = bass ? 0x178u : 0x1D4u;\n'
        '    uint8_t obj[0x1D4]; uint16_t w[101];\n'
        '    FILE*f=fopen(argv[2],"rb");\n'
        '    if(fread(obj,1,n,f)!=n){fprintf(stderr,"short read\\n");return 2;}\n'
        '    fclose(f);\n'
        '    if(bass) pk_cf_res_compact_bass(obj,w);\n'
        '    else     pk_cf_res_compact_snare(obj,w);\n'
        '    for(unsigned i=0;i<(bass?88u:101u);++i) printf("%04x\\n", w[i]);\n'
        '    return 0;\n}\n')
    exe = OUT / "probe"
    build = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            str(main_c), str(SRC), "-o", str(exe)],
                           capture_output=True, text=True)
    if build.returncode:
        die("the port did not build:\n" + (build.stderr or "")[-2000:])

    rnd = random.Random(20261007)
    obj_path = OUT / "obj.bin"
    checked = 0
    for fam, fresh, upd, trig, cls, width, is_bass in (
            ("bass", rcu.fresh_bass, rcu.update_bass, rcu.trigger_bass,
             bass.ResonantBass, 0x178, True),
            ("snare", rcu.fresh_snare, rcu.update_snare, rcu.trigger_snare,
             snare.ResonantSnare, 0x1D4, False)):
        for trial in range(TRIALS):
            targets = tuple(rnd.randrange(0, 4096) for _ in range(4))
            vel = rnd.randrange(1, 256)
            note = rnd.randrange(0, 128)
            obj = upd(fresh(vel, note), targets, pitch, chrom)
            if rnd.random() < 0.7:
                obj = trig(obj, vel, note)
            raw = bytes(obj[:width]) if is_bass else bytes(obj)
            obj_path.write_bytes(raw)
            run = subprocess.run([str(exe), "1" if is_bass else "0", str(obj_path)],
                                 capture_output=True, text=True, check=True)
            got = [int(x, 16) for x in run.stdout.split()]
            want = list(cls.from_arm(raw).words)
            if got != want:
                diff = [(i, g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w]
                die(f"{fam} trial {trial}, targets {targets}, vel {vel}, note {note}: "
                    f"{len(diff)} compact words differ, first {diff[:6]}")
            checked += 1

    # ---- THE CONTROL LAW: common_update / update_bass / update_snare / triggers
    #
    # The bridge alone only moves a state between layouts. What makes a knob
    # audible is the law, so it is compared the same way: the SAME template goes
    # into the C and into the Python, and the resulting ARM objects must agree.
    law_c = OUT / "law.c"
    law_c.write_text(
        '#include <stdio.h>\n#include <stdint.h>\n#include <stdlib.h>\n'
        'void pk_cf_res_update_bass(uint8_t*, const uint32_t[4], const uint16_t*);\n'
        'void pk_cf_res_update_snare(uint8_t*, const uint32_t[4], const uint16_t*);\n'
        'void pk_cf_res_trigger_bass(uint8_t*, unsigned, unsigned);\n'
        'void pk_cf_res_trigger_snare(uint8_t*, unsigned, unsigned);\n'
        'int main(int argc,char**argv){\n'
        '    (void)argc;\n'
        '    const int bass=atoi(argv[1]);\n'
        '    static uint8_t obj[0x1D4]; static uint16_t chrom[12];\n'
        '    /* BOTH families work in a 0x1D4 object: update_bass writes 0x17C,\n'
        '     * past the 0x178 prefix the bass captures compare. */\n'
        '    const unsigned wr = bass?0x178u:0x1D4u;\n'
        '    FILE*f=fopen(argv[2],"rb");\n'
        '    if(fread(obj,1,0x1D4u,f)!=0x1D4u) return 2;\n'
        '    fclose(f);\n'
        '    f=fopen(argv[9],"rb");\n'
        '    if(fread(chrom,2,12,f)!=12) return 2;\n'
        '    fclose(f);\n'
        '    uint32_t t[4];\n'
        '    for(int i=0;i<4;i++) t[i]=(uint32_t)strtoul(argv[3+i],0,10);\n'
        '    const unsigned vel=(unsigned)atoi(argv[7]), note=(unsigned)atoi(argv[8]);\n'
        '    if(bass) pk_cf_res_update_bass(obj,t,chrom);\n'
        '    else     pk_cf_res_update_snare(obj,t,chrom);\n'
        '    if(atoi(argv[10])){ if(bass) pk_cf_res_trigger_bass(obj,vel,note);\n'
        '                        else     pk_cf_res_trigger_snare(obj,vel,note); }\n'
        '    FILE*g=fopen(argv[11],"wb"); fwrite(obj,1,wr,g); fclose(g);\n'
        '    return 0;\n}\n')
    law_exe = OUT / "lawprobe"
    build = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            str(law_c), str(SRC), "-o", str(law_exe)],
                           capture_output=True, text=True)
    if build.returncode:
        die("the control law did not build:\n" + (build.stderr or "")[-2000:])

    chrom_path = OUT / "chrom.bin"
    chrom_path.write_bytes(chrom)
    obj_path = OUT / "law-obj.bin"
    out_path = OUT / "law-out.bin"
    OBJ = 0x1D4
    # Everything except the pitch word MUST agree; the pitch word MUST be the
    # only thing that does not, or the omission has stopped being an omission.
    law_checked = 0
    offsite = 0
    for fam, fresh, upd, trig, cmpw, is_bass in (
            ("bass", rcu.fresh_bass, rcu.update_bass, rcu.trigger_bass, 0x178, True),
            ("snare", rcu.fresh_snare, rcu.update_snare, rcu.trigger_snare, 0x1D4, False)):
        for trial in range(TRIALS):
            targets = tuple(rnd.randrange(0, 4096) for _ in range(4))
            vel = rnd.randrange(1, 256)
            note = rnd.randrange(0, 128)
            do_trig = rnd.random() < 0.7
            base = fresh(vel, note)
            tmpl = bytearray(base[:OBJ]) if len(base) >= OBJ \
                else bytearray(base) + bytes(OBJ - len(base))
            obj_path.write_bytes(bytes(tmpl[:OBJ]))
            subprocess.run([str(law_exe), "1" if is_bass else "0", str(obj_path),
                            *[str(x) for x in targets], str(vel), str(note),
                            str(chrom_path), "1" if do_trig else "0", str(out_path)],
                           check=True, capture_output=True)
            got = out_path.read_bytes()
            ref = bytearray(tmpl[:OBJ])
            ref = upd(ref, targets, pitch, chrom)
            if do_trig:
                ref = trig(ref, vel, note)
            want = bytes(ref[:cmpw])
            diff = [i for i, (g, w) in enumerate(zip(got, want)) if g != w]
            stray = [i for i in diff if i not in (0x34, 0x35)]
            if stray:
                offsite += 1
                if offsite <= 3:
                    die(f"{fam} trial {trial}, targets {targets}, vel {vel}, "
                        f"note {note}, trig {do_trig}: the law differs OUTSIDE the "
                        f"deliberately-omitted pitch word, at "
                        f"{[hex(i) for i in stray[:6]]}")
            law_checked += 1

    print(f"compact-cf: {checked} states ({TRIALS} per family) converted identically "
          f"to the models' own `from_arm`, over randomized TUNE/DECAY/ENV/MIX, "
          f"velocity, note and trigger")
    print("perky-3algo-compact-cf: PASS (the ColdFire's ARM->compact conversion is "
          "bit-exact against the reader the renderer itself uses, so the bridge that "
          "carries panel changes into the compact state is proven before anything "
          "depends on it), and its control law (common_update + update_bass/"
          "update_snare + the triggers) is bit-exact against the Python recovery "
          "over a further 800 states, with every difference confined to the ONE "
          "object word the port deliberately omits -- the pitch word at 0x34, "
          "which from_arm never reads)")


if __name__ == "__main__":
    main()
