#!/usr/bin/env python3
"""Prove the shipping manifest, the artifacts and the tree agree.

The brief's release-gate list asks for "no provenance mismatch between HEAD,
manifest and produced artifact". Nothing checked it.

What this gate can prove locally, and what it cannot, are different things,
and it says which is which rather than implying more than it knows:

  PROVEN HERE
    * every ``*_sha256=`` in the manifest matches the artifact it names;
    * ``git=`` resolves to a commit that exists in this repository;
    * ``tree=`` is one of clean/dirty;
    * if ``git=`` is HEAD and ``tree=clean``, the recorded provenance
      describes the current checkout.

  NOT PROVEN HERE
    * that re-running the build reproduces the artifact byte for byte.
      That needs the canary's inputs (a stock project on a card), which are
      not in the tree. The gate reports the comparison it *can* make and
      refuses to imply the one it cannot.

Exit 0 when nothing contradicts. Exit 1 on a mismatch, naming the field.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

# field -> the artifact whose bytes must hash to it
SHA_FIELDS = {
    'card_sha256': 'card_image_path',
    'midi_sha256': 'midi_updater_path',
}
MANIFEST_FIELD = 'manifest_path'


def read_manifest(path: pathlib.Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text().splitlines():
        m = re.match(r'^([a-z0-9_]+)=(.*)$', line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    # The manifest lives beside the artifacts, outside the tree: it carries
    # absolute-ish paths in the shipping copy and is regenerated per build.
    # Pick the manifest that actually CARRIES the artifact hashes. The canary
    # also writes a test manifest that has none -- preferring it would make this
    # gate skip its whole purpose and pass vacuously, which is the "audits
    # nothing" trap. So: choose by content, and refuse to pass on one that has
    # nothing to check.
    candidates = [
        ROOT / 'out' / 'PERKY2V_PERKY_TEST.txt',
        pathlib.Path.home() / 'Downloads' / 'PERKY2V_milestone_manifest.txt',
    ]
    checked: list[pathlib.Path] = []
    manifest = None
    for cand in candidates:
        if not cand.is_file():
            continue
        # Select on whether a manifest can actually be CHECKED -- it needs both
        # the hash AND the path it pins. The canary's own test manifest carries a
        # hash but no path, so choosing it skips the comparison and passes
        # vacuously. A substring test is not enough either: a comment mentioning
        # card_sha256 is not a recorded hash. Parse, then require the pair.
        f = read_manifest(cand)
        if any(k in f and f.get(p) for k, p in SHA_FIELDS.items()):
            manifest = cand
            checked.append(cand)
            break
    if manifest is None:
        # Distinguish "nothing has been built here" from "a manifest exists but
        # cannot evidence anything". The first is a SKIP -- a fresh checkout has
        # no artifact and no claim to check. The second is a FAILURE, because a
        # manifest that names no artifact hash is exactly the claim this gate
        # exists to refuse.
        present = [c for c in candidates if c.is_file()]
        if not present:
            print('  [SKIP] no shipping manifest here yet (build the canary first); '
                  'nothing to check')
            return 0
        raise SystemExit(
            'perky provenance: a manifest exists but carries no checkable hash.\n'
            '  found: ' + ', '.join(str(c) for c in present) + '\n'
            '  Each needs BOTH a *_sha256= hash and the *_path= it pins.'
            'this gate FAILS rather than skipping.')

    fields = read_manifest(manifest)
    if not fields:
        raise SystemExit(f'provenance: {manifest} has no key=value fields')

    bad: list[str] = []
    checked_hashes = 0
    print(f'  manifest: {manifest}')

    # 1. every recorded hash must match the artifact it names
    for sha_field, path_field in SHA_FIELDS.items():
        want = fields.get(sha_field)
        if not want:
            print(f'  [SKIP] {sha_field}: not recorded')
            continue
        raw = fields.get(path_field)
        if not raw:
            print(f'  [SKIP] {sha_field}: no {path_field} to check it against')
            continue
        art = pathlib.Path(raw).expanduser()
        if not art.is_file():
            print(f'  [SKIP] {sha_field}: {art} is not present')
            continue
        got = sha256(art)
        checked_hashes += 1
        if got == want:
            print(f'  {sha_field}: MATCHES {art.name}')
        else:
            bad.append(f'{sha_field}: {art.name} is {got}, manifest says {want}')
            print(f'  {sha_field}: MISMATCH against {art.name}')

    # 2. git= must name a commit this repository has
    g = fields.get('git')
    if g:
        try:
            resolved = subprocess.run(
                ['git', 'rev-parse', '--verify', f'{g}^{{commit}}'],
                cwd=ROOT, capture_output=True, text=True, check=True,
            ).stdout.strip()
            print(f'  git={g}: resolves to {resolved[:12]}')
        except subprocess.CalledProcessError:
            bad.append(f'git={g} does not resolve to a commit in this repository')
            print(f'  git={g}: DOES NOT RESOLVE')
    else:
        print('  [SKIP] git=: not recorded')

    # 3. tree= must be a known value
    t = fields.get('tree')
    if t not in (None, 'clean', 'dirty'):
        bad.append(f'tree={t!r} is neither clean nor dirty')
    elif t:
        print(f'  tree={t}')

    # 4. does the recorded revision describe THIS checkout?
    head = subprocess.run(['git', 'rev-parse', '--short=12', 'HEAD'],
                          cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain'],
                                cwd=ROOT, capture_output=True, text=True,
                                check=True).stdout.strip())
    if g and g.startswith(head[:len(g)]) and t == 'clean' and not dirty:
        print(f'  HEAD={head}: the manifest describes this checkout')
    else:
        # NOT a failure: the artifact is pinned by its hashes, and git= names
        # the commit the BUILD read. Report it so nobody reads more into it.
        print(f'  HEAD={head} (tree {"dirty" if dirty else "clean"}): the manifest '
              f'names git={g}, so it was built from a DIFFERENT revision.')
        print('            This is expected once work continues: the hashes above '
              'pin the artifact, and git= names the tree it came from.')

    if checked_hashes == 0:
        bad.append('no artifact hash could be checked, so nothing was proven -- a '
                   'manifest names an artifact by its *_sha256= field')

    if bad:
        for b in bad:
            print(f'  [FAIL] {b}')
        raise SystemExit(f'perky provenance: {len(bad)} mismatch(es)')

    print(f'  [PASS] {checked_hashes} artifact hash(es) match; manifest and recorded '
          f'revision do not contradict')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
