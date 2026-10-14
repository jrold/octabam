"""The port's source digest covers the sources of a tree that lives under an
out/ directory (every shard: out/shards/*, out/overlap/*). Until 12 Oct 2026
port_sources tested the absolute path for "out", so a shard hashed no file,
every shard had the same port_store key, and a shard ran whichever port the
store first built for it."""
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/verify"))
import reach  # noqa: E402


class Digest(unittest.TestCase):
    def tree(self, base):
        src = pathlib.Path(base) / "tools/emu/ot_emu"
        (src / "build").mkdir(parents=True)
        (src / "main.cpp").write_text("a")
        (src / "build" / "junk.o").write_text("x")
        return src

    def test_a_tree_under_out_hashes_its_sources(self):
        with tempfile.TemporaryDirectory() as t:
            src = self.tree(pathlib.Path(t) / "out/shards/one")
            self.assertEqual([p.name for p in reach.port_sources(src)], ["main.cpp"])
            before = reach.port_digest(src)
            (src / "main.cpp").write_text("b")
            self.assertNotEqual(reach.port_digest(src), before)

    def test_same_sources_same_digest_wherever_the_tree_is(self):
        with tempfile.TemporaryDirectory() as t:
            a = self.tree(pathlib.Path(t) / "one")
            b = self.tree(pathlib.Path(t) / "out/two")
            self.assertEqual(reach.port_digest(a), reach.port_digest(b))


if __name__ == "__main__":
    unittest.main()
