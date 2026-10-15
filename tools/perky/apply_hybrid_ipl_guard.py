#!/usr/bin/env python3
"""Apply/revert the authorized SR operand in the frozen local hybrid MAIN.

This is a post-link two-byte operand write, not a rebuild or flash packager.
The original input is never overwritten. No Elektron image bytes are embedded.
"""
import argparse
import hashlib
import json
from pathlib import Path

BASE = 0x40000400
INSTRUCTION = 0x400a1e64
ORIGINAL_SHA = 'a2d6915bc71a97d63f44e223e558cc4941d52113708f7ba92a57bdd669339b40'
GUARDED_SHA = '055cced1bb5319c35ee7d4708359a60a3e207a69d73711d2d536beadca060fbe'

def digest(data): return hashlib.sha256(data).hexdigest()

def transform(data, *, revert=False):
    expected = GUARDED_SHA if revert else ORIGINAL_SHA
    assert digest(data) == expected, 'input is not the qualified frozen image'
    offset = INSTRUCTION - BASE
    old, new = (0x2300, 0x2200) if revert else (0x2200, 0x2300)
    assert int.from_bytes(data[offset:offset+2], 'big') == 0x46fc
    assert int.from_bytes(data[offset+2:offset+4], 'big') == old
    changed = bytearray(data)
    changed[offset+2:offset+4] = new.to_bytes(2, 'big')
    delta = [i for i,(a,b) in enumerate(zip(data,changed)) if a != b]
    assert delta == [offset+2] and len(changed) == len(data)
    assert digest(changed) == (ORIGINAL_SHA if revert else GUARDED_SHA)
    return bytes(changed)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--revert', action='store_true')
    args = parser.parse_args()
    assert args.input.resolve() != args.output.resolve(), 'preserve the input'
    result = transform(args.input.read_bytes(), revert=args.revert)
    if args.output.exists():
        assert args.output.read_bytes() == result, 'refusing to overwrite a different artifact'
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(result)
    print(json.dumps({'input_sha256':digest(args.input.read_bytes()),
        'output_sha256':digest(result),'instruction_address':hex(INSTRUCTION),
        'operand_address':hex(INSTRUCTION+2),'operand_span_bytes':2,
        'actual_changed_bytes':1,'reverted':args.revert,'flash_authorized':False},indent=2))
