"""Assembly safety checks shared by the Noise Hat execution gates."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DIS = ROOT / 'vendor/dsp56300/build/source/disassemble/dsp56kDisassemble'
LINE = re.compile(r'^([0-9a-f]{6}): (\S+)(?:\s+.*?)?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$')


def audit_source(source: str) -> None:
    labels = re.findall(r'^(\w+):', source, re.M)
    collisions = [(a, b) for a in labels for b in labels if a != b and b.startswith(a)]
    if len(labels) != len(set(labels)) or collisions:
        raise SystemExit(f'Noise Hat label resolver hazard: {collisions}')
    for line in source.splitlines():
        match = re.search(r'\blua\s+\(r\d([+-])\$([0-9a-f]+)\)', line)
        if match:
            value = int(match[2], 16) * (-1 if match[1] == '-' else 1)
            if not -64 <= value <= 63:
                raise SystemExit(f'Noise Hat LUA displacement outside chip range: {line}')


def audit_binary(listing: str, binary: Path, org: int) -> None:
    decoded = subprocess.run([str(DIS), '-in', str(binary), '-pc', f'{org:x}', '-le', '-nops'],
                             capture_output=True, text=True, check=True).stdout
    binary.with_suffix('.disasm').write_text(decoded)
    parse = lambda text: {int(m[1], 16): m[2] for m in map(LINE.match, text.splitlines()) if m}
    typed, actual = parse(listing), parse(decoded)
    if not typed or not actual:
        raise SystemExit('Noise Hat assembly/disassembly listing is empty')
    # Explicit long JSR is decoded as JSR. No MPY -> MPYSU exception: every
    # signed site in these candidates must really encode a signed multiply.
    bad = [(pc, op, actual.get(pc)) for pc, op in typed.items()
           if actual.get(pc) != ('jsr' if op == 'jsrl' else op)]
    if bad:
        raise SystemExit(f'Noise Hat assembler round-trip mismatch: {bad[:12]}')
