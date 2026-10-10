"""A skip is printed as `[SKIP]`, the form acceptance.py and check_shards.py
recognise; other spellings exit 0 as a pass."""
import pathlib
import re
import unittest

VERIFY = pathlib.Path(__file__).resolve().parents[1]
# a printed string whose first word is a skip in another spelling, or
# "-- skipped" ending a printed line
OTHER = re.compile(r"""print\(\s*f?["']\s*(?:SKIPPED\b|SKIP\b(?!:)|\[skip\]|\[Skip\]|Skipped\b)"""
                   r"""|print\(.*--\s*skipped["']\)""")


class SkipSpelling(unittest.TestCase):
    def test_no_gate_prints_a_skip_the_runners_miss(self):
        bad = [f"{p.name}:{n}: {line.strip()}"
               for p in sorted(VERIFY.glob("*.py"))
               for n, line in enumerate(p.read_text().splitlines(), 1)
               if OTHER.search(line)]
        self.assertEqual(bad, [], "print `[SKIP]` instead:\n" + "\n".join(bad))

    def test_pattern_catches_the_known_spellings(self):
        for s in ('print(f"  SKIPPED: x")', 'print(f"  [skip] midi: x")',
                  'print(f"  {m} not placed -- skipped")'.replace("{m} ", "")):
            self.assertTrue(OTHER.search(s), s)


if __name__ == "__main__":
    unittest.main()
