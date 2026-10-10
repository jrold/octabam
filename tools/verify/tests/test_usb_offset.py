"""tools/hw/usb_offset.py: synthetic 20-channel takes with known offsets."""
import contextlib
import importlib.util
import io
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]


@unittest.skipUnless(importlib.util.find_spec("numpy"), "needs numpy (the .venv)")
class UsbOffset(unittest.TestCase):
    def test_selftest(self):
        spec = importlib.util.spec_from_file_location("usb_offset", ROOT / "tools/hw/usb_offset.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(mod.selftest())


if __name__ == "__main__":
    unittest.main()
