#!/usr/bin/env python3
"""Negative controls for private-P upload isolation; no firmware input."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/p) for p in ('tools', 'tools/build', 'tools/perky', 'modules/perky')]
os.environ.setdefault('REMIX', 'perky-machine')
from perky_fragmented_image import merge_upload_records


def main():
    common = [(0x33da3, [1,2])]
    assert merge_upload_records({'A': common, 'B': common}) == {'A': common, 'B': common}
    result = merge_upload_records({'A': [(0x1fdf,[3])]+common,
                                   'B': [(0x1d9f,[4,5])]+common})
    assert result['A'] == [(0x1fdf,[3])]+common
    assert result['B'] == [(0x1d9f,[4,5])]+common
    # Equal virtual private addresses are distinct physical memories.
    assert merge_upload_records({'A': [(0x1fdf,[3])], 'B': [(0x1fdf,[4])]}) == {'A': [(0x1fdf,[3])], 'B': [(0x1fdf,[4])]}
    bad = [
        {'A': common, 'B': [(0x33da3,[9,2])]},
        {'A': common, 'B': [(0x33da4,[9,2])]},
        {'A': [], 'B': [(0x1fff,[1,2])]},
        {'A': [], 'B': [(0x2000,[1])]},
        {'A': [], 'B': [(0x3ffff,[1,2])]},
        {'A': [], 'B': [(0x1d9f,[1,2]), (0x1da0,[3])]},
        {'A': [], 'B': [(0x1d9f,[])]},
    ]
    for rows in bad:
        try:
            merge_upload_records(rows)
        except AssertionError:
            continue
        raise AssertionError(('bad upload accepted',rows))
    print('[PASS] private upload isolation, unchanged shared union, seven overlap/domain/drift negative controls')


if __name__ == '__main__':
    main()
