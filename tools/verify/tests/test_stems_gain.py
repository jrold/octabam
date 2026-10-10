"""tools/verify/stems_gain.py: core 0's MAIN-gain arithmetic, from the
disassembly (docs/firmware/STEM_REC.md 18.2-18.3)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import stems_gain as sg  # noqa: E402

# A stand-in table: the hook reads the real one from the image. These tests
# need only T[254], which the port read as 0x7ffd87 (STEM_REC.md 18.4).
TABLE = [0] * 258
TABLE[254] = 0x7ffd87


def page(w1=0x7f00, w2=0x7f00, w3=0, w29=0x0040):
    words = [0] * 64
    for k in range(8):
        words[4 * k + 1], words[4 * k + 2], words[4 * k + 3] = w1, w2, w3
    words[0x29] = w29
    return words


class Arithmetic(unittest.TestCase):
    def test_mpy_is_the_dsp_fractional_multiply_truncated(self):
        self.assertEqual(sg.mpy(0x400000, 0x400000), 0x200000)          # 0.5 * 0.5
        self.assertEqual(sg.mpy(-0x400000, 0x400000), -0x200000)
        self.assertEqual(sg.mpy(1, 1), 0)                               # floor
        self.assertEqual(sg.mpy(-1, 1), -1)                             # floor, not toward zero

    def test_lim24_saturates_minus_one_squared(self):
        self.assertEqual(sg.lim24(sg.mpy(-0x800000, -0x800000)), 0x7fffff)

    def test_target_reproduces_the_port(self):
        # T1 at LEVEL 127 (w1 0x7f00), table index 254 (w2 0x7f00), MAIN
        # level 64: core 0's Y:0x01 read 0x1f7fe3 under the port.
        self.assertEqual(sg.target(0x7f00, 0x7f00, 0x0040, TABLE), 0x1f7fe3)

    def test_level_zero_is_silence(self):
        self.assertEqual(sg.target(0x0000, 0x7f00, 0x0040, TABLE), 0)


class Ramp(unittest.TestCase):
    def test_a_ramp_from_zero_settles_on_the_floor_of_the_target(self):
        m = sg.Mirror(TABLE)
        g = m.step(page())
        self.assertEqual(g[0][0], 0)                                     # sample 0: the old gain
        self.assertEqual(m.state[0], [0, 0x1f7fe3 >> 4, 0x1f7fe0])      # the port's settled gain
        self.assertEqual(m.step(page())[0], [0x1f7fe0] * 16)             # 3 LSB short, for good

    def test_a_split_holds_then_ramps(self):
        m = sg.Mirror(TABLE)
        m.step(page())
        g = m.step(page(w1=0x4000, w3=5))                                # LEVEL 64 from sample 5
        self.assertEqual(g[0][:5], [0x1f7fe0] * 5)
        inc = sg.lim24((sg.target(0x4000, 0x7f00, 0x0040, TABLE) - 0x1f7fe0) >> 4)
        self.assertEqual(g[0][5:], [0x1f7fe0 + i * inc for i in range(11)])
        g = m.step(page(w1=0x4000, w3=5))                                # m = min(5, 5): five more
        self.assertEqual(g[0][:5], [0x1f7fe0 + (11 + i) * inc for i in range(5)])

    def test_a_shorter_split_cuts_the_ramp(self):
        m = sg.Mirror(TABLE)
        m.step(page())
        m.step(page(w1=0x4000, w3=5))
        cur = m.state[0][2]
        g = m.step(page(w1=0x4000, w3=0))                                # m = min(0, 5) = 0
        inc = sg.lim24((sg.target(0x4000, 0x7f00, 0x0040, TABLE) - cur) >> 4)
        self.assertEqual(g[0][:2], [cur, cur + inc])


class Stem(unittest.TestCase):
    def test_one_track_is_its_share_of_the_mix(self):
        self.assertEqual(sg.stem24(0x1f7fe0, 0x400000), (0x1f7fe0 * 0x400000) >> 21)
        self.assertEqual(sg.main24([0x1f7fe0], [0x400000]), sg.stem24(0x1f7fe0, 0x400000))

    def test_a_stem_clips_like_the_mix(self):
        self.assertEqual(sg.stem24(0x7fffff, 0x7fffff), 0x7fffff)
        self.assertEqual(sg.stem24(0x7fffff, -0x800000), -0x800000)


class Pages(unittest.TestCase):
    def test_a_page_is_taken_when_the_index_moves_past_it(self):
        log = "\n".join([
            "   [     1.0] [0x80005462] <- 0x7f00 (2) at pc 0x4000cb6a in x  i=1",
            "   [     2.0] [0x80004804] <- 0x1 (4) at pc 0x40004e72 in x  i=2",
            "   [     2.0] [0x80004804] <- 0x1 (4) at pc 0x40004e72 in x  i=3",   # the second core's write
            "   [    18.0] [0x800054e2] <- 0x4000 (2) at pc 0x4000cb6a in x  i=4",
            "   [    18.0] [0x80004804] <- 0x2 (4) at pc 0x40004e72 in x  i=5",
            "   [    34.0] [0x80004804] <- 0 (4) at pc 0x40004e72 in x  i=6"])
        pages = sg.sent_pages(log)
        self.assertEqual(len(pages), 2)                                  # page 1, then page 2
        self.assertEqual(pages[0][1], 0x4000)
        self.assertEqual(pages[1][1], 0)

    def test_the_wrap_transient_is_not_a_page(self):
        # The fourth frame writes the index 4, then 0, in one routine
        # (STEM_REC.md 18.1): there are four pages, and 4 is never sent.
        log = "\n".join([
            "   [     1.0] [0x80004804] <- 0x3 (4) at pc 0x40004e72 in x  i=1",
            "   [     1.0] [0x800055e2] <- 0x1234 (2) at pc 0x4000cb6a in x  i=2",
            "   [     2.0] [0x80004804] <- 0x4 (4) at pc 0x40004e72 in x  i=3",
            "   [     2.0] [0x80004804] <- 0 (4) at pc 0x40004e72 in x  i=4",
            "   [     3.0] [0x80004804] <- 0x1 (4) at pc 0x40004e72 in x  i=5"])
        self.assertEqual([p[1] for p in sg.sent_pages(log)], [0x1234, 0])

    def test_a_mark_names_the_page_being_sent(self):
        # A test seam's counter, written once a frame: each value comes back
        # with the index, among the returned pages, of the page sent then.
        log = "\n".join([
            "   [     1.0] [0x80004804] <- 0x1 (4) at pc 0x40004e72 in x  i=1",
            "   [     1.5] [0x40b00000] <- 0x2 (4) at pc 0x40b00010 in x  i=2",
            "   [     2.0] [0x80004804] <- 0x2 (4) at pc 0x40004e72 in x  i=3",
            "   [     2.5] [0x40b00000] <- 0x3 (4) at pc 0x40b00010 in x  i=4",
            "   [     3.0] [0x80004804] <- 0x3 (4) at pc 0x40004e72 in x  i=5"])
        pages, marks = sg.sent_pages(log, mark=0x40b00000)
        self.assertEqual(len(pages), 2)
        self.assertEqual(marks, [(2, 0), (3, 1)])


if __name__ == "__main__":
    unittest.main()
