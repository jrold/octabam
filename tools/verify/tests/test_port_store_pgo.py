"""port_store: install prefers the store's PGO build, OCTABAM_PGO=0 asks for the plain one,
the PGO directory follows pgo.sh's bytes, and the profile is not installed."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/emu"))
sys.path.insert(0, str(ROOT / "tools/verify"))
import port_store  # noqa: E402
import reach  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "tools/emu/ot_emu").mkdir(parents=True)
        (self.root / "tools/emu/ot_emu/pgo.sh").write_text("#!/bin/bash\necho one\n")
        self.real_key, self.real_stamp = port_store.key, reach.stamp_port
        port_store.key = lambda root=self.root: "K" * 64
        reach.stamp_port = lambda *a, **k: None

    def tearDown(self):
        port_store.key, reach.stamp_port = self.real_key, self.real_stamp
        self.tmp.cleanup()

    def fill(self, d, text):
        d.mkdir(parents=True)
        (d / "ot_emu").write_text(text)
        (d / "ot_dsp_test").write_text(text)
        (d / "ot_emu.profdata").write_text("profile")
        (d / "pgo.log").write_text("log")


class Pgo(Base):
    def test_the_pgo_directory_follows_pgo_sh(self):
        a = port_store.pgo_dir("K" * 64, self.root)
        (self.root / "tools/emu/ot_emu/pgo.sh").write_text("#!/bin/bash\necho two\n")
        self.assertNotEqual(a, port_store.pgo_dir("K" * 64, self.root))
        self.assertTrue(a.name.startswith("K" * 64 + "-pgo-"))

    def test_install_takes_the_pgo_build_and_only_the_executables(self):
        self.fill(port_store.built.__globals__["store_dir"](self.root) / ("K" * 64), "plain")
        self.fill(port_store.pgo_dir("K" * 64, self.root), "pgo")
        dest, d = port_store.install(self.root / "out/emu", self.root)
        self.assertEqual((dest / "ot_emu").read_text(), "pgo")
        self.assertEqual((dest / "ot_dsp_test").read_text(), "pgo")
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["ot_dsp_test", "ot_emu"])    # no profdata, no log
        self.assertIn("-pgo-", d.name)

    def test_octabam_pgo_0_asks_for_the_plain_build(self):
        self.fill(port_store.built.__globals__["store_dir"](self.root) / ("K" * 64), "plain")
        self.fill(port_store.pgo_dir("K" * 64, self.root), "pgo")
        os.environ["OCTABAM_PGO"] = "0"
        try:
            dest, d = port_store.install(self.root / "out/emu", self.root)
        finally:
            del os.environ["OCTABAM_PGO"]
        self.assertEqual((dest / "ot_emu").read_text(), "plain")
        self.assertNotIn("-pgo-", d.name)


class Background(Base):
    """The PGO build starts itself, detached and never waiting."""

    def setUp(self):
        super().setUp()
        import gate_cache
        self.gate_cache = gate_cache
        self.real_project, self.real_spawn, self.real_pgo = gate_cache.project_dir, port_store.spawn, port_store.pgo
        gate_cache.project_dir = lambda: self.root          # a project that exists
        self.spawned = []
        port_store.spawn = lambda argv, **kw: self.spawned.append((argv, kw))
        os.environ.pop("OCTABAM_PGO", None)

    def tearDown(self):
        self.gate_cache.project_dir = self.real_project
        port_store.spawn = self.real_spawn
        port_store.pgo = self.real_pgo
        os.environ.pop("OCTABAM_PGO", None)
        super().tearDown()

    def test_it_starts_one_detached_nice_child_when_the_store_has_no_pgo_build(self):
        said = []
        self.assertTrue(port_store.pgo_background(self.root, said.append))
        argv, kw = self.spawned[0]
        self.assertEqual(argv[:3], ["nice", "-n", "10"])
        self.assertEqual(argv[-1], "pgo-bg")
        self.assertTrue(kw["start_new_session"])
        self.assertIn("background", said[0])

    def test_it_does_not_start_when_it_should_not(self):
        self.fill(port_store.pgo_dir("K" * 64, self.root), "pgo")                       # the store has it
        self.assertFalse(port_store.pgo_background(self.root, lambda m: None))
        import shutil
        shutil.rmtree(port_store.pgo_dir("K" * 64, self.root))
        os.environ["OCTABAM_PGO"] = "0"                                                   # asked for the plain build
        self.assertFalse(port_store.pgo_background(self.root, lambda m: None))
        del os.environ["OCTABAM_PGO"]
        self.gate_cache.project_dir = lambda: None                                        # nothing to train on
        self.assertFalse(port_store.pgo_background(self.root, lambda m: None))
        self.gate_cache.project_dir = lambda: self.root
        d = port_store.pgo_dir("K" * 64, self.root)
        (d.parent / f"{d.name}.failed").parent.mkdir(parents=True, exist_ok=True)
        (d.parent / f"{d.name}.failed").write_text("failed")                              # failed a minute ago
        self.assertFalse(port_store.pgo_background(self.root, lambda m: None))
        old = port_store.time.time() - port_store.PGO_RETRY_S - 5
        os.utime(d.parent / f"{d.name}.failed", (old, old))                               # long enough ago: retry
        self.assertTrue(port_store.pgo_background(self.root, lambda m: None))
        self.assertEqual(len(self.spawned), 1)

    def test_the_child_yields_to_another_build_and_records_a_failure(self):
        import fcntl
        sd = port_store.store_dir(self.root)
        sd.mkdir(parents=True, exist_ok=True)
        calls = []
        port_store.pgo = lambda root=self.root: calls.append(1)
        with open(sd / "pgo-running.lock", "a+") as held:                                 # another build holds the machine lock
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertEqual(port_store.pgo_bg(self.root), 0)
        self.assertEqual(calls, [])
        def boom(root=self.root):
            raise SystemExit("cmake failed")
        port_store.pgo = boom
        self.assertEqual(port_store.pgo_bg(self.root), 1)
        d = port_store.pgo_dir("K" * 64, self.root)
        self.assertIn("cmake failed", (sd / f"{d.name}.failed").read_text())


if __name__ == "__main__":
    unittest.main()
