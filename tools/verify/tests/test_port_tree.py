"""out/emu's CMake build tree is not there in a tree that got its port from
port_store (every shard, every fresh worktree): a harness that reads it must
build it first (port_store.ensure_tree)."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/emu"))
import port_store  # noqa: E402

READS = ("CMakeFiles/", "flags.make", "link.txt")
EXEMPT = {"tools/emu/port_store.py", "tools/verify/tests/test_port_tree.py"}


class PortTree(unittest.TestCase):
    def test_no_harness_reads_the_cmake_tree_without_building_it(self):
        files = subprocess.run(["git", "ls-files", "-z", "--", "tools", "modules", "scripts", "Makefile"],
                               cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\0")
        bad = []
        for rel in filter(None, files):
            if rel in EXEMPT or "/upstream/" in rel or rel.endswith(("CMakeLists.txt", ".md", ".sh")):
                continue
            try:
                text = (ROOT / rel).read_text()
            except (OSError, UnicodeDecodeError):
                continue
            if any(r in text for r in READS) and "ensure_tree" not in text:
                bad.append(rel)
        self.assertEqual(bad, [], "reads out/emu's CMake tree without port_store.ensure_tree()")

    def test_ensure_tree_leaves_a_present_tree_alone(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            for f in port_store.TREE_FILES:
                (d / "out/emu" / f).parent.mkdir(parents=True, exist_ok=True)
                (d / "out/emu" / f).write_text("x")
            self.assertEqual(port_store.ensure_tree(d), d / "out/emu")


if __name__ == "__main__":
    unittest.main()
