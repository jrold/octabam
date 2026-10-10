#!/usr/bin/env python3
"""Pin exact production/test/release sources behind Perky CF qualification."""
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    'modules/perky/cf_assets.s': '3d3d2fbf2421450e27712106c5c52dd554ab3d34df04099243b8dfef14654ca8',
    'modules/perky/cf_fold.c': '5cef1e4c0bba43de5d1192f988d8ab554555941d56d3af1b1ee0b38e31a7f53b',
    'modules/perky/cf_fold.h': 'e1e3d3c16065fbbfc77b3606782aef431d42ff745ae3c4105472e1444cc25996',
    'modules/perky/cf_karplus.c': '9329f5b7e5c98f2bd96d8b64ceec3c05e6934cfdf2a9bf7f8d32aabe755b281c',
    'modules/perky/cf_karplus.h': '8c311ecfa6e2eb9fe2b57c2af05a524419f44f61a002f0b94afe6ca404cd9d70',
    'modules/perky/cf_math.h': '1de0de1e7eb341fda2d30a8a12733feacf4e3a29dfc25b81692ab2ac0c8792be',
    'modules/perky/cf_noise_tone.c': '2da69911a55b35be844ac9fd6169014fada78f0aa41cb4ab1136ed38bfb14d0c',
    'modules/perky/cf_noise_tone.h': '9cbf001ccbdedb4ee25cd6ec88d8d804ac442a070b1f3ac4c26470c113417d45',
    'modules/perky/cf_perky4.c': 'aab59ab785a82c75497a3c40822a913bf712201e992a03679748a0bcde1f5a3c',
    'modules/perky/cf_resonant.c': '196afb963ffb00d3009546b17b970891b0d3d5684449e36d046eb68d3ac2e96b',
    'modules/perky/cf_resonant.h': 'a11636313ff7e8c2e9bf9d6ad6f40439056a46adbabc103ae843e7f69465834f',
    'modules/perky/cf_noise_hat.c': '0f4acec7d1a3df134faae121d431ff657d73e38692a4cf37283e4ee096965b0c',
    'modules/perky/cf_noise_hat.h': 'bcdb9999fe511ede8ec4fc991d2a42fd84288e4b9512d22604d6acb5d7d9287b',
    'modules/perky/cf_perky4.h': 'git:3772502be70d8f9cd5ba038841ac8ef94b2361f1',
    'modules/perky/control.c': 'b7905143a0f974dfaf3a39b8a5acb5a6c7dd406bfe7073970519b5842d295d4b',
    'modules/perky/control_cf_final.c': 'git:ae436d8281174c09d8191ff1ee48fdbdaff9232d',
    'modules/perky/machine.s': 'git:8a9c63cf333565ce0af185b061d9cd60c6236186',
    'modules/perky/fold_control_update.py': '2999a6bd0cebd4b2f99e7c5f111708843cb23840fbe95c2bcd43e8ce356c53a7',
    'modules/perky/karplus_control_state.py': '5a7202e01aacf0e7f13ff086c8c5624b19e56ccbebcda50d1befe62f0cb8e88f',
    'modules/perky/karplus_control_update.py': '74415d3cc5d2162e65fac63df89994dbdaf3271588dbac471df9122fe02b4d36',
    'modules/perky/noise_tone_control_update.py': 'dce869a5f996f2e7f99438344c214de0ac62c2944a20886071854a204a3bfe6e',
    'modules/perky/simple_drum_control.py': 'df108a857d49ec679e4355f7def9a4a7dd76fcc0056aee31a65e4c6f66e676f3',
    'modules/perky/resonant_control_update.py': '2866f790af44676d82d5a0a3f5122706a57c53d1c1f5b633ce71ea3dfdb8c1b6',
    'modules/perky/noise_hat_control_update.py': 'b8a1caa9a3d508589bd9585e90730152061f22550ef03d58c1ac89931b0997fd',
    'modules/perky/generate_cf_final.py': 'bf19d2aacabb103eb1bd299cb5c7787239bf22cf378274bb103b7e35450e291a',
    'remixes/test/perky-cf-final/remix.py': '409443c6b4e27e37c488c779a8f50e7795448acc4e56e77acb31996377945c3b',
    'tools/build/bin_decode.py': 'd092430bf99d30d39c6fa81a186a746f0bfc5c6875636a03f48d800e59a05144',
    'tools/build/build_bus.py': 'f11a293f3bd8f042c772374912441427e8d48153a07194a93c13970db1c33532',
    'tools/perky/build_cf_final.py': 'git:960ca6130bd1f405ba647cbc93801588983ad903',
    'tools/verify/verify_perky_cf_odd_access.py': '6bf5f83bfe27eba4a4688e66ced9bf01464c54919dd0144bc6c8ed2478a9ae14',
    'tools/perky/build_machine_canary.py': '3c1fc5155f64a3747ae80f59c2ebc41a7c68091f4c3b18450c64d7ed0106a609',
    'tools/perky/generate_cf_final_fixtures.py': 'b0ebb0c69b8c9429b9496591579a7fca04217fc2de709df6cb422dabdf2ac7e9',
    'tools/perky/perky_cf_assets.py': '1526214bf699f7bc4c9a17664e5f9ca5d871f366c3fd0bdd0d12089813c9b86b',
    'tools/perky/perky_cf_machine_module.py': 'git:71463eba1865e5d100082e5f88d6147b8639220c',
    'tools/verify/perky4_control_pcm_diff.cpp': '90a485db69b5044a3bba1e8fb8ce937af90eb5786517f1fc7ea8fd185bd54361',
    'tools/verify/perky4_long_tail_diff.cpp': '40319eb8b6e3624f6c74c31e035de5241ccb0dd07ae27b0ee2231c7c4171d2b1',
    'tools/verify/perky4_nt_state_diff.cpp': '39422f49285837d60c834179b937cefb87e5b67f54e0c626d1be4efbf57001f9',
    'tools/verify/perky4_render_stress.cpp': '4492720f00fcdd1041af22485ba124b05f33d87063bcfffedb6eb3dba47660c5',
    'tools/verify/perky4_sequence_diff.cpp': 'db15b944d082952e423b98e274fbf3006c85163f9a22de243758d97582f87bb7',
    'tools/verify/perky4_state_diff.cpp': '90bcd64afb7833e12f2e31325c47db3ae94a3990d5cd6cb2b24b1592a75975eb',
    'tools/verify/perky_cf_plock_reversion_diff.cpp': 'git:43886a10aa85e5716637a731ab77491de1e6a654',
    'tools/verify/perky_cf_production_render_diff.cpp': 'git:d2c15cf138c867989d41d3009a2fd40863057eec',
    'tools/verify/perky_cf_runtime_reset_diff.cpp': 'git:99eee126c66732a5275ca642a0e53e1ffacc2e5c',
    'tools/verify/perky_cf_split_plock_timing.cpp': '535e1c615a4186e633c8566952f9da77690124f7f8626f2d4eafecf2e60b0fe1',
    'tools/verify/perky_cf_stock_slot_diff.cpp': '7d253ad482def43f34ea2c86c31ca101d93a592c5a12c8197037656422cd26b3',
    'tools/verify/verify_perky_cf_codegen.py': '4c20c436ab01876a9c57da1c589341d18c80c7295a9bf8465390d933733cc076',
    'tools/verify/verify_perky_cf_final.py': 'e325a5b9f6060029874b8a333ecd654a64b3164b48d9c9b6302815e95cd8c266',
    'tools/verify/verify_perky_cf_param_coverage.py': '1a3809fbd1b890eb06ec2c6e41b0060337e0b37cb672dcd83ea26faff9eac8b1',
    'tools/verify/perky4_param_sweep.cpp': '39f4f352a13422a7df40acd8d659336bd049d3a83a23b0ee4a65eeb0ef7359eb',
    'tools/verify/verify_perky_cf_resonant_dsp.py': 'e5e468e34c6b705a6857bc3670a7b59d23da097984fccb79696574a3f4a31e4e',
    'tools/verify/perky_cf_resonant_diff.cpp': '59969e18179e25a258cf8d346850c5b93772ef1377a6228413f6cb8efc9e5527',
    'tools/verify/perky4_resonant_e2e.cpp': '627606b2c1c5369cbe90b335321aee60d5ca9523fbf6b3bb6d8359206838208b',
    'tools/verify/verify_perky_cf_noise_hat_dsp.py': '6d18c78a5d9f9edda7fceef91aa6cdb764fdf564a6ca610c11de9e3d84673037',
    'tools/verify/perky_cf_noise_hat_diff.cpp': 'f233f8dfa2a3a9d8965d9f2e0222eb640124d567d88d04e79c53325014cf641c',
    'tools/verify/verify_perky_cf_final_control.py': '9a99ee20ea4035d7e0f68e34623d8afeb1cd7dc066aafdad7a41e8d9731de24c',
    'tools/verify/verify_perky_cf_final_remix.py': '6dea693ac33f252bf6c8b37c25f48597e64674986f5c8d80e02eee6f2a960e05',
    'tools/verify/verify_perky_cf_freestanding.py': '5499198f777f7ccfde535661432722dd89b280f2130373a80dcd0db4a13399ef',
    'tools/verify/verify_perky_cf_hotloops.py': '621ed7aa1c4502c7cb57e187e60db4f2c9d6c914c5c5e0469ae18b5bae3d60bc',
    'tools/verify/verify_perky_cf_machine_module.py': '57f2479e73ed12acd27939084edc555b7d4e29853a8c77ab647e9f40437dea69',
    'tools/verify/verify_perky_cf_plock_reversion.py': '25af60dc3439946fb0f6d06e779fcb850402fa8a571b0ec527a91e4ece875d3c',
    'tools/verify/verify_perky_cf_production_render.py': '865d85c6cfe2de37bb4a5fdd109f349152682b768b84b097512a52e392fb03b7',
    'tools/verify/verify_perky_cf_runtime_memory_final.py': '7262ee02c48b18c8872709745b0fcda5d64b33e48d846922cda888db28f228d9',
    'tools/verify/verify_perky_cf_runtime_reset.py': 'aee956a8d8b2fd8a0b56df772a283e86578aa0d8ce52b35002112852ceb6a03b',
    'tools/verify/verify_perky_cf_stock_record_abi.py': 'git:050b46893fdda12ddd45ea40a0e0395a68eda034',
    'tools/verify/verify_perky_cf_userpath.py': 'git:ea4656e441d5a96db6c5ba52b2da1690735c2345',
    'tools/verify/verify_perky_final_wrappers.py': '4de6495980d1c9b413a4e7242a34ce68ffcf1b0d7afaab4dd852a9e32f89ca63',
    'tools/verify/verify_perky_cf_voice_silo.py': '411375e4259224fb4c7c092a2a77a13b00a3835a5033c3f97b8067a30ce5caa9',
    'modules/perky/cf_simple_drum.c': '94c16df5d2be801fc6094672c1adaab5f371b3e1cb3c85b2b1c1d8b29b810e77',
    'modules/perky/cf_simple_drum.h': '9a535090d2bd3f13cb5f360a74824658321a23330c48a7e92115a646b0631e53',
    'tools/verify/perky_cf_simple_drum_diff.cpp': 'dba75d4c5e34605c1af1eb7513c186593d9bfadabc0f4184eb9550f590b41f2e',
    'tools/verify/verify_perky_cf_simple_drum_dsp.py': '42f2594de2c1eb049e2b4c024be2d0611997c11a0ee24e7f1ec4502656b55e47',
    'tools/harness/perky_cf/capture_control_sweep.cpp': 'ed463a776e8c7a87920d7bd0d268b5dc262f6872ea5872eaaa673ba7f8e60e83',
    'modules/perky/CONTROL_RECOVERY.md': '73d64d79b9e4ea32ce88343608a630bc40bfb48c519efad25d6f454283407bd3',
    'modules/perky/cf_complex_drum.c': '3fae4684d8d1dd7f00b187a682a7294431047cee6d4edac7f7c2f8f36cecbc21',
    'modules/perky/cf_complex_drum.h': '98588a85c21c8e94e1b908de10a9b4086ef0830915aa3ecf3fd971b06c0165f2',
    'tools/verify/perky_cf_complex_drum_diff.cpp': 'b9ddf0d095ae3650d7c55bc303e0834b17d5e8d62d222c80271a521e73beb918',
    'tools/verify/verify_perky_cf_complex_drum_dsp.py': '9d29738416442e0cc988a2a74038c67f87fa90385b9f59a1c15a5f8fabb271b0',
    'tools/verify/verify_perky_cf_realtime_budget.py': 'cf367ad63013aca914433ec3224f4504e0473e48a3fcf5a386a98c1d372eb0db',
    'tools/verify/verify_perky_release_guards_selftest.py': '170e1093097273413415b667fd580249dcdba3eca1e294f9a2f76fd3eae6169d',
    'tools/verify/verify_perky_stock_dsp_identity.py': '1bab1de6c609232b7f79d87ebcb347430ca48adbba97110e8ec75cca55045bd3',
    'tools/verify/perky4_noise_hat_e2e.cpp': '88c3104bf5f6804ec2293d09ba29c8e01167395481a4ff0237ce302fa04e23ec',
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
