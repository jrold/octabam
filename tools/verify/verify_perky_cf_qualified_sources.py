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
    'modules/perky/cf_perky4.c': '4ff85c10fe45563e6f13866a289346305c41ac8ad501eda09efe2db07b70d019',
    'modules/perky/cf_resonant.c': '196afb963ffb00d3009546b17b970891b0d3d5684449e36d046eb68d3ac2e96b',
    'modules/perky/cf_resonant.h': 'a11636313ff7e8c2e9bf9d6ad6f40439056a46adbabc103ae843e7f69465834f',
    'modules/perky/cf_noise_hat.c': '0f4acec7d1a3df134faae121d431ff657d73e38692a4cf37283e4ee096965b0c',
    'modules/perky/cf_noise_hat.h': 'bcdb9999fe511ede8ec4fc991d2a42fd84288e4b9512d22604d6acb5d7d9287b',
    'modules/perky/cf_wavetable.c': 'e74029c09b4608d81546cc639e35605b468810588f65918dae042d963e898644',
    'modules/perky/cf_wavetable.h': '71845d1551c844e270a71456ba4f779aa4f698df9e9eb403b08105ddc1bcbffe',
    'modules/perky/cf_acoustic_hats.c': '4e3548b7b62c92466ecae76ca338182586a3e4aa9623342e574ca18a22fbf0b9',
    'modules/perky/cf_acoustic_hats.h': 'f75c74baf820c14c290574e52eebcb6949f96acc86df13aef4a04ccad19b6bfc',
    'modules/perky/cf_acoustic_hats_rate.inc': 'f9c94bf7916e04115ae0f1195b6040b216d35ad33d034a58afe23878bed44385',
    'modules/perky/cf_softfloat.h': '5cfbf0152376bef1f57994c30c0070cdd17841f404d1f53038f28b8a7179b768',
    'tools/perky/acoustic_hats_rate_table.py': '259ba9c99c1fb7f1410f585d2f6b22cb6f5648f15fb0c26ad1a6d3d765f68a3d',
    'tools/verify/perky_cf_acoustic_hats_diff.cpp': '64a681d1f7e92762da1ae0df6f6da21c73a392278eed3cb5d741d2fe47d19a75',
    'tools/verify/perky_cf_softfloat_check.c': '46e0dd3c588a925826afb53cf37fae6d0629ca637fa60c93bda21a05d398712c',
    'tools/verify/verify_perky_cf_acoustic_hats_dsp.py': '3cf2fcd4bef5e8003f1b52ee498e43b8b5c8e627adf82e69008d7e0f29626739',
    'tools/verify/perky_cf_wavetable_diff.cpp': '2d96110ca46526b89028b52449a80e627f3e36f591fbda6caf5600e7aafdf9ad',
    'tools/verify/verify_perky_cf_wavetable_dsp.py': '85799a59f5657db83066607e13ddb8580cf3156a467a66456e183bb08729ab1a',
    'modules/perky/cf_perky4.h': 'git:8d76417670c73f77a2a2ea1e18e4f2a368cf790e',
    'modules/perky/control.c': 'b7905143a0f974dfaf3a39b8a5acb5a6c7dd406bfe7073970519b5842d295d4b',
    'modules/perky/control_cf_final.c': 'git:108435896468acde6e80834fe4bf2c5d0c9ee562',
    'modules/perky/machine.s': 'git:8a9c63cf333565ce0af185b061d9cd60c6236186',
    'modules/perky/fold_control_update.py': '2999a6bd0cebd4b2f99e7c5f111708843cb23840fbe95c2bcd43e8ce356c53a7',
    'modules/perky/karplus_control_state.py': '5a7202e01aacf0e7f13ff086c8c5624b19e56ccbebcda50d1befe62f0cb8e88f',
    'modules/perky/karplus_control_update.py': '74415d3cc5d2162e65fac63df89994dbdaf3271588dbac471df9122fe02b4d36',
    'modules/perky/noise_tone_control_update.py': 'dce869a5f996f2e7f99438344c214de0ac62c2944a20886071854a204a3bfe6e',
    'modules/perky/simple_drum_control.py': 'df108a857d49ec679e4355f7def9a4a7dd76fcc0056aee31a65e4c6f66e676f3',
    'modules/perky/resonant_control_update.py': '2866f790af44676d82d5a0a3f5122706a57c53d1c1f5b633ce71ea3dfdb8c1b6',
    'modules/perky/noise_hat_control_update.py': 'b8a1caa9a3d508589bd9585e90730152061f22550ef03d58c1ac89931b0997fd',
    'modules/perky/generate_cf_final.py': '487efe3314106d686e45c47e05055ea85f05db94a499f41786b530be5bfb51d6',
    'remixes/test/perky-cf-final/remix.py': '409443c6b4e27e37c488c779a8f50e7795448acc4e56e77acb31996377945c3b',
    'tools/build/bin_decode.py': 'd092430bf99d30d39c6fa81a186a746f0bfc5c6875636a03f48d800e59a05144',
    'tools/build/build_bus.py': 'f11a293f3bd8f042c772374912441427e8d48153a07194a93c13970db1c33532',
    'tools/perky/build_cf_final.py': 'git:8f4f965ef5e270f750f1804da7451a0cad91eb43',
    'tools/verify/verify_perky_cf_odd_access.py': '6bf5f83bfe27eba4a4688e66ced9bf01464c54919dd0144bc6c8ed2478a9ae14',
    'tools/perky/build_machine_canary.py': '3c1fc5155f64a3747ae80f59c2ebc41a7c68091f4c3b18450c64d7ed0106a609',
    'tools/perky/generate_cf_final_fixtures.py': 'e67c63aebb0019a5997ac0816f059d84547d20f69bbbbce7a110cd2bae0a0317',
    'tools/perky/perky_cf_assets.py': '5d0f5bf0701f586cbd985b8abe061425175fff429f51a0678c0db4a30222a574',
    'tools/perky/perky_cf_machine_module.py': 'git:b12c6133c2aadfcc4eaa784630123fc066fea141',
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
    'tools/verify/verify_perky_cf_codegen.py': '628e793ec9cb624341c0d0efea3a2bd34a12ba1ed291fb0165cfad218ab2462f',
    'tools/verify/verify_perky_cf_final.py': '33b104c12301f2164bf6b2109c7455f59672170c62acb21275dab8f5ba1b225f',
    'tools/verify/verify_perky_cf_param_coverage.py': 'db101857edd321bce1dbe51716c4add8cc35f563d01bb3405b25707a276bce00',
    'tools/verify/perky4_param_sweep.cpp': 'c02a3fe66f35c177569f7d1f38bd1c97d9887ebc2f076e1261445f5dc1721151',
    'tools/verify/verify_perky_cf_resonant_dsp.py': '865bfbccb33004ed413509a22ee3729ce9921dbf937c1786d13b60b8211a7a69',
    'tools/verify/perky_cf_resonant_diff.cpp': '59969e18179e25a258cf8d346850c5b93772ef1377a6228413f6cb8efc9e5527',
    'tools/verify/perky4_resonant_e2e.cpp': '627606b2c1c5369cbe90b335321aee60d5ca9523fbf6b3bb6d8359206838208b',
    'tools/verify/verify_perky_cf_noise_hat_dsp.py': '661429c7e698a7f59966056df96f3ab33ae8ccbf6acf36bc2c37b01c1b260443',
    'tools/verify/perky_cf_noise_hat_diff.cpp': 'f233f8dfa2a3a9d8965d9f2e0222eb640124d567d88d04e79c53325014cf641c',
    'tools/verify/verify_perky_cf_final_control.py': '9a99ee20ea4035d7e0f68e34623d8afeb1cd7dc066aafdad7a41e8d9731de24c',
    'tools/verify/verify_perky_cf_final_remix.py': '6dea693ac33f252bf6c8b37c25f48597e64674986f5c8d80e02eee6f2a960e05',
    'tools/verify/verify_perky_cf_freestanding.py': '5499198f777f7ccfde535661432722dd89b280f2130373a80dcd0db4a13399ef',
    'tools/verify/verify_perky_cf_hotloops.py': '621ed7aa1c4502c7cb57e187e60db4f2c9d6c914c5c5e0469ae18b5bae3d60bc',
    'tools/verify/verify_perky_cf_machine_module.py': 'a39bdf3f5e9343e87d92f7a3d6e9e44a97a770d2f2c94c2017d0ba130a2f554d',
    'tools/verify/verify_perky_cf_plock_reversion.py': '641ce0251050bbff09ace813a0330eb2b0ff61347dbcef133d5c7ac700d28966',
    'tools/verify/verify_perky_cf_production_render.py': '87e8a318ca1f64722f051b955430814e3ddbe37602303a53e5c0cec9c1e684cf',
    'tools/verify/verify_perky_cf_runtime_memory_final.py': '6e645180176417f8020b44613e92ab7d2d7269d85a8022e1f71929ee99e4abd3',
    'tools/verify/verify_perky_cf_runtime_reset.py': '265c0449acc56b0b54694d1a5b7dc90c1e8ff5f9714cccc72458be0848d0b4f4',
    'tools/verify/verify_perky_cf_stock_record_abi.py': 'git:050b46893fdda12ddd45ea40a0e0395a68eda034',
    'tools/verify/verify_perky_cf_userpath.py': 'git:b55767908baefb8760eb8835c16ffafff61244f5',
    'tools/verify/verify_perky_final_wrappers.py': '4de6495980d1c9b413a4e7242a34ce68ffcf1b0d7afaab4dd852a9e32f89ca63',
    'tools/verify/verify_perky_cf_voice_silo.py': '9c5c8fc1dbb152d37181961fe134e6e6c1b8e2c78103e2c337a43b20646f1ba0',
    'modules/perky/cf_simple_drum.c': '94c16df5d2be801fc6094672c1adaab5f371b3e1cb3c85b2b1c1d8b29b810e77',
    'modules/perky/cf_simple_drum.h': '9a535090d2bd3f13cb5f360a74824658321a23330c48a7e92115a646b0631e53',
    'tools/verify/perky_cf_simple_drum_diff.cpp': 'dba75d4c5e34605c1af1eb7513c186593d9bfadabc0f4184eb9550f590b41f2e',
    'tools/verify/verify_perky_cf_simple_drum_dsp.py': '42f2594de2c1eb049e2b4c024be2d0611997c11a0ee24e7f1ec4502656b55e47',
    'tools/harness/perky_cf/capture_control_sweep.cpp': '3f32adfc3c89be9ff824a79d71aa5a6c25d5264fd3b00d87b969ca76a5b49b6b',
    'modules/perky/CONTROL_RECOVERY.md': '127fec2b5dfa62ce972fa5822097dcdc08fdcba5388048499760ae1f56a9cac9',
    'modules/perky/cf_complex_drum.c': '3fae4684d8d1dd7f00b187a682a7294431047cee6d4edac7f7c2f8f36cecbc21',
    'modules/perky/cf_complex_drum.h': '98588a85c21c8e94e1b908de10a9b4086ef0830915aa3ecf3fd971b06c0165f2',
    'tools/verify/perky_cf_complex_drum_diff.cpp': 'b9ddf0d095ae3650d7c55bc303e0834b17d5e8d62d222c80271a521e73beb918',
    'tools/verify/verify_perky_cf_complex_drum_dsp.py': '9d29738416442e0cc988a2a74038c67f87fa90385b9f59a1c15a5f8fabb271b0',
    'modules/perky/slap_coeff_table.py': '3e59df4898b8fa68488f2dcde27138d6c6da663abe977e9f18db7770f3170be1',
    'modules/perky/cf_slap.c': 'd1749f273859d12062fe8a1b9b64cd1334fcddba5636ed00f89d13d36eb7fc88',
    'modules/perky/cf_slap.h': '4d10f0e328cff102aeaf1e4a720438fac504e78965488aeac2f6d2cec8b4ed22',
    'modules/perky/cf_slap_coeff.inc': 'f70e05ea6d093270d3563fabf22eb56b999500aef42609a9cfc8b3473f29f316',
    'tools/verify/perky_cf_slap_diff.cpp': '9316192e195de0af5b7ae6af66aefba63497909bb92e4795949d1def9f038dd2',
    'tools/verify/verify_perky_cf_slap_dsp.py': '7c5cb68bd48bfa4e881afae7f65ed2ae8780ad15956375c6a5dab14949d476e9',
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
