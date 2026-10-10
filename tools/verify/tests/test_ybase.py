"""The shared-window base substitution matches whole literals only."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from remix import ybase  # noqa: E402

BASE = ybase.LITERAL
LONGER = BASE + "0"


class SubstituteTests(unittest.TestCase):
    def test_whole_literal_is_rewritten(self):
        src = f"        move    y:>{BASE},a\n        move    #>{BASE},x0\n"
        out = ybase.substitute(src, 0x38000)
        self.assertEqual(out, "        move    y:>$38000,a\n        move    #>$38000,x0\n")

    def test_longer_literal_is_unchanged(self):
        for tail in "0123456789abcdefABCDEF":
            src = f"        move    #>{BASE}{tail},x0\n"
            self.assertEqual(ybase.substitute(src, 0x38000), src)

    def test_mixed_source_rewrites_only_the_whole_literal(self):
        src = f"move y:>{BASE},a\nmove #>{LONGER},b\nmove y:>{BASE}\n"
        want = f"move y:>$38000,a\nmove #>{LONGER},b\nmove y:>$38000\n"
        self.assertEqual(ybase.substitute(src, 0x38000), want)

    def test_count_ignores_longer_literal(self):
        self.assertEqual(ybase.count(f"{BASE} {LONGER} {BASE},"), 2)

    def test_check_reports_a_wrong_count(self):
        self.assertIsNone(ybase.check("SEND", BASE))
        self.assertIn("expected 1", ybase.check("SEND", BASE + BASE))
        self.assertIn("no expected", ybase.check("NOPE", BASE))


if __name__ == "__main__":
    unittest.main()
