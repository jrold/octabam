#!/usr/bin/env python3
"""Pin the exact production/test sources behind the final Perky CF qualification.

The PCM counts are valid only for these bytes. Any change to the renderer,
control path, asset extractor, module declaration, remix profile, or executable
differential tests must deliberately refresh this manifest after rerunning the
full qualification against the exact PĒRKONS v1.2.1 firmware.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "modules/perky/cf_math.h": "1de0de1e7eb341fda2d30a8a12733feacf4e3a29dfc25b81692ab2ac0c8792be",
    "modules/perky/cf_fold.c": "43e29f3a780d13b828d903a2350e2217a937b712bae9a8ed5367aebf21a4bcaa",
    "modules/perky/cf_fold.h": "e1e3d3c16065fbbfc77b3606782aef431d42ff745ae3c4105472e1444cc25996",
    "modules/perky/cf_karplus.c": "efc27b24ab3dd6f883cfef7c993f8dea450921ad8a4250cf60bba50648b4d56c",
    "modules/perky/cf_karplus.h": "8c311ecfa6e2eb9fe2b57c2af05a524419f44f61a002f0b94afe6ca404cd9d70",
    "modules/perky/cf_noise_tone.c": "8280e80b86bea5e6cecbe058c186c69b6f0e4c5c6141dd162c9f2dc89dca1ccc",
    "modules/perky/cf_noise_tone.h": "9cbf001ccbdedb4ee25cd6ec88d8d804ac442a070b1f3ac4c26470c113417d45",
    "modules/perky/cf_perky4.c": "2e51ce5b6fc29cd492c6fcbfd27c58419ef7a84fa18ea42e306dffa6f4351bde",
    "modules/perky/cf_perky4.h": "ba3d7ab037cdb1537278796e321384322779a91ca977f40cd16f0198190f8805",
    "modules/perky/control_cf_final.c": "e0c0c70fd9549468feae8d732a2d1cdcc6b6cca17801372bd49d26dcd5883a67",
    "modules/perky/cf_assets.s": "3d3d2fbf2421450e27712106c5c52dd554ab3d34df04099243b8dfef14654ca8",
    "modules/perky/generate_cf_final.py": "4c02d2da5e14a7e7a34f78c378729e83f383dc88c0cdd66bc9f94cc0da9245b9",
    "tools/perky/perky_cf_assets.py": "90ccbdf0f7a8c86220f6b71cb2e105a9d1f868c65d35d8492e2e64b0e8d63a96",
    "tools/perky/generate_cf_final_fixtures.py": "e6176d75855543f9d9dbadf3da3a27fb3b06c3b45557bf119dfc0ff045fd7c5a",
    "tools/perky/perky_cf_machine_module.py": "1244a1cb4dc5dd14d935f1e3b59a1ce409f1f2b6dbde8d7b22bd00942b1afcab",
    "remixes/test/perky-cf-final/remix.py": "409443c6b4e27e37c488c779a8f50e7795448acc4e56e77acb31996377945c3b",
    "tools/verify/perky4_state_diff.cpp": "90bcd64afb7833e12f2e31325c47db3ae94a3990d5cd6cb2b24b1592a75975eb",
    "tools/verify/perky4_nt_state_diff.cpp": "39422f49285837d60c834179b937cefb87e5b67f54e0c626d1be4efbf57001f9",
    "tools/verify/perky4_sequence_diff.cpp": "db15b944d082952e423b98e274fbf3006c85163f9a22de243758d97582f87bb7",
    "tools/verify/perky4_control_pcm_diff.cpp": "90a485db69b5044a3bba1e8fb8ce937af90eb5786517f1fc7ea8fd185bd54361",
    "tools/verify/perky4_render_stress.cpp": "4492720f00fcdd1041af22485ba124b05f33d87063bcfffedb6eb3dba47660c5",
    "tools/verify/perky_cf_split_plock_timing.cpp": "60c5bc623b45ddfe8ca5bc381375dc450cf36abce24c69c20aed424d203440ac",
    "tools/verify/perky_cf_production_render_diff.cpp": "19d6ebf73c6bfc27ed9f9c52fcd70f81521e26ef3115a0c35a9ef05b4f4cd417",
    "tools/verify/verify_perky_cf_production_render.py": "d58406effcb6e30cd2001c4285b37e9b3f1c68396ed74a009f234e09422a9dbe",
    "tools/verify/verify_perky_cf_final.py": "4e68c05ebc00b4a7f7ecbe94476424ad86ffc1a7ef306bc0852217b0be2fc277",
    "tools/verify/verify_perky_stock_dsp_identity.py": "1bab1de6c609232b7f79d87ebcb347430ca48adbba97110e8ec75cca55045bd3",
    "tools/perky/build_cf_final.py": "11ea97bf33c40417d19d802fadfbf5e47373f748f50ec66315fecaa109fd98d3",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    failures = []
    for rel, expected in EXPECTED.items():
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"{rel}: missing")
            continue
        got = sha256(path)
        if got != expected:
            failures.append(f"{rel}: {got} != {expected}")
    if failures:
        raise SystemExit("PERKY qualified-source identity: FAIL\n  " + "\n  ".join(failures))
    print(f"PERKY qualified-source identity: PASS ({len(EXPECTED)} files byte-pinned to executed PCM qualification)")


if __name__ == "__main__":
    main()
