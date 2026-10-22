"""placement_boundary_noop and placement_v4_merge_eligible in assembly.

Applied after generate_cf_placement_asm, whose layout exports the assembly
(modules/perky/cf_placement_predicates.s) uses. Both C predicates are pinned
by the SHA-256 of their text and renamed *_c; they stay in the unit as the
reference bodies, and the exported names become the assembly. Neither is an
oracle seam; both only read state.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = (('pkplacementpred', ROOT / 'modules/perky/cf_placement_predicates.s'),)

PINNED = (
    ('int __attribute__((noinline)) placement_boundary_noop(unsigned tr,const uint32_t *input,int trig)\n',
     '186e2350660c0d84692aafa39f6dc3a2d01fd132325d52e1b51da12a2584623a'),
    ('static inline int placement_v4_view(const pk4_assets*a,uint32_t want)\n',
     '6cbc7e36d049cda5b0215def719902422161c4302e6dc1183f5ad1d14d0bc51e'),
    ('int __attribute__((noinline)) placement_v4_merge_eligible(const uint32_t *input)\n',
     '03b3828f643637c479fdc73b46ac14d0df824825cec1fd34c1cd88969a673136'),
)
RENAMES = (
    ('int __attribute__((noinline)) placement_boundary_noop(unsigned tr,const uint32_t *input,int trig)\n{',
     'int placement_boundary_noop(unsigned tr,const uint32_t *input,int trig);\n'
     '/* PKFM31: the exported predicate is assembly (cf_placement_predicates.s). */\n'
     'int __attribute__((noinline)) placement_boundary_noop_c(unsigned tr,const uint32_t *input,int trig);\n'
     'int __attribute__((noinline)) placement_boundary_noop_c(unsigned tr,const uint32_t *input,int trig)\n{'),
    ('int __attribute__((noinline)) placement_v4_merge_eligible(const uint32_t *input)\n{',
     'int placement_v4_merge_eligible(const uint32_t *input);\n'
     '/* PKFM31: the exported predicate is assembly (cf_placement_predicates.s). */\n'
     'int __attribute__((noinline)) placement_v4_merge_eligible_c(const uint32_t *input);\n'
     'int __attribute__((noinline)) placement_v4_merge_eligible_c(const uint32_t *input)\n{'),
)


def transform(work, source_path):
    text = Path(source_path).read_text()
    assert 'placement_export_layout' in text, 'apply the placement kernel first (its layout exports)'
    for head, digest in PINNED:
        assert text.count(head) == 1, ('predicate anchor changed', head)
        start = text.index(head)
        body = text[start:text.index('\n}\n', start) + 3]
        assert hashlib.sha256(body.encode()).hexdigest() == digest, \
            ('predicate C changed; re-derive cf_placement_predicates.s', head)
    for old, new in RENAMES:
        assert text.count(old) == 1, ('predicate anchor changed', old[:80])
        text = text.replace(old, new, 1)
    target = Path(work) / 'placement-predicates-asm.c'
    target.write_text(text)
    return target
