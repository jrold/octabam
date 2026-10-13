"""recloop.record_audio: segment headers at any playback rate."""
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import toolpath  # noqa: E402,F401  (every tools/ dir on sys.path)
import recloop  # noqa: E402

RECORD_WORDS = 84


def record(*parts):
    words = [w for p in parts for w in p]
    return words + [0] * (RECORD_WORDS - len(words))


def header(count, rate, tag=0):
    return [count, 0, rate, tag]


def pairs(*lr):
    return [w for p in lr for w in p]


class RecordAudioTests(unittest.TestCase):
    def test_generator_commands_are_not_pcm(self):
        for controls in ([0] * 80, [0x7f7f7f] * 80):
            rec = [0x504b00, 0x593100] + controls
            self.assertEqual(recloop.record_audio(rec), [])
            self.assertEqual(recloop.record_audio(rec, right=True), [])

    def test_magic_values_inside_stock_pcm_are_preserved(self):
        data = [(0x504b00, 0x593100)] + [(17, -17)] * 15
        rec = record(header(16, 0x40000), pairs(*data))
        self.assertEqual(recloop.record_audio(rec), [l for l, _ in data])
        self.assertEqual(recloop.record_audio(rec, right=True), [r for _, r in data])

    def test_thru_two_empty_headers_then_sixteen_pairs(self):
        data = [(100 + k, -100 - k) for k in range(16)]
        rec = record(header(0, 0x40000), header(0, 0x40000), pairs(*data))
        self.assertEqual(recloop.record_audio(rec), [l for l, _ in data])
        self.assertEqual(recloop.record_audio(rec, right=True), [r for _, r in data])

    def test_unity_split_segments(self):
        a = [(10 + k, 0) for k in range(5)]
        b = [(50 + k, 0) for k in range(11)]
        rec = record(header(5, 0x40000, 0x100000), pairs(*a), header(11, 0x40000, 0x140000), pairs(*b))
        self.assertEqual(recloop.record_audio(rec), [l for l, _ in a + b])

    def test_half_rate_static_with_no_sample(self):
        # T3 of OCTABAM89_setgate bank 2 under the port (2 Oct 2026): the
        # STATIC slot's sample not staged, one segment at rate 0x20000.
        rec = record(header(0, 0x40000), header(16, 0x20000, 0xe00000), pairs(*[(0, 0)] * 8))
        self.assertEqual(recloop.record_audio(rec), [0] * 8)

    def test_half_rate_split(self):
        # T6 of the same part: 4 + 12 output samples at rate 0x20000.
        rec = record(header(4, 0x20000, 0x180000), pairs((0, 0), (0, 0)),
                     header(12, 0x20000, 0x200000), pairs(*[(0, 0)] * 6))
        self.assertEqual(recloop.record_audio(rec), [0] * 8)

    def test_half_rate_carries_its_samples(self):
        data = [(1000 * (k + 1), -1000 * (k + 1)) for k in range(8)]
        rec = record(header(16, 0x20000, 0x80000), pairs(*data))
        self.assertEqual(recloop.record_audio(rec), [l for l, _ in data])

    def test_segment_one_pair_past_the_estimate(self):
        a = [(7, 0)] * 3
        b = [(9, 0)] * 6
        rec = record(header(4, 0x20000), pairs(*a), header(12, 0x20000), pairs(*b))
        self.assertEqual(recloop.record_audio(rec), [7, 7, 7] + [9] * 6)


if __name__ == "__main__":
    unittest.main()
