#!/usr/bin/env python3
"""Self-test Perky final packaging guards with synthetic fixtures.

No firmware/toolchain is required. The test proves the stock-DSP identity and
card/MIDI wrapper round-trip gates both accept exact data and fail closed on a
single deliberate corruption.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2] if len(Path(__file__).resolve().parents) > 2 else Path.cwd()
VERIFY = ROOT / "tools/verify"
BUILD = ROOT / "tools/build"
sys.path.insert(0, str(BUILD))
import bin_decode  # type: ignore  # noqa:E402


def encode_word(k: int, p: int) -> int:
    if (k & 0x800000) == 0:
        return bin_decode.rot16((p ^ k ^ bin_decode.C3) & bin_decode.M) ^ bin_decode.XOR_A
    return bin_decode.bswap((p ^ k ^ bin_decode.C7) & bin_decode.M) ^ bin_decode.XOR_B


def make_elup(elek: bytes, seed: int = 0x12345678) -> bytes:
    payload = struct.pack(">I", len(elek)) + elek
    payload += b"\0" * ((-len(payload)) & 3)
    plain = list(struct.unpack(f">{len(payload)//4}I", payload))
    out = [bin_decode.MAGIC, seed]
    k = seed
    acc = 0
    for p in plain:
        c = encode_word(k, p)
        out.append(c)
        acc = (acc + p) & bin_decode.M
        k = c
    out.append(encode_word(k, acc))
    return struct.pack(f">{len(out)}I", *out)


def run_ok(cmd: list[object]) -> str:
    p = subprocess.run(list(map(str, cmd)), cwd=ROOT, check=True, capture_output=True, text=True)
    return p.stdout


def run_fail(cmd: list[object], needle: str) -> str:
    p = subprocess.run(list(map(str, cmd)), cwd=ROOT, capture_output=True, text=True)
    text = p.stdout + p.stderr
    if p.returncode == 0:
        raise AssertionError(f"negative test unexpectedly passed: {' '.join(map(str, cmd))}")
    if needle not in text:
        raise AssertionError(f"negative test failed for wrong reason; wanted {needle!r}:\n{text}")
    return text


def main() -> None:
    dsp_gate = VERIFY / "verify_perky_stock_dsp_identity.py"
    wrapper_gate = VERIFY / "verify_perky_final_wrappers.py"
    if not dsp_gate.is_file() or not wrapper_gate.is_file():
        raise SystemExit("run from an Octabam checkout containing final Perky release gates")

    with tempfile.TemporaryDirectory(prefix="perky-release-guards-") as td:
        work = Path(td)

        # DSP identity: synthetic images only need to span the pinned DSP extent.
        base = 0x40000400
        dsp_end = 0x401086F4
        size = dsp_end - base + 64
        stock = bytearray((i * 37 + 11) & 0xFF for i in range(size))
        candidate = bytearray(stock)
        stock_path = work / "stock-mainos.bin"
        cand_path = work / "candidate-mainos.bin"
        stock_path.write_bytes(stock)
        cand_path.write_bytes(candidate)
        run_ok([sys.executable, dsp_gate, stock_path, cand_path])
        mutate = 0x400E21E0 - base + 12345
        candidate[mutate] ^= 1
        cand_path.write_bytes(candidate)
        run_fail([sys.executable, dsp_gate, stock_path, cand_path], "1 changed bytes")

        # Wrapper round-trip: build a minimal valid ELEK and ELUP around arbitrary MAIN OS.
        version = "PK4CF1"
        mainos = bytes((i * 13 + 7) & 0xFF for i in range(4097))
        elek = bytearray(128)
        elek[:4] = b"ELEK"
        elek[8:18] = version.rjust(10, " ").encode("ascii")
        # Fill the rest deterministically without disturbing magic/version.
        for i in range(18, len(elek)):
            elek[i] = (i * 19 + 3) & 0xFF
        card = make_elup(bytes(elek))
        main_path = work / "mainos.bin"
        elek_path = work / "image.elek"
        card_path = work / "image.bin"
        midi_path = work / "image.syx"
        eft_path = work / "fake-eft"
        main_path.write_bytes(mainos)
        elek_path.write_bytes(elek)
        card_path.write_bytes(card)
        midi_path.write_bytes(b"synthetic-midi\n")
        eft_path.write_text(
            "#!/usr/bin/env python3\n"
            "import shutil,sys\n"
            "from pathlib import Path\n"
            "a=sys.argv[1:]\n"
            "out=Path(a[a.index('-o')+1]); out.mkdir(parents=True,exist_ok=True)\n"
            f"shutil.copy2({str(main_path)!r}, out/'section_3_MAIN_OS.bin')\n"
        )
        os.chmod(eft_path, 0o755)
        wrapper_cmd = [
            sys.executable, wrapper_gate,
            "--mainos", main_path,
            "--elek", elek_path,
            "--card", card_path,
            "--midi", midi_path,
            "--eft", eft_path,
            "--version", version,
            "--work", work / "wrapper-work",
        ]
        run_ok(wrapper_cmd)

        bad_elek = bytearray(elek)
        bad_elek[8] ^= 1
        bad_elek_path = work / "bad.elek"
        bad_elek_path.write_bytes(bad_elek)
        bad_cmd = wrapper_cmd.copy()
        bad_cmd[bad_cmd.index("--elek") + 1] = bad_elek_path
        run_fail(bad_cmd, "version field mismatch")

        print("PERKY release guards self-test: PASS")
        print("  stock DSP identity accepts exact span and rejects one-byte mutation")
        print("  wrapper verifier accepts synthetic card/MIDI round-trip and rejects corrupted ELEK")
        print("  synthetic MAIN OS sha256=" + hashlib.sha256(mainos).hexdigest())


if __name__ == "__main__":
    main()
