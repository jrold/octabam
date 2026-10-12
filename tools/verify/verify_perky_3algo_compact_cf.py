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

    print(f"compact-cf: {checked} states ({TRIALS} per family) converted identically "
          f"to the models' own `from_arm`, over randomized TUNE/DECAY/ENV/MIX, "
          f"velocity, note and trigger")
    print("perky-3algo-compact-cf: PASS (the ColdFire's ARM->compact conversion is "
          "bit-exact against the reader the renderer itself uses, so the bridge that "
          "carries panel changes into the compact state is proven before anything "
          "depends on it)")


if __name__ == "__main__":
    main()
