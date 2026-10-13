#!/usr/bin/env python3
"""Emit the Perky DSP program as placeable shards.

The program is one 3051-word code stream, which is why it can only be placed in
one contiguous harvested run. With SPRING REV, DARK REV and LO-FI kept, the
largest run is PLATE's 594 words, so the program must be split.

`build_bus.py`'s `place(words, start)` already takes one stream and a start
address, and the machinery around it (`runs`, per-run cursors, `_end_of_run`,
`_written`) is already multi-run -- the constraint is only that `place()` is
called once with the whole program. This tool produces what a loop over it
needs: one word stream and one origin per shard.

Two emissions, and the distinction matters:

  * at each shard's MONOLITH origin, the bytes must equal the monolith's bytes
    for that source range. This proves the slice-and-rewrite is faithful.
  * at each shard's ASSIGNED origin (across the two local runs and the five
    shared tails), the extents must be exact and `dsp_asm` must report no
    sizing drift. This proves it places.

Byte-identity does NOT hold at the assigned origins, and should not: internal
label addresses move. Only the first emission is a byte-identity claim.

The one trap, which cost a false start: rewriting only references in the
`op label` form is not enough. Labels also appear as immediates, `do` loop
targets and memory-reference operands, so the rewrite is token-scoped over
every non-comment line. A line-form rewrite silently leaves references
unresolved, and the assembler then fails -- or resolves something by accident.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path[:0] = ["tools", "tools/build", "tools/perky", "modules/perky"]

import build_bus as B  # noqa: E402
import all_fx_layout as L  # noqa: E402

MONOLITH_ORG = 0x1000
BEGIN = re.compile(r"; ===== BEGIN (\S+) =====")
END = re.compile(r"; ===== END (\S+) =====")
LABEL_DEF = re.compile(r"(?m)^([A-Za-z_][A-Za-z0-9_]*):")
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def load_source(multi_asm: pathlib.Path, tag="A") -> str:
    return multi_asm.read_text().replace("@CONT@", {"A": "$000426", "B": "$000221"}[tag])


def slice_pieces(src: str, whole_len: int, syms: dict):
    """[(name, monolith_start, monolith_end, text, first_offset)] in address order."""
    begins = [(m.start(), m.group(1)) for m in BEGIN.finditer(src)]
    ends = {m.group(1): m.start() for m in END.finditer(src)}
    label_off: dict[str, int] = {}
    for m in LABEL_DEF.finditer(src):
        label_off.setdefault(m.group(1), m.start())

    pieces = [(o, ends[n], n) for o, n in begins if n in ends and ends[n] > o]

    def piece_of(off):
        for a, b, n in pieces:
            if a <= off < b:
                return n
        return None

    starts: dict[str, int] = {}
    for lbl, addr in syms.items():
        off = label_off.get(lbl)
        if off is None:
            continue
        p = piece_of(off)
        if p and (p not in starts or addr < starts[p]):
            starts[p] = addr
    if not starts:
        sys.exit("emit_shards: no marked piece defines a label -- markers gone?")

    seq = sorted(starts.items(), key=lambda t: t[1])
    out = []
    for i, (n, a) in enumerate(seq):
        b = seq[i + 1][1] if i + 1 < len(seq) else MONOLITH_ORG + whole_len
        off = next(o for o, x in begins if x == n)
        out.append((n, a, b, src[off:ends[n]], off))
    return out


def externals(slice_src: str, syms: dict) -> set[str]:
    """Label tokens this slice references but does not define."""
    defined = set(LABEL_DEF.findall(slice_src))
    refs = set()
    for line in slice_src.splitlines():
        if line.lstrip().startswith(";"):
            continue
        for tok in TOKEN.findall(line):
            if tok in syms and tok not in defined:
                refs.add(tok)
    return refs


def rewrite(slice_src: str, syms: dict, mapper) -> str:
    sh = slice_src
    for t in sorted(externals(slice_src, syms), key=len, reverse=True):
        sh = re.sub(r"\b" + re.escape(t) + r"\b", "$%06x" % mapper(syms[t]), sh)
    return sh


def emit(multi_asm: pathlib.Path, tag="A"):
    """Return (pieces, monolith_words, assigned)."""
    src = load_source(multi_asm, tag)
    whole, syms = B.assemble_syms(src, MONOLITH_ORG, "mono")
    pieces = slice_pieces(src, len(whole), syms)

    # Shared P is ONE backing memory for both cores. A shared shard must
    # never refer into payload-relative private P. Only the seam and shards
    # called exclusively by that seam may occupy the local donor records.
    owner=lambda addr: next((n for n,a,b,_,_ in pieces if a<=addr<b),None)
    incoming={n:set() for n,_,_,_,_ in pieces}
    for n,_,_,text,_ in pieces:
        for label in externals(text,syms):
            target=owner(syms[label])
            if target is not None:incoming[target].add(n)
    seam='synth_seam_glue.asm'
    local_allowed={seam}|{n for n,callers in incoming.items() if callers=={seam}}
    local=L.local_p_spans(tag)
    # Reserve 48 private Plate words for the startup clear that protects tails.
    spans=((local[0][0],local[0][1]-48),local[1])+L.SAFE_SHARED_P_SPANS
    cursors=[a for a,b in spans]
    dest={}
    for n,a,b,_,_ in sorted(pieces,key=lambda p:-(p[2]-p[1])):
        indices=range(len(spans)) if n in local_allowed else range(2,len(spans))
        if n==seam:indices=range(2)
        hit=next((i for i in indices if cursors[i]+b-a<=spans[i][1]),None)
        if hit is None:raise ValueError(f'{n}: no core-safe shard placement')
        dest[n]=cursors[hit];cursors[hit]+=b-a
    private={n for n,addr in dest.items() if addr<0x30000}
    assert all(incoming[n] <= private for n in private), 'shared-to-private reference'

    def final(addr: int) -> int:
        for n, a, b, _, _ in pieces:
            if a <= addr < b:
                return dest[n] + (addr - a)
        return addr

    return pieces, whole, dest, final, syms


def check(multi_asm: pathlib.Path, verbose: bool) -> int:
    pieces, whole, dest, final, syms = emit(multi_asm)
    total = 0
    bad = []

    for n, a, b, text, _ in pieces:
        extent = b - a
        # (1) at the MONOLITH origin: must be byte-identical.
        mono_text = rewrite(text, syms, lambda x: x)
        w_mono, _ = B.assemble_syms(mono_text, a, "mono_" + n)
        want = whole[a - MONOLITH_ORG:b - MONOLITH_ORG]
        if w_mono != want:
            d = [i for i in range(min(len(w_mono), len(want))) if w_mono[i] != want[i]]
            bad.append(f"{n}: monolith-origin bytes differ at {d[:4]}")
        if len(w_mono) != extent:
            bad.append(f"{n}: monolith extent {len(w_mono)} != {extent}")
        # (2) at the ASSIGNED origin: extents exact.
        w_asg, _ = B.assemble_syms(rewrite(text, syms, final), dest[n], "asg_" + n, strict_layout=True)
        if len(w_asg) != extent:
            bad.append(f"{n}: assigned extent {len(w_asg)} != {extent}")
        total += extent
        if verbose:
            print(f"  {n:44s} mono 0x{a:05x} -> 0x{dest[n]:05x}  {extent:4d} words")

    # (3) THE CALL GRAPH. Every external reference was rewritten to an
    # absolute $hex; check each one names a FINAL address that lies inside some
    # shard. This is the "disassemble what you assemble / verify actual
    # branches, calls and ranges" requirement, checked at the source level:
    # the encoding is already pinned by check (1), so what remains to verify is
    # that no call or jump aims outside the placed program.
    spans = [(dest[n], dest[n] + (b - a) - 1, n) for n, a, b, _, _ in pieces]

    def owner(addr):
        for lo, hi, n in spans:
            if lo <= addr <= hi:
                return n
        return None

    bad_targets = []
    n_targets = 0
    for n, a, b, text, _ in pieces:
        refs = externals(text, syms)
        n_targets += len(refs)
        for t in refs:
            fa = final(syms[t])
            if owner(fa) is None:
                bad_targets.append((n, t, hex(fa)))
    if bad_targets:
        for n, t, fa in bad_targets[:6]:
            bad.append(f"{n}: target {t} -> {fa} is OUTSIDE every shard")

    print(f"  pieces: {len(pieces)}   words: {total}   monolith: {len(whole)}")
    local = sum(1 for n, _, _, _, _ in pieces if dest[n] < 0x30000)
    print(f"  in LOCAL P: {local}   in SHARED tails: {len(pieces) - local}")
    print(f"  cross-piece reference targets checked: {n_targets}"
          f"   outside every shard: {len(bad_targets)}")
    if total != len(whole):
        bad.append(f"total {total} != monolith {len(whole)}")
    if bad:
        for b in bad:
            print(f"  FAIL {b}")
        return 1
    print("  monolith-origin bytes identical for every piece: True")
    print("  assigned-origin extents exact for every piece: True")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--multi-asm", type=pathlib.Path,
                    default=pathlib.Path("out/perky/light2/multi.asm"))
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if not a.multi_asm.exists():
        sys.exit(f"emit_shards: {a.multi_asm} not found -- build the payload first")
    return check(a.multi_asm, a.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
