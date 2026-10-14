"""refhash_run: the manifest is the one the sequential bash matrix wrote."""
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import refhash_run as R  # noqa: E402


class Run(unittest.TestCase):
    def test_artifacts_are_listed_in_sorted_order_from_the_known_names(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            for rel in ("out/mainos_bus.bin", "out/mainos_bus_dev.bin", "out/mainos_bus_mode1.bin",
                        "out/dsp/mem_dev_A.mem", "out/other.bin"):
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_bytes(b"x")
            self.assertEqual(R.artifacts(d), ["out/dsp/mem_dev_A.mem", "out/mainos_bus.bin",
                                              "out/mainos_bus_dev.bin", "out/mainos_bus_mode1.bin"])

    def test_a_traceback_loses_its_line_numbers_only(self):
        t = 'Traceback:\n  File "/x/y.py", line 123, in f\nValueError: bad 123\n'
        self.assertEqual(R.TRACE.sub('File "<src>", line <n>', t),
                         'Traceback:\n  File "<src>", line <n>, in f\nValueError: bad 123\n')

    def test_a_case_is_its_environment_then_the_artifacts_then_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "tools/build").mkdir(parents=True)
            (d / "tools/build/build_bus.py").write_text(
                "import os, pathlib\npathlib.Path('out').mkdir(exist_ok=True)\n"
                "pathlib.Path('out/mainos_bus.bin').write_bytes(os.environ['REMIX'].encode() + os.environ.get('X', '').encode())\n"
                "print('built', os.environ['REMIX'])\n")
            out = d / "o"
            out.mkdir()
            rc, lines = R.run_case(d, "t", "X=1 REMIX=other", out)
            self.assertEqual(rc, 0)
            self.assertEqual(lines[0], "case t rc=0")
            self.assertTrue(lines[1].endswith("  out/mainos_bus.bin"))
            self.assertTrue(lines[2].endswith("  <report>"))
            self.assertEqual((out / "t.log").read_text(), "built other\n")      # a later REMIX= wins
            self.assertEqual(R.sha(d / "out/mainos_bus.bin"), lines[1].split()[0])


if __name__ == "__main__":
    unittest.main()
