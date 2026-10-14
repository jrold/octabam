"""tools/hw/ot_brain.py: every valid corpus file through JSON and back,
byte for byte."""
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[1] / "hw"))
import ot_brain  # noqa: E402

CORPUS = HERE / "brainfile_corpus"
EXPECT = json.loads((CORPUS / "expect.json").read_text())


class RoundTrip(unittest.TestCase):
    def test_dump_then_build_is_identical(self):
        for name, e in EXPECT.items():
            if e["outcome"] != "valid":
                continue
            with self.subTest(name):
                data = (CORPUS / f"{name}.brain").read_bytes()
                j = json.loads(json.dumps(ot_brain.dump(data)))
                self.assertEqual(ot_brain.build(j), data)

    def test_an_edited_value_lands(self):
        data = (CORPUS / "settings_known.brain").read_bytes()
        j = ot_brain.dump(data)
        j["records"][0]["values"][2]["value"] = 1234
        out = ot_brain.dump(ot_brain.build(j))
        self.assertEqual(out["records"][0]["values"][2]["value"], 1234)


class ProjectPair(unittest.TestCase):
    def test_project_kinds_dump_and_pair(self):
        import contextlib
        import io
        import tempfile
        from remix import brainfile
        rec = brainfile.Record(brainfile.PROJECT_RECORD, "octabam.brain",
                               payload=brainfile.Entry(6, "octabam.busdelay", 0x01020304).encode())
        work = brainfile.File(brainfile.PROJECT_WORK, [rec], "T").encode()
        strd = brainfile.File(brainfile.PROJECT_STRD, [rec], "T").encode()
        for blob, kind in ((work, "project .work"), (strd, "project .strd")):
            j = ot_brain.dump(blob)
            self.assertEqual(j["file"], kind)
            self.assertEqual(j["records"][0]["entries"],
                             [{"fx_id": "0x06", "store_id": "octabam.busdelay", "layout": "01020304"}])
            self.assertEqual(ot_brain.build(json.loads(json.dumps(j))), blob)
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "brain.work").write_bytes(work[:-3] + b"xyz")
            (d / "brain.strd").write_bytes(strd)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                ot_brain.main(["ot_brain.py", "pair", str(d)])
            self.assertIn("brain.work", out.getvalue())
            self.assertIn("1 records", out.getvalue())


if __name__ == "__main__":
    unittest.main()
