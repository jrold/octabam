#!/usr/bin/env python3
"""CF METER's DSP meter under the port: the insert on T8 counts frames,
reads core 0's frame spin count and the ESAI status, and times the frame
on timer 0; a burn must take spin count away.

    python3 tools/verify/verify_cfmeter.py REMIX [--project DIR] [--frames 900]

Stages the project with T8's FX2 = CF METER (every part of every bank: the
emulated load applies bank A part 1), boots the remix's image in `ot_emu`
with the sequencer running, and reads T8's instance block at the end
(`--dsp-peek 0:X:6b00`: FX2 position 3 on core 0, r7 = 0x6200 + 0x300 x 3).
Three runs:

  1. DBRN 0: frames counted within 8 of the frames run (the port's DSP
     frames start with the transport); spin min <= spin max, spin max > 0
     (the port's idle step adds the skipped polls back into the count);
     period min <= period max, both > 0 (timer 0 counts the port's steps
     / 2, not the unit's cycles); the ESAI flag counts are printed, not
     asserted (the vendored ESAI_1 reads TUE every frame: nothing feeds
     it there).
  2. DBRN 40 (960 cycles per sample): the planted fault. Spin min must
     fall below run 1's with the period max unchanged (within 10 %); the
     fall prices one poll of the wait in the port's steps.
  3. DBRN 127 (3,048 cycles per sample): past core 0's frame under the
     port. Period max must exceed 1.5 x run 1's: the DSP missed the frame
     sync and waited for the ring to come round, the late-frame signature
     slot 9 and slot 14 exist to show.

SKIPs without a project (OT_PROJECT / --project), without the port, or for
a remix without CF METER. What it cannot see: the unit's cycle costs (the
port prices each instruction at one step) and the ESAI's real underrun
behaviour; both need the capture procedure in modules/cfmeter/README.md.
"""
import argparse, os, pathlib, re, shutil, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); import toolpath  # noqa: E402,F401
from remix import registry  # noqa: E402
import ot_project  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
EMU = ROOT / "out/emu/ot_emu"
PY = ROOT / ".venv/bin/python3"
OUT = ROOT / "out/cfmeterverify"
BLOCK = 0x6b00                   # T8's FX2 instance on core 0
SLOT = dict(last_frame=1, spin_min=3, spin_max=4, tue=5, roe=6, esai1=7, per_min=8, per_max=9, frames=10)


