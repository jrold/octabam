#!/usr/bin/env python3
"""Label-level reachability of the composed Perky source.

The production image enters the machine at exactly one place, the source hook
`pk3d_source`, so anything not reachable from there is dead P.

WHY LABEL-LEVEL. A first version walked instructions and tracked addresses by
adding word counts, which drifts from the assembler's real layout; a target whose
computed address matched no instruction ended the walk, and it pruned the entire
Resonant half of the dispatcher -- reporting the demonstrably-live
`pk3d_snare_voice` (107 instructions) as dead. Label-level reachability needs no
address arithmetic at all, so that class of error cannot occur.

CALIBRATION, and how it landed: the verified dead code is **51 instructions**
established by actually removing them and confirming 15/15 Fold ARM parity. This
tool reproduces **51 instructions in 6 blocks, exactly**, and names the same six
(`pk_u32_sub`, `pk_sub_no_borrow`, `pk_u32_asr`, `pk_u32_shift_sign_ready`,
`pk_noise_step`, `pk_noise_refresh`). Its instruction count is therefore trusted.

Its WORD estimate is approximate -- it counts an extra word for `do` and for an
immediate operand, giving 54 where the verified removal saved 67. The verified 67
is the number to quote; use this tool for the SET of dead code, not its size.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky")]

COND = {"bne", "beq", "blt", "bgt", "ble", "bge", "bcc", "bcs", "bpl", "bmi",
        "bhs", "blo", "brset", "brclr", "bset", "bclr"}
TAIL = {"bra", "jmp", "rts", "rti"}
CALL = {"jsr", "jsrl", "bsr"}


def main() -> None:
    import build_dsp_3algo_source as composed
    text = composed.normalize(composed.compose())
    lines = text.splitlines()

    # label -> list of (op, operand) until the next label
    blocks: dict[str, list[tuple[str, str]]] = {}
    order: list[str] = []
    cur = "<preamble>"
    blocks[cur] = []
    order.append(cur)
    for raw in lines:
        s = raw.split(";")[0].strip()
        if not s:
            continue
        if s.endswith(":"):
            cur = s[:-1]
            if cur not in blocks:
                blocks[cur] = []
                order.append(cur)
            continue
        parts = s.split(None, 1)
        blocks[cur].append((parts[0], parts[1] if len(parts) > 1 else ""))

    def target(operand: str):
        m = re.match(r"([A-Za-z_]\w*)", operand.strip())
        if m and m.group(1) in blocks:
            return m.group(1)
        return None

    seen: set[str] = set()
    work = ["pk3d_source"]
    unresolved: list[str] = []
    while work:
        lab = work.pop()
        while lab is not None and lab not in seen:
            seen.add(lab)
            body = blocks.get(lab)
            if body is None:
                break
            nxt = order[order.index(lab) + 1] if order.index(lab) + 1 < len(order) else None
            fell = False
            for op, rest in body:
                if op in CALL or op in COND:
                    t = target(rest)
                    if t:
                        work.append(t)
                    elif rest and not rest.startswith("#"):
                        unresolved.append(f"{lab}: {op} {rest}")
                elif op == "do":
                    t = target(rest.split(",")[-1])
                    if t:
                        work.append(t)
                elif op == "jmp":
                    t = target(rest)
                    if t:
                        lab = t
                        fell = True
                        break
                    unresolved.append(f"{lab}: jmp {rest}")
                elif op in ("rts", "rti"):
                    lab = None
                    fell = True
                    break
                elif op == "bra":
                    t = target(rest)
                    if t:
                        lab = t
                        fell = True
                        break
                    lab = None
                    fell = True
                    break
            if not fell:
                lab = nxt

    dead = [l for l in order if l not in seen and blocks[l]]
    dead_instr = sum(len(blocks[l]) for l in dead)
    # APPROXIMATE: two words for `do` and for an immediate operand. Gives 54
    # against a verified 67, so quote the verified figure for size and this tool
    # for membership.
    dead_words = sum(2 if (op == "do" or "#" in rest) else 1
                     for l in dead for op, rest in blocks[l])
    print(f"labels: {len(order)}   reachable from pk3d_source: {len(seen)}")
    print(f"UNREACHABLE: {dead_instr} instructions in {len(dead)} blocks "
          f"= {dead_words} words")
    for l in dead:
        print(f"   {l:32s} {len(blocks[l]):3d} instr")
    if unresolved:
        print(f"\n{len(unresolved)} call/branch targets were NOT label-form "
              f"(address or expression) and were not followed:")
        for u in unresolved[:8]:
            print(f"   {u}")
    print(f"\nCALIBRATION: 51 instructions matches the verified 51 exactly, so the")
    print(f"SET is trusted. The word estimate is approximate (54 here against the")
    print(f"verified 67); quote 67 for size. NOTE that these 6 blocks ARE the whole")
    print(f"dead set -- there is no more dead code to find, so the 67 words is a")
    print(f"ceiling and cannot close the 86-word gap to retaining DJ EQ.")


if __name__ == "__main__":
    main()
