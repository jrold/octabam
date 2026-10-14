"""scripts/vendor.sh and scripts/setup.sh refuse a vendor/ that is a symlink
(a worktree's), before any fetch or patch."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]


class VendorGuard(unittest.TestCase):
    def tree(self, d, symlink):
        d = pathlib.Path(d)
        (d / "scripts").mkdir()
        for name in ("vendor.sh", "setup.sh"):
            shutil.copy2(ROOT / "scripts" / name, d / "scripts" / name)
        if symlink:
            (d / "elsewhere").mkdir()
            os.symlink(d / "elsewhere", d / "vendor")
        return d

    def test_vendor_sh_refuses_a_symlinked_vendor_and_touches_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.tree(d, True)
            r = subprocess.run(["bash", "scripts/vendor.sh", "mc68k", "dsp56300"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 3)
            self.assertIn("symlink", r.stderr)
            self.assertEqual(list((d / "elsewhere").iterdir()), [])

    def test_setup_sh_refuses_it_too(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.tree(d, True)
            r = subprocess.run(["bash", "scripts/setup.sh"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 3)
            self.assertEqual(list((d / "elsewhere").iterdir()), [])
            self.assertNotIn("System tools", r.stdout)

    def test_an_own_vendor_is_not_refused(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.tree(d, False)
            r = subprocess.run(["bash", "scripts/vendor.sh"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)               # the usage line, past the guard's place
            self.assertNotIn("symlink", r.stderr)


if __name__ == "__main__":
    unittest.main()
