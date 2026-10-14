"""A stock_dsp module keeps the stock effect it replaces out of the harvest."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from remix import stock  # noqa: E402

# stock.p_spans reads the user's own 1.40C slice; CI has none.
HAVE_STOCK = (pathlib.Path(__file__).resolve().parents[3] / "out/raw/section_3_MAIN_OS.bin").is_file()


@unittest.skipUnless(HAVE_STOCK, "needs out/raw/section_3_MAIN_OS.bin (make os && make recon)")
class HarvestTests(unittest.TestCase):
    def test_unlisted_effect_is_harvested(self):
        self.assertIn("COMPRESSOR", stock.harvested(set()))

    def test_stock_dsp_module_keeps_its_donor(self):
        self.assertNotIn("COMPRESSOR", stock.harvested({"SIDECHAIN_COMPRESSOR"}))

    def test_other_effects_stay_harvested(self):
        got = stock.harvested({"SIDECHAIN_COMPRESSOR"})
        self.assertEqual(got, stock.harvested(set()) - {"COMPRESSOR"})


if __name__ == "__main__":
    unittest.main()
