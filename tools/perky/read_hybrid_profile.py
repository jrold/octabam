#!/usr/bin/env python3
"""Read the probe's automatic card export: no CF METER or audio capture needed."""
import argparse
import json
import re
import struct
from pathlib import Path
from hybrid_profile import decode_profiler_dump


def read_export(path, build=None):
    raw = Path(path).read_bytes()
    if len(raw) < 84:
        raise ValueError('truncated profiling file')
    magic, version, size, sequence = struct.unpack_from('>4I', raw)
    if magic != 0x504b5032 or version != 2 or size != len(raw) or sequence & 1:
        raise ValueError('invalid profiling header/length/snapshot sequence')
    source_id = raw[16:84].split(b'\0', 1)[0].decode('ascii')
    if not re.fullmatch('[0-9a-f]{64}', source_id):
        raise ValueError('invalid probe source identity')
    if build is not None and source_id != build['hybrid_source_id']:
        raise ValueError('profile belongs to a different probe source build')
    profile = decode_profiler_dump(raw[84:])
    if profile['version'] != 2:
        raise ValueError('card export must contain v2 full-frame profiler')
    return {'source_id': source_id, 'sequence': sequence,
            'build_matched': build is not None, 'profile': profile,
            'status': 'DIAGNOSTIC_ONLY_HARDWARE_REVIEW_REQUIRED'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('profile', type=Path)
    ap.add_argument('--build', type=Path, required=True, help='BUILD.json for the exact tested image')
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    result = read_export(args.profile, json.loads(args.build.read_text()))
    text = json.dumps(result, indent=2) + '\n'
    if args.out:
        args.out.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
