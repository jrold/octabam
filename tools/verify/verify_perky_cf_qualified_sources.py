#!/usr/bin/env python3
"""Pin exact production/test/release sources behind Perky CF qualification."""
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    'modules/perky/cf_assets.s': '3d3d2fbf2421450e27712106c5c52dd554ab3d34df04099243b8dfef14654ca8',
    'modules/perky/cf_fold.c': '96ac7a5a7e4868670f0f159f935ad9f130582d1161088c5948f3eeccbaa7be0f',
    'modules/perky/cf_fold.h': 'e1e3d3c16065fbbfc77b3606782aef431d42ff745ae3c4105472e1444cc25996',
    'modules/perky/cf_karplus.c': '9639a1f1292ddeaf95e46a5feb38a254e2b77497d997ea50fe3f42d676052170',
    'modules/perky/cf_karplus.h': '8c311ecfa6e2eb9fe2b57c2af05a524419f44f61a002f0b94afe6ca404cd9d70',
    'modules/perky/cf_math.h': 'd621ce5f2738917e076cc74f8d3b6080b4d237e615e8f6f4fc42bc5dbdc83262',
    'modules/perky/cf_noise_tone.c': '08cbf517d53365740b5e89399233b5d4229e496bc822efe2f8aeb7af13b6eea6',
    'modules/perky/cf_noise_tone.h': '9cbf001ccbdedb4ee25cd6ec88d8d804ac442a070b1f3ac4c26470c113417d45',
    'modules/perky/cf_perky4.c': '8478ec462d6444906fc4d2e07673458509d3df0568a1cc8b06ada187e3e6fe63',
    'modules/perky/cf_resonant.c': 'd759084a0ab41fa65e11fb2d9d6d5470ffcc73a20bb1c5b839242bc3ab119499',
    'modules/perky/cf_resonant.h': 'a11636313ff7e8c2e9bf9d6ad6f40439056a46adbabc103ae843e7f69465834f',
    'modules/perky/cf_noise_hat.c': '18aac652089aa04d7e6f751dd8bba3314f63aa1a8bf7dfb1016fd421f7df8776',
    'modules/perky/cf_noise_hat.h': 'bcdb9999fe511ede8ec4fc991d2a42fd84288e4b9512d22604d6acb5d7d9287b',
    'modules/perky/cf_wavetable.c': 'e203b681ff8c6268ee32337bd8e71fb05c580ecbef0828f1fe218cc28e357ad0',
    'modules/perky/cf_wavetable.h': '71845d1551c844e270a71456ba4f779aa4f698df9e9eb403b08105ddc1bcbffe',
    'tools/verify/perky_cf_wavetable_diff.cpp': '2d96110ca46526b89028b52449a80e627f3e36f591fbda6caf5600e7aafdf9ad',
    'tools/verify/verify_perky_cf_wavetable_dsp.py': '85799a59f5657db83066607e13ddb8580cf3156a467a66456e183bb08729ab1a',
    'modules/perky/cf_perky4.h': 'git:be2b01999e5c771adca65932c5e4468059c3ca15',
    'modules/perky/control.c': 'b7905143a0f974dfaf3a39b8a5acb5a6c7dd406bfe7073970519b5842d295d4b',
    'modules/perky/control_cf_final.c': 'git:47186b60e1edb8d20579df164e76a051258a3bc4',
    'modules/perky/machine.s': 'git:8a9c63cf333565ce0af185b061d9cd60c6236186',
    'modules/perky/fold_control_update.py': '2999a6bd0cebd4b2f99e7c5f111708843cb23840fbe95c2bcd43e8ce356c53a7',
    'modules/perky/karplus_control_state.py': '5a7202e01aacf0e7f13ff086c8c5624b19e56ccbebcda50d1befe62f0cb8e88f',
    'modules/perky/karplus_control_update.py': '74415d3cc5d2162e65fac63df89994dbdaf3271588dbac471df9122fe02b4d36',
    'modules/perky/noise_tone_control_update.py': 'dce869a5f996f2e7f99438344c214de0ac62c2944a20886071854a204a3bfe6e',
    'modules/perky/simple_drum_control.py': 'df108a857d49ec679e4355f7def9a4a7dd76fcc0056aee31a65e4c6f66e676f3',
    'modules/perky/resonant_control_update.py': '2866f790af44676d82d5a0a3f5122706a57c53d1c1f5b633ce71ea3dfdb8c1b6',
    'modules/perky/noise_hat_control_update.py': 'b8a1caa9a3d508589bd9585e90730152061f22550ef03d58c1ac89931b0997fd',
    'modules/perky/generate_cf_final.py': 'ff93a6716b576dd0661cdcbb5eb3e19f2a471a6fe76ca0dba3259656c7f342ca',
    'remixes/test/perky-cf-final/remix.py': '409443c6b4e27e37c488c779a8f50e7795448acc4e56e77acb31996377945c3b',
    'tools/build/bin_decode.py': 'd092430bf99d30d39c6fa81a186a746f0bfc5c6875636a03f48d800e59a05144',
    'tools/build/build_bus.py': '4248b54852bd96643950bdac18543e750c60c69355629b150399d3dd6c45c937',
    'tools/perky/build_cf_final.py': 'git:5c2f788a0d4e1a81d012aaa9b0e7eaad656a23f6',
    'tools/verify/verify_perky_cf_odd_access.py': '6bf5f83bfe27eba4a4688e66ced9bf01464c54919dd0144bc6c8ed2478a9ae14',
    'tools/perky/build_machine_canary.py': 'af645f0b7f74b26c3cabe0d35fc60770779d3c2647f686f738a3a0e987e32d08',
    'tools/perky/generate_cf_final_fixtures.py': '9248c851b14e8b7ae4f63dcfa480be10d20b841dd25a6b991594a87dc49120d2',
    'tools/perky/perky_cf_assets.py': '067984479b88314319356c7422a933dc5bed81dfadfbd0fe4a17fa58668fb709',
    'tools/perky/perky_cf_machine_module.py': 'git:678d13efb93bccf843738e8a3e7d4eff9b955695',
    'tools/verify/perky4_control_pcm_diff.cpp': '90a485db69b5044a3bba1e8fb8ce937af90eb5786517f1fc7ea8fd185bd54361',
    'tools/verify/perky4_long_tail_diff.cpp': '40319eb8b6e3624f6c74c31e035de5241ccb0dd07ae27b0ee2231c7c4171d2b1',
    'tools/verify/perky4_nt_state_diff.cpp': '39422f49285837d60c834179b937cefb87e5b67f54e0c626d1be4efbf57001f9',
    'tools/verify/perky4_render_stress.cpp': '4492720f00fcdd1041af22485ba124b05f33d87063bcfffedb6eb3dba47660c5',
    'tools/verify/perky4_sequence_diff.cpp': 'db15b944d082952e423b98e274fbf3006c85163f9a22de243758d97582f87bb7',
    'tools/verify/perky4_state_diff.cpp': '90bcd64afb7833e12f2e31325c47db3ae94a3990d5cd6cb2b24b1592a75975eb',
    'tools/verify/perky_cf_plock_reversion_diff.cpp': 'git:d877a3d919769d3f3fccc1cdcbe296b9c1bbadcc',
    'tools/verify/perky_cf_production_render_diff.cpp': 'git:a774d8ad6510437addf7c0ed65c96dc690c0d745',
    'tools/verify/perky_cf_runtime_reset_diff.cpp': 'git:10627814a806a3afa9a59e755ce12684ded54989',
    'tools/verify/perky_cf_split_plock_timing.cpp': '8e08b88933c34ebed63f3e1cb8334ccac885f9ee71484ad8b77ae1bda723e3af',
    'tools/verify/perky_cf_stock_slot_diff.cpp': '7d253ad482def43f34ea2c86c31ca101d93a592c5a12c8197037656422cd26b3',
    'tools/verify/verify_perky_cf_codegen.py': '32fe01b394609842bb4988e40ae1db829f2a27047d05f7fd47249f032b17d029',
    'tools/verify/verify_perky_cf_final.py': 'fa4208e3ccddd1eccf4a368edb48737ce47d74cefe2f371255b46c4deeb6d04b',
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
    'tools/verify/verify_perky_cf_machine_module.py': 'e42c2c1a50fc0cdefec1e278617f23d6cf46747c345b3b3fc80916a64ce810a1',
    'tools/verify/verify_perky_cf_plock_reversion.py': 'c2fb6847bbbd6806c5bc1d53ce677905ac299255811bd57d96e5de52e4547a6b',
    'tools/verify/verify_perky_cf_production_render.py': 'acc4bfafcaacc17fbf01b9d9364cd6bdb00087687a58c34cd64727faf9801004',
    'tools/verify/verify_perky_cf_runtime_memory_final.py': 'ddc1a6c18a9227e7cab992d9bbe33e7f432ac54281c005e16127b2d574ab3465',
    'tools/verify/verify_perky_cf_runtime_reset.py': '4a5710b1a4795f21d5a2c4966f2f7eb8d4609c318a1d125f7942f6800ced6d67',
    'tools/verify/verify_perky_cf_stock_record_abi.py': 'git:050b46893fdda12ddd45ea40a0e0395a68eda034',
    'tools/verify/verify_perky_cf_userpath.py': 'git:d33c479d7c749e7d027e69ff4afda419ab3c01b1',
    'tools/verify/verify_perky_final_wrappers.py': '4de6495980d1c9b413a4e7242a34ce68ffcf1b0d7afaab4dd852a9e32f89ca63',
    'tools/verify/verify_perky_cf_voice_silo.py': 'a98abbed07961232c26d5e3c09d2eb9ac1891493dba812139d9afee546497d38',
    'modules/perky/cf_simple_drum.c': 'abc62704ce6a8b4a5580aa5fe75746e2c35442e0b84c8a49cc3cc11497512a8c',
    'modules/perky/cf_simple_drum.h': '9a535090d2bd3f13cb5f360a74824658321a23330c48a7e92115a646b0631e53',
    'tools/verify/perky_cf_simple_drum_diff.cpp': 'dba75d4c5e34605c1af1eb7513c186593d9bfadabc0f4184eb9550f590b41f2e',
    'tools/verify/verify_perky_cf_simple_drum_dsp.py': '42f2594de2c1eb049e2b4c024be2d0611997c11a0ee24e7f1ec4502656b55e47',
    'tools/harness/perky_cf/capture_control_sweep.cpp': '3f32adfc3c89be9ff824a79d71aa5a6c25d5264fd3b00d87b969ca76a5b49b6b',
    'modules/perky/CONTROL_RECOVERY.md': '2317526f744af8331e21bfdc58355d5a304b57e31c7fcd000966f848d08a1b9c',
    'modules/perky/cf_complex_drum.c': 'c57c9e5f89b534c165bd5e8b7e65ac666e2496de6bd773f1d7102f408090ab7e',
    'modules/perky/cf_complex_drum.h': '98588a85c21c8e94e1b908de10a9b4086ef0830915aa3ecf3fd971b06c0165f2',
    'tools/verify/perky_cf_complex_drum_diff.cpp': 'b9ddf0d095ae3650d7c55bc303e0834b17d5e8d62d222c80271a521e73beb918',
    'tools/verify/verify_perky_cf_complex_drum_dsp.py': '9d29738416442e0cc988a2a74038c67f87fa90385b9f59a1c15a5f8fabb271b0',
    'modules/perky/slap_coeff_table.py': '3e59df4898b8fa68488f2dcde27138d6c6da663abe977e9f18db7770f3170be1',
    'modules/perky/cf_slap.c': 'e0e0a62c8112ceb5b9fe8bb7108feb7e7e396f89f43099e2e55f4107d692ab2b',
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
