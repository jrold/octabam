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
    'modules/perky/cf_perky4.c': '73126def8d4ce1f1a3209bf49af160b7564a86df123f321397c4553b96b7bcc7',
    'modules/perky/cf_resonant.c': '196afb963ffb00d3009546b17b970891b0d3d5684449e36d046eb68d3ac2e96b',
    'modules/perky/cf_resonant.h': 'a11636313ff7e8c2e9bf9d6ad6f40439056a46adbabc103ae843e7f69465834f',
    'modules/perky/cf_noise_hat.c': '0f4acec7d1a3df134faae121d431ff657d73e38692a4cf37283e4ee096965b0c',
    'modules/perky/cf_noise_hat.h': 'bcdb9999fe511ede8ec4fc991d2a42fd84288e4b9512d22604d6acb5d7d9287b',
    'modules/perky/cf_perky4.h': 'git:3b91caec256692488ad61e553896f2970eff599d',
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
    'modules/perky/generate_cf_final.py': '3b3fa03710881eae9f538de3d063e530025d02bcfb91f84e3bc3273a1d3708ac',
    'remixes/test/perky-cf-final/remix.py': '409443c6b4e27e37c488c779a8f50e7795448acc4e56e77acb31996377945c3b',
    'tools/build/bin_decode.py': 'd092430bf99d30d39c6fa81a186a746f0bfc5c6875636a03f48d800e59a05144',
    'tools/build/build_bus.py': 'f11a293f3bd8f042c772374912441427e8d48153a07194a93c13970db1c33532',
    'tools/perky/build_cf_final.py': 'git:e6ebbce90956d9636c9b4ebe4367300e7faf3eb8',
    'tools/verify/verify_perky_cf_odd_access.py': '6bf5f83bfe27eba4a4688e66ced9bf01464c54919dd0144bc6c8ed2478a9ae14',
    'tools/perky/build_machine_canary.py': '3c1fc5155f64a3747ae80f59c2ebc41a7c68091f4c3b18450c64d7ed0106a609',
    'tools/perky/generate_cf_final_fixtures.py': 'b0ebb0c69b8c9429b9496591579a7fca04217fc2de709df6cb422dabdf2ac7e9',
    'tools/perky/perky_cf_assets.py': '1526214bf699f7bc4c9a17664e5f9ca5d871f366c3fd0bdd0d12089813c9b86b',
    'tools/perky/perky_cf_machine_module.py': 'git:1dd20f60aac17f03d918dca3641362ce0d624f4e',
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
    'tools/verify/verify_perky_cf_final.py': 'ada3a8ec6945dfaed994ace45a404c90b0ac323082f76570bb96434d3883836b',
    'tools/verify/verify_perky_cf_param_coverage.py': '4de0fe36cb4711bd772961362f05d096bc6a661ab3669b18dd5b8fe7e791c821',
    'tools/verify/perky4_param_sweep.cpp': '5444c5d9229c60e739fcc7477d5c6875c12e57e6815b094ada4f83b7f42dfbd3',
    'tools/verify/verify_perky_cf_resonant_dsp.py': '11b6d6a9421ded9e35df54503aef4f2e392f432246daacb2ed667fb2b9cd2b40',
    'tools/verify/perky_cf_resonant_diff.cpp': '59969e18179e25a258cf8d346850c5b93772ef1377a6228413f6cb8efc9e5527',
    'tools/verify/perky4_resonant_e2e.cpp': '627606b2c1c5369cbe90b335321aee60d5ca9523fbf6b3bb6d8359206838208b',
    'tools/verify/verify_perky_cf_noise_hat_dsp.py': '037e5bc59a381cd442cb5f4ed0aa648c40c249c704dff98ce48d2b1571e2775c',
    'tools/verify/perky_cf_noise_hat_diff.cpp': 'f233f8dfa2a3a9d8965d9f2e0222eb640124d567d88d04e79c53325014cf641c',
    'tools/verify/verify_perky_cf_final_control.py': '9a99ee20ea4035d7e0f68e34623d8afeb1cd7dc066aafdad7a41e8d9731de24c',
    'tools/verify/verify_perky_cf_final_remix.py': '6dea693ac33f252bf6c8b37c25f48597e64674986f5c8d80e02eee6f2a960e05',
    'tools/verify/verify_perky_cf_freestanding.py': '5499198f777f7ccfde535661432722dd89b280f2130373a80dcd0db4a13399ef',
    'tools/verify/verify_perky_cf_hotloops.py': '621ed7aa1c4502c7cb57e187e60db4f2c9d6c914c5c5e0469ae18b5bae3d60bc',
    'tools/verify/verify_perky_cf_machine_module.py': 'cd05c232398ab5b6eec2627820b0ecb2714b9ef1f03b7c7169618543cfa4b637',
    'tools/verify/verify_perky_cf_plock_reversion.py': 'f74e040040ff30328ae70f278a2ebc825dafec17ec729381c24ea2043988ddae',
    'tools/verify/verify_perky_cf_production_render.py': '501b7d275a320a0688df1f31147e6e7357489df25ed0b5c0ca99908dc9403c8d',
    'tools/verify/verify_perky_cf_runtime_memory_final.py': '0805fb85fd9dc0a5fa1fe8169c4516302931e71fee97ac8aabfe0fec1a72622f',
    'tools/verify/verify_perky_cf_runtime_reset.py': '8ad6bfdca0722569ede361d45ebc0d482f922d12480688661480e6970d020096',
    'tools/verify/verify_perky_cf_stock_record_abi.py': 'git:050b46893fdda12ddd45ea40a0e0395a68eda034',
    'tools/verify/verify_perky_cf_userpath.py': 'git:598953868faf655236b5b00b67ce0ba1421e6428',
    'tools/verify/verify_perky_final_wrappers.py': '4de6495980d1c9b413a4e7242a34ce68ffcf1b0d7afaab4dd852a9e32f89ca63',
    'tools/verify/verify_perky_cf_voice_silo.py': '6a05db5c8aaddfab40bd9e05276529dd44755894d25a64bfeb82f54a5601478a',
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
