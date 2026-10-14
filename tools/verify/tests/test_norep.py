"""build_bus refuses a `rep` in a DSP source; a `do` loop and a comment are fine.
tools/build/norep.py, called by build_bus.assemble_syms."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/build"))
sys.path.insert(0, str(ROOT / "tools"))
import norep  # noqa: E402


class Rep(unittest.TestCase):
    def test_a_planted_rep_is_refused(self):
        for line in ("        rep     #$18", "        rep     x0", "lab:    rep #8", "\trep\t#$7f ; a comment"):
            with self.assertRaises(SystemExit) as c:
                norep.refuse_rep(f"init:\n        clr a\n{line}\n        div x0,a\nproc:\n", "fixture")
            self.assertIn("rep in a DSP source (fixture)", str(c.exception))
            self.assertIn("line 3", str(c.exception))

    def test_do_loops_comments_and_names_are_not(self):
        norep.refuse_rep("""init:
        do      #$18,>norep_x_01
        div     x0,a
norep_x_01:
        ; rep #8 in a comment
        move    x:(r1)+,x0   ; rep is gone
repeat: nop
        reprieve
""")

    def test_the_modules_carry_none(self):
        bad = []
        for f in sorted((ROOT / "modules").glob("*/*.asm")):
            if "upstream" in f.parts:
                continue
            try:
                norep.refuse_rep(f.read_text(), f.name)
            except SystemExit as e:
                bad.append(str(e))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
