#!/usr/bin/env python3
"""Build a local DSP specialization experiment from the preserved PERKY4S.

No flash wrapper. A runs stock sources; B retains one production-admitted
oscillator. A separate paired harness prices two independent B contexts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/p) for p in ('tools', 'tools/build', 'tools/perky', 'modules/perky')]
os.environ.setdefault('REMIX', 'perky-machine')
import ab_records as A
import all_fx_layout as L
import build_four_payload as payload
import perky_dsp_b_specialization as S
import perky_fragmented_image as F
import perky_image as P
import repack_machine_loader as loader
from remix import registry, stock


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(work, baseline):
    work.mkdir(parents=True, exist_ok=True)
    payload.build(work)
    assert (work/'multi.asm').read_bytes() == (baseline/'multi.asm').read_bytes(), 'baseline renderer source drift'
    pristine = (ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    original = (baseline/'fragmented-normal.bin').read_bytes()
    image = bytearray(original)
    for tag, c in P.PAY.items():
        rr, _ = A.records(pristine, *c['payload'])
        recs, _ = A.records(image, *c['payload'])
        old, _, entry = F.plan(work/'multi.asm', tag)
        # Refuse a mismatched preserved baseline before changing its code.
        for addr, words in old:
            if addr < 0x2000:
                assert [A.rd(image, A.word_at(recs, 0, addr+i)) for i in range(len(words))] == words
        site = {'A': 0x39c, 'B': 0x1a2}[tag]
        assert A.rd(image, A.word_at(recs, 0, site+1)) == entry
        # Reconstruct precisely the generic installer's pre-fragment hooks.
        A.wr(image, A.word_at(recs, 0, site+1), L.local_p_spans(tag)[0][0])
        for addr in range(0x40, 0x4a if tag == 'A' else 0x4b):
            A.wr(image, A.word_at(recs, 0, addr), A.rd(pristine, A.word_at(rr, 0, addr)))
        if tag == 'B':
            # The generic PERKY builder already grows low Y by moving B's
            # mailbox down 256 words. Reproduce that clear geometry too.
            for addr, value in ((0x41, 0x8100), (0x43, 0x3f00), (0x45, 0x37f00)):
                A.wr(image, A.word_at(recs, 0, addr), value)
        end = max(addr+n for space, addr, n, _ in rr if space == 0 and addr < 0x2000)
        assert end == S.PRIVATE_TAILS[tag][0], (tag, 'stock private P high-water drift', hex(end))
    control, control_records, _ = F.install(bytes(image), work/'multi.asm')
    assert control == original, 'default fragmented installer changed the preserved baseline'
    saved_records = json.loads((baseline/'p-records.json').read_text())
    assert json.loads(json.dumps(control_records)) == saved_records, 'default shared uploads changed'
    normal, appended, ledgers = F.install(bytes(image), work/'multi.asm', planner=S.plan)
    image = bytearray(normal)
    # Remove A's oscillator source hook, restoring both displaced stock words.
    ar, _ = A.records(image, *A.PAYLOAD_A)
    sr, _ = A.records(pristine, *A.PAYLOAD_A)
    for addr in (0x39c, 0x39d):
        A.wr(image, A.word_at(ar, 0, addr), A.rd(pristine, A.word_at(sr, 0, addr)))
    normal = bytes(image)
    normal_path = work/'fragmented-normal.bin'
    normal_path.write_bytes(normal)
    (work/'p-records.json').write_text(json.dumps(appended, indent=2)+'\n')
    y, layout = P.load_tables(work)
    x = P.load_state_init(work, layout)
    for tag, c in P.PAY.items():
        raw, _ = P.extend_upload(normal, tag, y, x, P.extra_state_init(layout),
                                 P.load_extra_y_init(work, layout), appended[tag])
        (work/f'dsp-{tag}.upload.bin').write_bytes(raw)
        rr, _ = A.records(pristine, *c['payload'])
        recs, _ = A.records(raw, A.BASE, len(raw))
        for addr, words in S.plan(work/'multi.asm', tag)[0]:
            assert [A.rd(raw, A.word_at(recs, 0, addr+i)) for i in range(len(words))] == words
        for effect, (addr, count) in stock.p_spans(tag).items():
            if effect in ('PLATE REV', 'COMPRESSOR'):
                continue
            assert [A.rd(raw, A.word_at(recs, 0, addr+i)) for i in range(count)] == [A.rd(pristine, A.word_at(rr, 0, addr+i)) for i in range(count)], (tag, effect)
            effect_id = registry.modules()[effect].menu.fx2_id
            for base in (0x215, 0x235):
                assert A.rd(raw, A.word_at(recs, 1, base+effect_id)) == A.rd(pristine, A.word_at(rr, 1, base+effect_id)), (tag, effect, 'dispatch')
        if tag == 'A':
            assert not any(a == S.PRIVATE_TAILS['B'][0] for a, w in appended[tag]), 'B-private code leaked into A'
    main = work/'fragmented-mainos.bin'
    platform = work/'platform'
    platform.mkdir(exist_ok=True)
    for name in ('layout.json', 'runtime.raw', 'runtime.elf', 'table.inc', 'blob0.bin'):
        source = baseline/'platform'/name
        if not source.exists():
            source = baseline/'platform-loader'/name
        shutil.copy2(source, platform/name)
    loader.build(normal_path, work, main, platform_dir=platform,
                 work=work/'platform-loader', p_records=appended)
    subprocess.run([sys.executable, str(ROOT/'tools/verify/verify_perky_machine_boot.py'),
                    '--image', str(main), '--packed', str(work), '--platform', str(platform),
                    '--platform-work', str(work/'platform-loader'), '--normal-image', str(normal_path),
                    '--p-records', str(work/'p-records.json')], cwd=ROOT, check=True)
    shared = {r['start']: r for rows in ledgers.values() for r in rows if r['start'] >= 0x30000}
    report = dict(schema='perky-dsp-b-specialization-v1', hardware_validated=False,
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  baseline_normal_sha256=sha(baseline/'fragmented-normal.bin'),
                  default_installer_baseline_identical=True,
                  main_sha256=sha(main), stock_sha256=hashlib.sha256(pristine).hexdigest(),
                  candidate_private_tails=S.PRIVATE_TAILS, guard_words=S.GUARD_WORDS,
                  cores=ledgers, shared_capacity=L.shared_p_capacity(),
                  shared_words=sum(r['length'] for r in shared.values()),
                  shared_free=L.shared_p_capacity()-sum(r['length'] for r in shared.values()),
                  second_context_words=S.CONTEXT_WORDS, context_bank=[S.BANK_BASE, S.BANK_BASE+S.CONTEXT_WORDS],
                  limitations=['Private tails and upper guards require physical validation.',
                               'A source hook is stock; B production admission is still T1 only.',
                               'Paired experiment enters the source seam through a harness, not stock T2 dispatch.',
                               'Boot readback verifies ColdFire uploads, not simultaneous hardware execution.'])
    report['source_sha256'] = {str(path.relative_to(ROOT)):sha(path)
                             for folder in ('modules/perky','tools/perky','tools/build','tools/verify')
                             for path in sorted((ROOT/folder).glob('*'))
                             if path.is_file() and path.suffix in ('.py','.asm','.c','.cpp','.h','.s')}
    report['tool_sha256'] = {str(path.absolute().relative_to(ROOT)):sha(path)
                            for path in (F.B.DIS,F.B.DISASM,ROOT/'out/emu/ot_emu')}
    report['source_diff_sha256'] = hashlib.sha256(subprocess.check_output(['git','diff','HEAD'],cwd=ROOT)).hexdigest()
    (work/'placement.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'[PASS] specialized uploads/boot/retained FX bytes; shared free {report["shared_free"]}; B-private kernels 557 words')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, default=ROOT/'out/perky/hybrid/dsp-b-feasibility')
    p.add_argument('--baseline', type=Path, default=ROOT/'out/perky/hybrid/baseline/reproduction')
    args = p.parse_args()
    build(args.work.resolve(), args.baseline.resolve())


if __name__ == '__main__':
    main()
