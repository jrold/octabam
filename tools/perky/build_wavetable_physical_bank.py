#!/usr/bin/env python3
"""Place a candidate compressed wave bank only in mapped Octatrack Y ranges.

This is a placement candidate and test-data writer, not a firmware installer.
Local FX arenas and shared upper RAM need retirement/initialization gates before
these allocations become production claims. Bank is identical on both cores;
shared words must be loaded once and remain read-only after installation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
import wavetable_asset_codec as codec
import simple_drum_tables as packed
from build_wavetable_asset_bank import IDS
from build_wavetable_cached_source import DIRECTORY

# Leave Y:$a020..$bfff out of the table bank for later state/ring allocation.
# This is a candidate reserve, not an assertion that every persistent ring fits.
ARENAS = ((0x1000, 0xA020), (0x38013, 0x40000))


def build(source, out, encoding='direct'):
    assert encoding in ('second-difference32', 'direct')
    out.mkdir(parents=True, exist_ok=True)
    cursors = [low for low, high in ARENAS]
    directory, records, assets = [], [], []
    for identity in IDS:
        raw = (source / f'asset_{identity:08x}.bin').read_bytes()
        assert len(raw) == 4096
        if encoding == 'second-difference32':
            asset = codec.pack(struct.unpack('<2048h', raw), 32)
            words, header_words = asset.words, 65
        else:
            words, header_words = packed.pack_u16(struct.unpack('<2048h', raw)), 0
        for arena, (low, high) in enumerate(ARENAS):
            if cursors[arena] + len(words) <= high:
                address = cursors[arena]
                cursors[arena] += len(words)
                break
        else:
            raise ValueError('wave bank does not fit declared candidate arenas')
        directory += [identity & 65535, identity >> 16, address, address + header_words]
        records.append((address, tuple(words)))
        assets.append({'identity': identity, 'header': address, 'data': address + header_words,
                       'words': len(words), 'sha256': hashlib.sha256(raw).hexdigest()})
    records.insert(0, (DIRECTORY, tuple(directory)))
    occupied = sorted((base, base + len(words)) for base, words in records)
    assert all(end <= next_base for (_, end), (next_base, _) in zip(occupied, occupied[1:]))
    assert DIRECTORY + len(directory) <= 0xC50
    # No bank record may cross the absent local-Y area or a live boot mailbox.
    for base, words in records[1:]:
        assert any(low <= base < base + len(words) <= high for low, high in ARENAS)
    data = ''.join(f'Y {address:x} ' + ' '.join(f'{word:06x}' for word in words) + '\n'
                   for address, words in records)
    (out / 'bank.data').write_text(data)
    report = {'schema': 'perky-wavetable-physical-candidate-v1', 'bank_words': sum(len(w) for _, w in records),
              'encoding': encoding, 'directory': DIRECTORY, 'directory_words': len(directory), 'arenas': ARENAS,
              'arena_words': [at - low for at, (low, high) in zip(cursors, ARENAS)],
              'assets': assets, 'physical_installation_qualified': False,
              'data_sha256': hashlib.sha256(data.encode()).hexdigest()}
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report, data


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=ROOT / 'out/perky/all-voice-assets')
    ap.add_argument('--out', type=Path, default=ROOT / 'out/perky/wavetable-physical-bank')
    ap.add_argument('--codec', choices=('direct', 'second-difference32'), default='direct')
    args = ap.parse_args()
    result, _ = build(args.source, args.out, args.codec)
    print(f"Wavetable placement candidate: {result['bank_words']} words; local/shared {result['arena_words']}; installation pending")
