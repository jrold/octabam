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
    'modules/perky/cf_perky4.c': 'e12ef683191cd3bd1f7c92c219b0c9f0f848cfb6d2db6d641ad9b381b228811d',
    'modules/perky/cf_resonant.c': '196afb963ffb00d3009546b17b970891b0d3d5684449e36d046eb68d3ac2e96b',
    'modules/perky/cf_resonant.h': 'a11636313ff7e8c2e9bf9d6ad6f40439056a46adbabc103ae843e7f69465834f',
    'modules/perky/cf_noise_hat.c': '0f4acec7d1a3df134faae121d431ff657d73e38692a4cf37283e4ee096965b0c',
    'modules/perky/cf_noise_hat.h': 'bcdb9999fe511ede8ec4fc991d2a42fd84288e4b9512d22604d6acb5d7d9287b',
    'modules/perky/cf_wavetable.c': 'e74029c09b4608d81546cc639e35605b468810588f65918dae042d963e898644',
    'modules/perky/cf_wavetable.h': '71845d1551c844e270a71456ba4f779aa4f698df9e9eb403b08105ddc1bcbffe',
    'tools/verify/perky_cf_wavetable_diff.cpp': '2d96110ca46526b89028b52449a80e627f3e36f591fbda6caf5600e7aafdf9ad',
    'tools/verify/verify_perky_cf_wavetable_dsp.py': '85799a59f5657db83066607e13ddb8580cf3156a467a66456e183bb08729ab1a',
    'modules/perky/cf_perky4.h': 'git:b13e6a623e2860e2aed3574b2d5d4c2bd6f369b0',
    'modules/perky/control.c': 'b7905143a0f974dfaf3a39b8a5acb5a6c7dd406bfe7073970519b5842d295d4b',
    'modules/perky/control_cf_final.c': 'git:d14f3dd4411e8b5c5c4e0148ea3577a1bc049b60',
    'modules/perky/machine.s': 'git:8a9c63cf333565ce0af185b061d9cd60c6236186',
    'modules/perky/fold_control_update.py': '2999a6bd0cebd4b2f99e7c5f111708843cb23840fbe95c2bcd43e8ce356c53a7',
    'modules/perky/karplus_control_state.py': '5a7202e01aacf0e7f13ff086c8c5624b19e56ccbebcda50d1befe62f0cb8e88f',
    'modules/perky/karplus_control_update.py': '74415d3cc5d2162e65fac63df89994dbdaf3271588dbac471df9122fe02b4d36',
    'modules/perky/noise_tone_control_update.py': 'dce869a5f996f2e7f99438344c214de0ac62c2944a20886071854a204a3bfe6e',
    'modules/perky/simple_drum_control.py': 'df108a857d49ec679e4355f7def9a4a7dd76fcc0056aee31a65e4c6f66e676f3',
    'modules/perky/resonant_control_update.py': '2866f790af44676d82d5a0a3f5122706a57c53d1c1f5b633ce71ea3dfdb8c1b6',
    'modules/perky/noise_hat_control_update.py': 'b8a1caa9a3d508589bd9585e90730152061f22550ef03d58c1ac89931b0997fd',
    'modules/perky/generate_cf_final.py': '1c9040c01632ed768d2c4d33bbc9d5e87aefda936c3e79aff54abb5ee5b42b30',
    'remixes/test/perky-cf-final/remix.py': '409443c6b4e27e37c488c779a8f50e7795448acc4e56e77acb31996377945c3b',
    'tools/build/bin_decode.py': 'd092430bf99d30d39c6fa81a186a746f0bfc5c6875636a03f48d800e59a05144',
    'tools/build/build_bus.py': 'f11a293f3bd8f042c772374912441427e8d48153a07194a93c13970db1c33532',
    'tools/perky/build_cf_final.py': 'git:a808354635ea9c0ca754f18c25df101e4c9226d0',
    'tools/verify/verify_perky_cf_odd_access.py': '6bf5f83bfe27eba4a4688e66ced9bf01464c54919dd0144bc6c8ed2478a9ae14',
    'tools/perky/build_machine_canary.py': '3c1fc5155f64a3747ae80f59c2ebc41a7c68091f4c3b18450c64d7ed0106a609',
    'tools/perky/generate_cf_final_fixtures.py': '9248c851b14e8b7ae4f63dcfa480be10d20b841dd25a6b991594a87dc49120d2',
    'tools/perky/perky_cf_assets.py': 'c439d655182f3ff7e80ad007626a90ea7a3286cadf4cfbab65c42be28525cc77',
    'tools/perky/perky_cf_machine_module.py': 'git:499e559058d24b446abf0ff9c5f30837d2230b38',
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
    'tools/verify/verify_perky_cf_codegen.py': 'cb844a81e93f36f605e5e1c7d8404c71fbf09155130aba914a0868938dd4ab37',
    'tools/verify/verify_perky_cf_final.py': 'f6037eaedf2c9e028bbd64e9034f1b4f6a87b65687a860ed253c96ab41697099',
    'tools/verify/verify_perky_cf_param_coverage.py': '20b09191004cfaffc7425c2ddb3cb06b3f71ad024c4c813042e9d3b19e6bb34e',
    'tools/verify/perky4_param_sweep.cpp': '99ede3b36050415ae483a6585140216dc88633d6c14df1f6f99ae3500e0fd928',
    'tools/verify/verify_perky_cf_resonant_dsp.py': '1f5e92abd3ba25f55bb38fc5c7df28251e680a20cc9e711f849a96f69264b80b',
    'tools/verify/perky_cf_resonant_diff.cpp': '59969e18179e25a258cf8d346850c5b93772ef1377a6228413f6cb8efc9e5527',
    'tools/verify/perky4_resonant_e2e.cpp': '627606b2c1c5369cbe90b335321aee60d5ca9523fbf6b3bb6d8359206838208b',
    'tools/verify/verify_perky_cf_noise_hat_dsp.py': 'f4f6ef9a310994584f3a4422b7b4d63e1c04604e0437fb0a636ca625d877900d',
    'tools/verify/perky_cf_noise_hat_diff.cpp': 'f233f8dfa2a3a9d8965d9f2e0222eb640124d567d88d04e79c53325014cf641c',
    'tools/verify/verify_perky_cf_final_control.py': '9a99ee20ea4035d7e0f68e34623d8afeb1cd7dc066aafdad7a41e8d9731de24c',
    'tools/verify/verify_perky_cf_final_remix.py': '6dea693ac33f252bf6c8b37c25f48597e64674986f5c8d80e02eee6f2a960e05',
    'tools/verify/verify_perky_cf_freestanding.py': '5499198f777f7ccfde535661432722dd89b280f2130373a80dcd0db4a13399ef',
    'tools/verify/verify_perky_cf_hotloops.py': '621ed7aa1c4502c7cb57e187e60db4f2c9d6c914c5c5e0469ae18b5bae3d60bc',
    'tools/verify/verify_perky_cf_machine_module.py': '651bae4dc15b6ecbbf3d653a6406cc3c4aba8c3411d7b587a1a8b8bc76965325',
    'tools/verify/verify_perky_cf_plock_reversion.py': 'b063d207c0ae4feda4adfcb8f84036cf6e47aebdb5e1c51bdc4ab0755f5d6eca',
    'tools/verify/verify_perky_cf_production_render.py': '3e80cec7dd14acbe2d5ee2c2f639c8d28040f0a0994671cc656211ee29c0b2eb',
    'tools/verify/verify_perky_cf_runtime_memory_final.py': '9dfec8288f9674c47e31166c2dec7d733c0c83020180085436a4ae9d97a48a7a',
    'tools/verify/verify_perky_cf_runtime_reset.py': 'fa6607dd7a43c3fc9739759072fdbe080d69ae3b6bfcb7ebfd815e0e48baf02d',
    'tools/verify/verify_perky_cf_stock_record_abi.py': 'git:050b46893fdda12ddd45ea40a0e0395a68eda034',
    'tools/verify/verify_perky_cf_userpath.py': 'git:818b3254296b04ad065fd97d1fe4fb93e793260c',
    'tools/verify/verify_perky_final_wrappers.py': '4de6495980d1c9b413a4e7242a34ce68ffcf1b0d7afaab4dd852a9e32f89ca63',
    'tools/verify/verify_perky_cf_voice_silo.py': '7c2b39b0974c438660e384786225ff235a75ccdf29af6c9df094171d12ae8298',
    'modules/perky/cf_simple_drum.c': '94c16df5d2be801fc6094672c1adaab5f371b3e1cb3c85b2b1c1d8b29b810e77',
    'modules/perky/cf_simple_drum.h': '9a535090d2bd3f13cb5f360a74824658321a23330c48a7e92115a646b0631e53',
    'tools/verify/perky_cf_simple_drum_diff.cpp': 'dba75d4c5e34605c1af1eb7513c186593d9bfadabc0f4184eb9550f590b41f2e',
    'tools/verify/verify_perky_cf_simple_drum_dsp.py': '42f2594de2c1eb049e2b4c024be2d0611997c11a0ee24e7f1ec4502656b55e47',
    'tools/harness/perky_cf/capture_control_sweep.cpp': 'c383791f9c0ff3ac679c70033f0766cede198d4d7aa9d0bba1c8ded5c934a4e3',
    'modules/perky/CONTROL_RECOVERY.md': '766b38efc808cb0052bb715e8fe5c2e6fd9d307333424627efa6519e46428b34',
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
