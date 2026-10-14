"""refhash_store: the baseline is keyed by the merge-base, fetched from the
store, saved only when absent, and the store keeps the newest KEEP."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import refhash_store as R  # noqa: E402


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root,
                          capture_output=True, text=True, check=True).stdout.strip()


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        (self.root / "a").write_text("1")
        git(self.root, "add", "a")
        git(self.root, "commit", "-q", "-m", "one")
        git(self.root, "branch", "base")           # base = the merge-base
        git(self.root, "checkout", "-q", "-b", "work")
        self.saves = []
        self.real = R.save_baseline

        def fake(k, mb, root=self.root):
            self.saves.append(mb)
            d = R.store_dir(root) / k
            d.mkdir(parents=True)
            (d / "manifest.txt").write_text(f"case from {mb}\n")
            (d / "KEY").write_text(k + "\n")
        R.save_baseline = fake

    def tearDown(self):
        R.save_baseline = self.real
        self.tmp.cleanup()

    def test_fetch_saves_once_per_merge_base_and_copies(self):
        say = lambda *_: None
        R.fetch("base", self.root, say)
        self.assertEqual(len(self.saves), 1)
        dest = self.root / "out/refhash/baseline"
        self.assertIn(self.saves[0], (dest / "manifest.txt").read_text())
        R.fetch("base", self.root, say)                         # in place: nothing copied or saved
        # another worktree's out/ is empty: copied from the store, not saved again
        import shutil
        shutil.rmtree(dest)
        R.fetch("base", self.root, say)
        self.assertEqual(len(self.saves), 1)
        self.assertTrue((dest / "manifest.txt").is_file())

    def test_a_new_merge_base_is_a_new_key_and_replaces_the_baseline(self):
        k1 = R.key("base", self.root)
        R.fetch("base", self.root, lambda *_: None)
        (self.root / "a").write_text("2")
        git(self.root, "commit", "-q", "-am", "two")
        git(self.root, "branch", "-f", "base", "HEAD")        # main moved; the branch rebased onto it
        self.assertNotEqual(R.key("base", self.root), k1)
        R.fetch("base", self.root, lambda *_: None)
        self.assertEqual(len(self.saves), 2)
        self.assertEqual((self.root / "out/refhash/baseline/KEY").read_text().strip(), R.key("base", self.root))

    def test_the_key_follows_the_stock_slice(self):
        k = R.key("base", self.root)
        (self.root / "out/raw").mkdir(parents=True)
        (self.root / "out/raw/section_3_MAIN_OS.bin").write_bytes(b"x")
        self.assertNotEqual(R.key("base", self.root), k)

    def test_prune_keeps_the_newest(self):
        sd = R.store_dir(self.root)
        for i in range(R.KEEP + 3):
            d = sd / f"k{i:02d}"
            d.mkdir(parents=True)
            (d / "manifest.txt").write_text("x")
            os.utime(d, (1000 + i, 1000 + i))
        R.prune(self.root)
        left = sorted(p.name for p in sd.iterdir() if p.is_dir())
        self.assertEqual(len(left), R.KEEP)
        self.assertEqual(left[0], "k03")


if __name__ == "__main__":
    unittest.main()