def run_port(image, card, set_name, name, frames, log):
    cmd = [str(EMU), "--image", str(image), "--card", str(card), "--set", set_name, "--project", name,
           "--sequencer", "--internal-clock", "--frames", str(frames), "--load-ms", "90000",
           "--dsp", "--main-level", "64", "--dsp-peek", f"0:X:{BLOCK:x},24"]
    with open(log, "w") as f:
        f.write(" ".join(cmd) + "\n"); f.flush()
        r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    text = log.read_text()
    if r.returncode:
        sys.exit(f"verify_cfmeter: ot_emu exit {r.returncode} -- {log}")
    m = re.search(rf"core 0 X:0x0*{BLOCK:x}:((?: [0-9a-f]{{6}})+)", text)
    if not m:
        sys.exit(f"verify_cfmeter: no peek of X:{BLOCK:#x} in {log}")
    words = [int(w, 16) for w in m.group(1).split()]
    ran = re.search(r"frames run : (\d+) since transport start", text)
    return {k: words[i] for k, i in SLOT.items()}, int(ran.group(1)) if ran else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("remix", nargs="?", default=os.environ.get("REMIX"))
    ap.add_argument("--project", default=os.environ.get("OT_PROJECT", ""))
    ap.add_argument("--frames", type=int, default=900)
    ap.add_argument("--set-name", default="OCTABAM")
    ap.add_argument("--name", default="CFMETER")
    ap.add_argument("--image", default="")
    a = ap.parse_args()
    remix = registry.remix(a.remix)
    if "CF METER" not in remix.modules:
        print(f"  [ -- ] verify_cfmeter: {a.remix} carries no CF METER"); return 0
    if not a.project:
        print("  [SKIP] verify_cfmeter: no project (OT_PROJECT=<dir> or --project)"); return 0
    if not EMU.is_file():
        print("  [SKIP] verify_cfmeter: no port binary (make emu-cf)"); return 0
    pdir = pathlib.Path(a.project).expanduser()
    if not (pdir / "project.work").is_file():
        sys.exit(f"verify_cfmeter: {pdir} is not a project")
    mod = registry.modules()["CF METER"]
    OUT.mkdir(parents=True, exist_ok=True)

    image = pathlib.Path(a.image) if a.image else OUT / "mainos.bin"
    if not a.image:
        env = dict(os.environ, REMIX=a.remix, XBUS="1", SPEC="1"); env.setdefault("BUILD", "0")
        r = subprocess.run([sys.executable, str(ROOT / "tools/build/build_bus.py")], env=env,
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode:
            sys.exit(f"verify_cfmeter: building {a.remix} failed:\n{(r.stdout + r.stderr)[-1500:]}")
        shutil.copy2(ROOT / "out/mainos_bus.bin", image)

    dbrn_slot = next(i for i, p in enumerate(mod.params) if p.name == b"DBRN")
    p1 = [p.default or 0 for p in mod.params[:6]]
    p2 = [p.default or 0 for p in mod.params[6:12]]
    results = {}
    for label, dbrn in (("healthy", 0), ("burn", 40), ("wall", 127)):
        copy = OUT / f"project_{label}"
        if copy.exists():
            shutil.rmtree(copy)
        copy.mkdir(parents=True)
        for f in pdir.iterdir():
            if f.is_file() and f.suffix.lower() == ".work":
                shutil.copy2(f, copy / f.name)
        page = list(p1); page[dbrn_slot] = dbrn
        ot_project.set_fx(copy, "fx2", 8, "CF METER", page=page, page2=p2, guard=False)
        card = OUT / f"card_{label}.img"
        r = subprocess.run([str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"), str(copy), a.set_name, a.name,
                            "--tree", str(OUT / f"tree_{label}"), "--out", str(card)],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"verify_cfmeter: stage_card failed:\n{r.stdout[-1000:]}{r.stderr[-1000:]}")
        block, ran = run_port(image, card, a.set_name, a.name, a.frames, OUT / f"port_{label}.txt")
        results[label] = (block, ran)
        print(f"  {label} (DBRN {dbrn}): frames run {ran}; T8 block: "
              + ", ".join(f"{k} {v}" for k, v in block.items()))

    fails = 0
    def check(label, ok, detail=""):
        nonlocal fails
        fails += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] {label}{'  ' + detail if detail else ''}")

    h, ran = results["healthy"]
    check("frames counted match the frames run (the insert sees every frame)", abs(h["frames"] - ran) <= 8,
          f"{h['frames']} counted, {ran} run")
    check("the frame id moved (x:$415 steps per frame)", h["last_frame"] != 0, f"last {h['last_frame']:#x}")
    check("spin count: min <= max, max > 0", 0 < h["spin_max"] and h["spin_min"] <= h["spin_max"],
          f"min {h['spin_min']} max {h['spin_max']}")
    check("period on timer 0: min <= max, min > 0", 0 < h["per_min"] <= h["per_max"],
          f"min {h['per_min']} max {h['per_max']} (counts / 4, the port's steps)")
    print(f"  ESAI frames: TUE {h['tue']}, ROE {h['roe']}, ESAI_1 {h['esai1']} (printed, not asserted)")
    b, _ = results["burn"]
    fell = h["spin_min"] - b["spin_min"]
    check("DBRN 40 takes spin count away (the planted fault)", fell > 0,
          f"spin min {h['spin_min']} -> {b['spin_min']}")
    check("DBRN 40 leaves the frame period alone", abs(b["per_max"] - h["per_max"]) <= 0.1 * h["per_max"],
          f"period max {h['per_max']} -> {b['per_max']}")
    if fell > 0:
        print(f"  one poll of the wait = {24 * 40 * 16 / fell:.1f} port steps ({24 * 40 * 16} burnt per frame / {fell} polls)")
    w, _ = results["wall"]
    check("DBRN 127 misses the frame sync (period max > 1.5 x healthy: the late-frame signature)",
          w["per_max"] > 1.5 * h["per_max"], f"period max {h['per_max']} -> {w['per_max']}, spin max {h['spin_max']} -> {w['spin_max']}")
    if fails:
        sys.exit(f"verify_cfmeter: {fails} check(s) failed -- {OUT}")
    print("  verify_cfmeter: all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
