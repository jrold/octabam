#!/usr/bin/env python3
"""Pin exact production/test/release sources behind Perky CF qualification."""
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    'modules/perky/cf_assets.s': '3d3d2fbf2421450e27712106c5c52dd554ab3d34df04099243b8dfef14654ca8',
    'modules/perky/cf_fold.c': '43e29f3a780d13b828d903a2350e2217a937b712bae9a8ed5367aebf21a4bcaa',
    'modules/perky/cf_fold.h': 'e1e3d3c16065fbbfc77b3606782aef431d42ff745ae3c4105472e1444cc25996',
    'modules/perky/cf_karplus.c': 'efc27b24ab3dd6f883cfef7c993f8dea450921ad8a4250cf60bba50648b4d56c',
    'modules/perky/cf_karplus.h': '8c311ecfa6e2eb9fe2b57c2af05a524419f44f61a002f0b94afe6ca404cd9d70',
    'modules/perky/cf_math.h': '1de0de1e7eb341fda2d30a8a12733feacf4e3a29dfc25b81692ab2ac0c8792be',
    'modules/perky/cf_noise_tone.c': '2da69911a55b35be844ac9fd6169014fada78f0aa41cb4ab1136ed38bfb14d0c',
    'modules/perky/cf_noise_tone.h': '9cbf001ccbdedb4ee25cd6ec88d8d804ac442a070b1f3ac4c26470c113417d45',
    'modules/perky/cf_perky4.c': '5ad2e3072c7632ebfb3a3d016e1175986c02493d7e88207384117b3c2dc1b737',
    'modules/perky/cf_perky4.h': 'ba3d7ab037cdb1537278796e321384322779a91ca977f40cd16f0198190f8805',
    'modules/perky/control.c': 'b7905143a0f974dfaf3a39b8a5acb5a6c7dd406bfe7073970519b5842d295d4b',
    'modules/perky/control_cf_final.c': '73241ce22fb5392d038d4458dcaa6b47be3ba9f37f80c2a3e4894c6a7088d8c3',
    'modules/perky/generate_cf_final.py': '4c02d2da5e14a7e7a34f78c378729e83f383dc88c0cdd66bc9f94cc0da9245b9',
    'remixes/test/perky-cf-final/remix.py': '409443c6b4e27e37c488c779a8f50e7795448acc4e56e77acb31996377945c3b',
    'tools/build/bin_decode.py': 'd092430bf99d30d39c6fa81a186a746f0bfc5c6875636a03f48d800e59a05144',
    'tools/perky/build_cf_final.py': '07621f447a41e0c567ee6f3eed819b38343d1886428213ef8b91d21ee21dbd0a',
    'tools/perky/build_machine_canary.py': '3c1fc5155f64a3747ae80f59c2ebc41a7c68091f4c3b18450c64d7ed0106a609',
    'tools/perky/generate_cf_final_fixtures.py': 'e6176d75855543f9d9dbadf3da3a27fb3b06c3b45557bf119dfc0ff045fd7c5a',
    'tools/perky/perky_cf_assets.py': '90ccbdf0f7a8c86220f6b71cb2e105a9d1f868c65d35d8492e2e64b0e8d63a96',
    'tools/perky/perky_cf_machine_module.py': '1244a1cb4dc5dd14d935f1e3b59a1ce409f1f2b6dbde8d7b22bd00942b1afcab',
    'tools/verify/perky4_control_pcm_diff.cpp': '90a485db69b5044a3bba1e8fb8ce937af90eb578651f1fc7ea8fd185bd54361',
    'tools/verify/perky4_long_tail_diff.cpp': '40319eb8b6e3624f6c74c31e035de5241ccb0dd07ae27b0ee2231c7c4171d2b1',
    'tools/verify/perky4_nt_state_diff.cpp': '39422f49285837d60c834179b937cefb87e5b67f54e0c626d1be4efbf57001f9',
    'tools/verify/perky4_render_stress.cpp': '4492720f00fcdd1041af22485ba124b05f33d87063bcfffedb6eb3dba47660c5',
    'tools/verify/perky4_sequence_diff.cpp': 'db15b944d082952e423b98e274fbf3006c85163f9a22de243758d97582f87bb7',
    'tools/verify/perky4_state_diff.cpp': '90bcd64afb7833e12f2e31325c47db3ae94a3990d5cd6cb2b24b1592a75975eb',
    'tools/verify/perky_cf_plock_reversion_diff.cpp': '64dd0e1c09f9851d3cb47a5aa9208077569e9c4dd88684c84e2fee576a0cf4b2',
    'tools/verify/perky_cf_production_render_diff.cpp': '19d6ebf73c6bfc27ed9f9c52fcd70f81521e26ef3115a0c35a9ef05b4f4cd417',
    'tools/verify/perky_cf_runtime_reset_diff.cpp': 'f0cbb4b0616a202ac5bee9520dc7d31993ba75acc4aedeb9a23280b7eb1f6278',
    'tools/verify/perky_cf_split_plock_timing.cpp': '60c5bc623b45ddfe8ca5bc381375dc450cf36abce24c69c20aed424d203440ac',
    'tools/verify/perky_cf_stock_slot_diff.cpp': '52cb58960c2e8bf9461775f92f21359d507e3eb453d0136a86a1976ed679d1c9',
    'tools/verify/verify_perky_cf_codegen.py': '4c20c436ab01876a9c57da1c589341d18c80c7295a9bf8465390d933733cc076',
    'tools/verify/verify_perky_cf_final.py': '3e3c32b63fe727f4f242bf432e947d0046be699d91a9a8dea7e3521fcdf65320',
    'tools/verify/verify_perky_cf_final_control.py': '9e0dcdfb9da07ccaa65e0e50865315fc8a66c92e104f55cd1d3fa971d407602c',
    'tools/verify/verify_perky_cf_final_remix.py': '6dea693ac33f252bf6c8b37c25f48597e64674986f5c8d80e02eee6f2a960e05',
    'tools/verify/verify_perky_cf_freestanding.py': '5499198f777f7ccfde535661432722dd89b280f2130373a80dcd0db4a13399ef',
    'tools/verify/verify_perky_cf_hotloops.py': '621ed7aa1c4502c7cb57e187e60db4f2c9d6c914c5c5e0469ae18b5bae3d60bc',
    'tools/verify/verify_perky_cf_machine_module.py': 'a523367146f4040eac8d86ea0a65e3a16663e665c89ffaa767180ea9c8a68e10',
    'tools/verify/verify_perky_cf_plock_reversion.py': 'f872da3d15427c644bf6ec9d40c5925d7859189fe862f76070de78ac88e984fc',
    'tools/verify/verify_perky_cf_production_render.py': '81e14ffeb0fec3073f9727f577a9238e7c61f662640d6565928713c1b1589121',
    'tools/verify/verify_perky_cf_runtime_memory_final.py': 'a3490feab654f26ca4bb7bb22bacacb8e9b0855fe57277493f05f27177876f8f',
    'tools/verify/verify_perky_cf_runtime_reset.py': '7c902640c9e0633c58f3711a15f707f2acb7e2891758f2c612b07b0e07d21d04',
    'tools/verify/verify_perky_cf_stock_record_abi.py': '3d0b950962c295efca481e23bf61551a94ad00f37abd138964b2f9e09f46acf1',
    'tools/verify/verify_perky_final_wrappers.py': 'f1d48b7d88c9411e2680d7462ae31fdc62ae5276f270fef189a66cfe67f676fc',
    'tools/verify/verify_perky_stock_dsp_identity.py': '1bab1de6c609232b7f79d87ebcb347430ca48adbba97110e8ec75cca55045bd3',
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    failures=[]
    for rel, expected in EXPECTED.items():
        path=ROOT/rel
        if not path.is_file(): failures.append(f"{rel}: missing"); continue
        got=sha256(path)
        if got != expected: failures.append(f"{rel}: {got} != {expected}")
    if failures: raise SystemExit("PERKY qualified-source identity: FAIL\n  " + "\n  ".join(failures))
    print(f"PERKY qualified-source identity: PASS ({len(EXPECTED)} files byte-pinned to executed PCM qualification)")

if __name__ == "__main__": main()
