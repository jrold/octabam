#!/usr/bin/env python3
"""Profile PKFM20 with the already-proven read-only cost observer.

Rebind only ELF symbols and isolated output paths. The frozen Resonant profile
body still requires identical 32768-frame cycles, exact source, stock audio,
comparison dumps and final-card witness against its unprofiled control.
"""
import inspect
from pathlib import Path
import subprocess

import measure_perky_remaining_cf as remaining
import profile_perky_resonant_cost as profile

calibration = profile.calibration
ROOT = profile.ROOT
BUILD = ROOT / 'out/perky/hybrid/full-map-remaining-cf-mix-v1'
WORK = ROOT / 'out/perky/hybrid/resonant-cf-optimization/final-profile'
PROVEN_PROFILE = ROOT / 'out/perky/hybrid/resonant-cf-optimization/profiles'


def prepare_reused(work, candidate):
    work.mkdir(parents=True, exist_ok=True)
    assert not (work / 'observer').exists(), 'Never replace an existing profiling instrument'
    old_receipt_path = PROVEN_PROFILE / 'PROFILE_OBSERVER.json'
    old_receipt = profile.read(old_receipt_path)
    observer_build = profile.read(PROVEN_PROFILE / 'observer/BUILD.json')
    observer = PROVEN_PROFILE / 'observer/ot_emu_safety'
    assert calibration.sha(observer) == old_receipt['observer_sha256'] == observer_build['binary_sha256']
    frozen = profile.read(ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json')
    assert old_receipt['parent_observer_sha256'] == observer_build['parent_sha256'] == frozen['observer_sha256']
    assert calibration.sha(calibration.DEFAULT_WORK / 'observer/ot_emu_safety') == frozen['observer_sha256']
    for name, expected in old_receipt['source_sha256'].items():
        assert calibration.sha(Path(name)) == expected, ('Proven profile source changed', name)
    baseline_receipt_path = PROVEN_PROFILE / 'PKFM17-WTWT-SlapControl-NoiseTone-all14/PROFILE.json'
    baseline_receipt = profile.read(baseline_receipt_path)
    assert baseline_receipt['status'] == 'PASS_UNCHANGED_AUDIO_STATE_AND_CYCLES'
    assert baseline_receipt['source_sha256'][str(Path(profile.__file__))] == calibration.sha(Path(profile.__file__))
    metadata = profile.read(candidate / 'BUILD.json')
    assert metadata['version'] == 'PKFM20'
    elf = candidate / 'probe/platform/runtime.elf'
    assert calibration.sha(elf) == metadata['runtime_sha256']
    assert calibration.sha(candidate / 'probe/mainos_PKFM20.bin') == metadata['main_sha256']
    symbols = work / 'symbols.txt'
    lines = subprocess.check_output(['m68k-elf-nm', '-n', '-S', str(elf)], text=True)
    symbols.write_text(''.join(
        f'{int(fields[0], 16):x} {int(fields[0], 16) + int(fields[1], 16):x} {fields[3]}\n'
        for line in lines.splitlines()
        if len(fields := line.split()) == 4 and fields[2] in ('t', 'T')))
    (work / 'observer').symlink_to(PROVEN_PROFILE / 'observer', target_is_directory=True)
    calibration.save(work / 'PROFILE_OBSERVER.json', dict(
        status='REUSED_PROVEN_READ_ONLY_COST_OBSERVER_WITH_NEW_ELF_SYMBOLS',
        elf_sha256=calibration.sha(elf), symbols_sha256=calibration.sha(symbols),
        observer_sha256=calibration.sha(observer),
        parent_observer_sha256=frozen['observer_sha256'],
        source_sha256={**old_receipt['source_sha256'],
                       **{str(path): calibration.sha(path) for path in
                          (Path(__file__), Path(profile.__file__), Path(remaining.__file__))}},
        reused_observer_receipt=str(old_receipt_path),
        reused_observer_receipt_sha256=calibration.sha(old_receipt_path),
        prior_unchanged_cycle_audio_proof=str(baseline_receipt_path),
        prior_unchanged_cycle_audio_proof_sha256=calibration.sha(baseline_receipt_path),
        scope='Same observer binary/header/frozen parent; only symbol ranges and private output paths change. New-image equivalence remains mandatory.'))


def adapted_main():
    source = inspect.getsource(profile.main)
    replacements = {
        "assert build['version'] == configuration['version'] == 'PKFM17'":
            "assert build['version'] == configuration['version'] == 'PKFM20'",
        "image = source / 'probe/mainos_PKFM17.bin'":
            "image = source / 'probe' / f\"mainos_{build['version']}.bin\"",
        "'Path(_calibration_source), Path(_resonant_driver), Path(_profile_driver))}'":
            "'Path(_calibration_source), Path(_resonant_driver), Path(_profile_driver), Path(_profile_helper), Path(_remaining_driver))}'",
        "                     _profile_driver=str(Path(__file__).resolve()))":
            "                     _profile_driver=str(Path(__file__).resolve()),\n"
            "                     _profile_helper=str(Path(_profile_module.__file__).resolve()),\n"
            "                     _remaining_driver=str(Path(remaining.__file__).resolve()))",
        "(Path(__file__), Path(state.__file__), Path(resonant.__file__), Path(cost.__file__),":
            "(Path(__file__), Path(_profile_module.__file__), Path(remaining.__file__), Path(state.__file__), Path(resonant.__file__), Path(cost.__file__),",
        "        control_receipt=str(control), control_sha256=calibration.sha(control),":
            "        control_receipt=str(control), control_sha256=calibration.sha(control),\n"
            "        image_sha256=row['image_sha256'], elf_sha256=calibration.sha(elf), inputs=row['inputs'],",
    }
    for before, after in replacements.items():
        assert source.count(before) == 1, ('Frozen profile template changed', before)
        source = source.replace(before, after, 1)
    return source


def main():
    source = adapted_main()
    namespace = dict(vars(profile))
    namespace.update(__file__=str(Path(__file__).resolve()), _profile_module=profile, remaining=remaining,
                     DEFAULT_BUILD=BUILD, DEFAULT_WORK=WORK, prepare=prepare_reused)
    exec(compile(source, str(Path(__file__).resolve()), 'exec'), namespace)
    namespace['main']()


if __name__ == '__main__':
    main()
