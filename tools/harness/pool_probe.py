#!/usr/bin/env python3
"""Stock's audio page pool under the port (modules/memory/README.md).

    .venv/bin/python3 tools/harness/pool_probe.py <image> <out dir>

Stages the tone project (tools/harness/usb_sig_project.py, from
~/.octabam_project), boots <image> with the allocator's paths watched, and
prints the hits during the boot and LOAD PROJECT, the pool's globals and
every held slot's pages (first, last, contiguous runs) after the load and
after releasing slot 3 (call 0x40096300 3). Each snapshot is also
written as JSON under <out dir>."""
import json
import pathlib
import sys
import tempfile
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/verify")); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tools/harness"))
import verify_usb_post as V

IMAGE = sys.argv[1]
OUT = pathlib.Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
src = pathlib.Path("~/.octabam_project").expanduser().read_text().strip()
work = pathlib.Path(tempfile.mkdtemp(prefix="pool_"))
card = V.stage(src, work)
WATCH = {0x40096f24: "cold init", 0x40096914: "slot alloc (bump)", 0x40096910: "slot alloc: already held (-46)",
         0x40096926: "slot alloc: too few free (-5)", 0x40096300: "slot release", 0x40095a90: "recorder pages walk",
         0x400948cc: "0x400948cc", 0x40095b70: "slot pages clear"}
V.IMAGE = pathlib.Path(IMAGE)
e = V.Emu(["--image", IMAGE, "--interactive", "--watch-pc", ",".join(hex(a) for a in WATCH)] + card, OUT / "port.log")
def rd(addr, n):
    return e.peek(addr, n)
def snap(tag):
    g = rd(0x80006914, 16)
    lst, start, total, used = (int.from_bytes(g[i:i + 4], "big") for i in (0, 4, 12, 8))
    starts = [int.from_bytes(b, "big") for b in [rd(0x46c2e580 + 4 * i, 4) for i in range(136)]]
    counts = [int.from_bytes(rd(0x46c75e88 + 2 * i, 2), "big") for i in range(136)]
    held = [(i, starts[i], counts[i]) for i in range(136) if counts[i]]
    rows = []
    for i, s, n in held:
        if i < 128:
            pages = [int.from_bytes(rd(lst + 2 * (s + k), 2), "big") for k in range(n)]
        else:
            base = lst + 2 * (i - 128 + 2) * 14602
            pages = [int.from_bytes(rd(base + 2 * k, 2), "big") for k in range(n)]
        runs = sum(1 for k in range(1, len(pages)) if pages[k] != pages[k - 1] + 1) + 1 if pages else 0
        rows.append(dict(slot=i, start=s, pages=n, first=pages[:3], last=pages[-1:], runs=runs))
    d = dict(tag=tag, list=hex(lst), slot_start_table=hex(start), total=total, used=used, free=total - used, held=rows)
    (OUT / f"{tag}.json").write_text(json.dumps(d, indent=1))
    print(tag, "total", total, "used", used, "free", total - used, "slots held", len(rows))
    for r in rows:
        print("  ", r)
try:
    h = e.cmd("hits").split()[2:]
    from collections import Counter, OrderedDict
    c = Counter(int(x.split(":")[1], 16) for x in h)
    print("hits during boot + load:", {WATCH.get(k, hex(k)): v for k, v in c.items()})
    seq = []
    for x in h:
        f = x.split(":")
        pc = int(f[1], 16)
        if not seq or seq[-1][0] != pc:
            seq.append([pc, 1, f[2], f[3]])
        else:
            seq[-1][1] += 1
    print("order:", [(WATCH.get(p, hex(p)), n, "d0=" + d0, "d1=" + d1) for p, n, d0, d1 in seq][:40])
    snap("after_load")
    print("call release slot 3:", e.cmd("call 0x40096300 3"))
    snap("after_release_slot3")
    h = e.cmd("hits").split()
    print("hits after load:", h[:2])
finally:
    e.close()
