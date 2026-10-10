"""verify_fx2lock -- the FX2 chooser cannot change a track's effect.

    python3 tools/verify/verify_fx2lock.py REMIX [--project DIR]

Boots the selected image (out/mainos_bus.bin, an "image" gate) under the
port with the project staged, selects T2, opens the FX2 chooser (FX2
twice), moves the cursor one row down and presses YES; then reads the
live FX2 ids (0x80000ec4) and compares them with a run that pressed
nothing. Without FX2 LOCK the same sequence turns T2's SEND into the
stock DELAY (measured 4 Oct 2026, bottleservice: 09 -> 08); with it the
ids are the same in both runs; a third run with the poke undone in RAM
(`--poke`) must change T2's. Also asserts the poke is in the image. The
lock is the chooser's YES key entry (0x400bc374) pointed at the NO
handler.

SKIPs without a project (OT_PROJECT, --project or ~/.octabam_project),
without the port, or for a remix without FX2 LOCK.
"""
import argparse, os, pathlib, shutil, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); import toolpath  # noqa: E402,F401
from remix import registry  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
EMU = ROOT / "out/emu/ot_emu"
PY = ROOT / ".venv/bin/python3"
OUT = ROOT / "out/fx2lockverify"
BASE = 0x40000400
LIVE_IDS = 0x80000ec4
POKE_AT, POKE, STOCK = 0x400bc374, bytes.fromhex("4003d440"), bytes.fromhex("40052474")
K = dict(no=0x32, fx2=0x26, down=0x20, yes=0x31, t2=0x11)


def script(select):
    t, lines = 1500, []
    def tap(k, gap=250):
        nonlocal t
        lines.append(f"{t} key {K[k]:#x} down"); t += 40
        lines.append(f"{t} key {K[k]:#x} up"); t += gap
    tap("no", 400)                       # the boot's date prompt
    if select:
        tap("t2", 400)
        tap("fx2", 160); tap("fx2", 800)  # the FX2 chooser: a double tap, 200 ms apart (240 did not open it)
        tap("down", 600)
        tap("yes", 1200)
    lines.append(f"{t} quit")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("remix", nargs="?", default=os.environ.get("REMIX"))
    ap.add_argument("--project", default=os.environ.get("OT_PROJECT", ""))
    ap.add_argument("--set-name", default="OCTABAM")
    ap.add_argument("--name", default="FX2LOCK")
    a = ap.parse_args()
    remix = registry.remix(a.remix)
    if "FX2 LOCK" not in remix.modules:
        print(f"  [ -- ] verify_fx2lock: {a.remix} carries no FX2 LOCK"); return 0
    project = a.project
    if not project and pathlib.Path("~/.octabam_project").expanduser().is_file():
        project = pathlib.Path("~/.octabam_project").expanduser().read_text().strip()
    if not project:
        print("  [SKIP] verify_fx2lock: no project (OT_PROJECT=<dir>, --project or ~/.octabam_project)"); return 0
    if not EMU.is_file():
        print("  [SKIP] verify_fx2lock: no port binary (make emu-cf)"); return 0
    pdir = pathlib.Path(project).expanduser()
    if not (pdir / "project.work").is_file():
        sys.exit(f"verify_fx2lock: {pdir} is not a project")
    OUT.mkdir(parents=True, exist_ok=True)
    image = ROOT / "out/mainos_bus.bin"
    img = image.read_bytes()
    fails = 0

    def check(msg, ok):
        nonlocal fails
        print(f"  [{'ok' if ok else 'FAIL'}] {msg}")
        fails += not ok

    check("the image carries the poke (the chooser's YES entry -> the close handler, 0x400bc374)",
          img[POKE_AT - BASE:POKE_AT - BASE + len(POKE)] == POKE)

    copy = OUT / "project"
    if copy.exists():
        shutil.rmtree(copy)
    copy.mkdir(parents=True)
    for f in pdir.iterdir():
        if f.is_file() and f.suffix.lower() == ".work":
            shutil.copy2(f, copy / f.name)
    card = OUT / "card.img"
    r = subprocess.run([str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"), str(copy), a.set_name, a.name,
                        "--tree", str(OUT / "tree"), "--out", str(card)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"verify_fx2lock: stage_card failed:\n{r.stdout[-1000:]}{r.stderr[-1000:]}")

    ids = {}
    stock = STOCK                                    # the control: the poke undone in RAM
    for tag, select in (("quiet", False), ("select", True), ("control", True)):
        sp, dump, log, c = OUT / f"{tag}.script", OUT / f"{tag}_ids.bin", OUT / f"{tag}.txt", OUT / f"{tag}.img"
        sp.write_text(script(select))
        shutil.copy2(card, c)
        cmd = [EMU, "--image", image, "--card", c, "--set", a.set_name, "--project", a.name, "--load-ms", "90000",
               "--mkii", "--live-script", sp, "--mem-dump", f"{LIVE_IDS:#x},16={dump}"]
        if tag == "control":                     # --poke takes one byte per addr=val
            cmd += ["--poke", ";".join(f"{POKE_AT + i:#x}={b:#x}" for i, b in enumerate(stock))]
        with open(log, "w") as f:
            f.write(" ".join(map(str, cmd)) + "\n"); f.flush()
            r = subprocess.run(list(map(str, cmd)), cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        if r.returncode:
            sys.exit(f"verify_fx2lock: ot_emu exit {r.returncode} -- {log}")
        text = log.read_text()
        check(f"{tag}: the live script ran to its quit", "ended on quit" in text)
        ids[tag] = dump.read_bytes()
    fx2 = {k: v[8:16].hex() for k, v in ids.items()}
    check(f"FX2 ids after the chooser select == untouched  {fx2['select']} vs {fx2['quiet']}",
          fx2["select"] == fx2["quiet"] and len(ids["quiet"]) == 16)
    check(f"control (the poke undone in RAM): the same select changes T2's FX2  {fx2['control']}",
          fx2["control"] != fx2["quiet"] and fx2["control"][:2] == fx2["quiet"][:2])
    print(f"verify_fx2lock: {'ok' if not fails else 'FAILED'} ({fails} failure(s)) -- {OUT}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
