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
    'modules/perky/cf_perky4.h': 'git:db6c66589f5a9ed609cf423867ddc032ea81aa73',
    'modules/perky/control.c': 'b7905143a0f974dfaf3a39b8a5acb5a6c7dd406bfe7073970519b5842d295d4b',
    'modules/perky/control_cf_final.c': 'git:6305b0632de8de4dc847c05b28ca76819cb9a2d6',
    'modules/perky/machine.s': 'git:8f32c73639d85145c96f94ca7624fe1a308c6bc8',
    'modules/perky/fold_control_update.py': '4dc83fbff2f3f84ab8da953e986f2f8523a917c74a87e409f32fb5d15a014bdf',
    'modules/perky/karplus_control_state.py': '8ad77698da197533015b74e0f308829f5f188c966adf481c34b783f7447db736',
    'modules/perky/karplus_control_update.py': '74415d3cc5d2162e65fac63df89994dbdaf3271588dbac471df9122fe02b4d36',
    'modules/perky/noise_tone_control_update.py': 'dffd08a4a93710d684778a7372498d9b80ab0b3c3502ccf46db5eecb6e7578cc',
    'modules/perky/simple_drum_control.py': 'df108a857d49ec679e4355f7def9a4a7dd76fcc0056aee31a65e4c6f66e676f3',
    'modules/perky/generate_cf_final.py': '4c02d2da5e14a7e7a34f78c378729e83f383dc88c0cdd66bc9f94cc0da9245b9',
    'remixes/test/perky-cf-final/remix.py': '409443c6b4e27e37c488c779a8f50e7795448acc4e56e77acb31996377945c3b',
    'tools/build/bin_decode.py': 'd092430bf99d30d39c6fa81a186a746f0bfc5c6875636a03f48d800e59a05144',
    'tools/build/build_bus.py': 'f11a293f3bd8f042c772374912441427e8d48153a07194a93c13970db1c33532',
    'tools/perky/build_cf_final.py': 'git:18349f140b05a05a21b45e7be6d51c5eca276e41',
    'tools/perky/build_machine_canary.py': '3c1fc5155f64a3747ae80f59c2ebc41a7c68091f4c3b18450c64d7ed0106a609',
    'tools/perky/generate_cf_final_fixtures.py': 'e6176d75855543f9d9dbadf3da3a27fb3b06c3b45557bf119dfc0ff045fd7c5a',
    'tools/perky/perky_cf_assets.py': '90ccbdf0f7a8c86220f6b71cb2e105a9d1f868c65d35d8492e2e64b0e8d63a96',
    'tools/perky/perky_cf_machine_module.py': 'git:fc36d10eb126f28e81a56dc8aa1a805bd75d90fd',
    'tools/verify/perky4_control_pcm_diff.cpp': '90a485db69b5044a3bba1e8fb8ce937af90eb5786517f1fc7ea8fd185bd54361',
    'tools/verify/perky4_long_tail_diff.cpp': '40319eb8b6e3624f6c74c31e035de5241ccb0dd07ae27b0ee2231c7c4171d2b1',
    'tools/verify/perky4_nt_state_diff.cpp': '39422f49285837d60c834179b937cefb87e5b67f54e0c626d1be4efbf57001f9',
    'tools/verify/perky4_render_stress.cpp': '4492720f00fcdd1041af22485ba124b05f33d87063bcfffedb6eb3dba47660c5',
    'tools/verify/perky4_sequence_diff.cpp': 'db15b944d082952e423b98e274fbf3006c85163f9a22de243758d97582f87bb7',
    'tools/verify/perky4_state_diff.cpp': '90bcd64afb7833e12f2e31325c47db3ae94a3990d5cd6cb2b24b1592a75975eb',
    'tools/verify/perky_cf_plock_reversion_diff.cpp': 'git:2434333c1a8e74d79c2ce270201b6c19d6ab6ac2',
    'tools/verify/perky_cf_production_render_diff.cpp': 'git:b6f6ebd0d51468f90b51e465698283d26fd71ab4',
    'tools/verify/perky_cf_runtime_reset_diff.cpp': 'git:c9a53b5050ac434b51f6166f445d290045588a90',
    'tools/verify/perky_cf_split_plock_timing.cpp': '60c5bc623b45ddfe8ca5bc381375dc450cf36abce24c69c20aed424d203440ac',
    'tools/verify/perky_cf_stock_slot_diff.cpp': '52cb58960c2e8bf9461775f92f21359d507e3eb453d0136a86a1976ed679d1c9',
    'tools/verify/verify_perky_cf_codegen.py': '4c20c436ab01876a9c57da1c589341d18c80c7295a9bf8465390d933733cc076',
    'tools/verify/verify_perky_cf_final.py': '765a906239a930831aef23f99330734ad038fc129f79b9f9511b5b3ad70ed7e8',
    'tools/verify/verify_perky_cf_final_control.py': 'git:453c3f766c71dd141ef999d111c9dc7241f09faf',
    'tools/verify/verify_perky_cf_final_remix.py': '6dea693ac33f252bf6c8b37c25f48597e64674986f5c8d80e02eee6f2a960e05',
    'tools/verify/verify_perky_cf_freestanding.py': '5499198f777f7ccfde535661432722dd89b280f2130373a80dcd0db4a13399ef',
    'tools/verify/verify_perky_cf_hotloops.py': '621ed7aa1c4502c7cb57e187e60db4f2c9d6c914c5c5e0469ae18b5bae3d60bc',
    'tools/verify/verify_perky_cf_machine_module.py': 'git:7fba03ee036c4ce818b8109232853f55c80096f5',
    'tools/verify/verify_perky_cf_plock_reversion.py': 'f872da3d15427c644bf6ec9d40c5925d7859189fe862f76070de78ac88e984fc',
    'tools/verify/verify_perky_cf_production_render.py': '81e14ffeb0fec3073f9727f577a9238e7c61f662640d6565928713c1b1589121',
    'tools/verify/verify_perky_cf_runtime_memory_final.py': 'a3490feab654f26ca4bb7bb22bacacb8e9b0855fe57277493f05f27177876f8f',
    'tools/verify/verify_perky_cf_runtime_reset.py': '7c902640c9e0633c58f3711a15f707f2acb7e2891758f2c612b07b0e07d21d04',
    'tools/verify/verify_perky_cf_stock_record_abi.py': 'git:a37c45bfd380f18dbd6033d23e138a1d638ceb10',
    'tools/verify/verify_perky_cf_userpath.py': 'git:36c271285d42ef166bd041f015b5f91882d9f31c',
    'tools/verify/verify_perky_final_wrappers.py': 'f1d48b7d88c9411e2680d7462ae31fdc62ae5276f270fef189a66cfe67f676fc',
    'tools/verify/verify_perky_release_guards_selftest.py': '170e1093097273413415b667fd580249dcdba3eca1e294f9a2f76fd3eae6169d',
    'tools/verify/verify_perky_stock_dsp_identity.py': '1bab1de6c609232b7f79d87ebcb347430ca48adbba97110e8ec75cca55045bd3',
}

def file_digest(path: Path, expected: str) -> str:
    data = path.read_bytes()
    if expected.startswith('git:'):
        header = b'blob ' + str(len(data)).encode() + b'\0'
        return 'git:' + hashlib.sha1(header + data).hexdigest()
    return hashlib.sha256(data).hexdigest()

def main() -> None:
    failures=[]
    for rel, expected in EXPECTED.items():
        path=ROOT/rel
        if not path.is_file(): failures.append(f"{rel}: missing"); continue
        got=file_digest(path, expected)
        if got != expected: failures.append(f"{rel}: {got} != {expected}")
    if failures: raise SystemExit("PERKY qualified-source identity: FAIL\n  " + "\n  ".join(failures))
    print(f"PERKY qualified-source identity: PASS ({len(EXPECTED)} files byte-pinned to executed PCM/emulator qualification)")

if __name__ == "__main__": main()
