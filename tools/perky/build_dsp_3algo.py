#!/usr/bin/env python3
"""Compose and build the reduced two-voice / three-algorithm Perky DSP image.

This is the build front end for the reduced target: it takes the COMPOSED DSP
source (``build_dsp_3algo_source.py``), installs it into the in-memory PERKY
module together with the source-machine ColdFire plumbing the repository
already has, builds the vetted ``perky-dsp-3algo`` remix, and drives the result
through every non-physical gate the repository offers.

The FX sacrifice is not chosen here. ``verify_perky_3algo_sacrifice.py``
measures the composed program against the stock effect spans and the remix
lists exactly the effects that measurement allows; this wrapper refuses to
build if that gate does not pass, so a packaging decision can never drift away
from the numbers.

Nothing in this script flashes hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "tools/remix"), str(ROOT / "tools/build"),
                str(ROOT / "modules/perky")]

REMIX = "perky-dsp-3algo"
DEFAULT_WORK = ROOT / "out/perky/dsp-3algo"
DEFAULT_MAINOS = ROOT / "out/mainos_perky_dsp_3algo.bin"


def die(message: str) -> "NoReturn":
    raise SystemExit("build-perky-dsp-3algo: " + message)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        die(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        die(f"generated source {path} must live under the repository root")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(label: str, script: Path, **env_extra) -> None:
    if not script.exists():
        die(f"missing gate {script}")
    print(f"  -> {label}")
    env = os.environ.copy()
    env.update({k: str(v) for k, v in env_extra.items()})
    result = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env)
    if result.returncode:
        die(f"gate failed: {label} ({script}, exit {result.returncode})")


def preflight() -> None:
    """Every gate that must pass before an image is worth packaging.

    The first two are the load-bearing ones for this target:

    * the composed renderers must be instruction-identical to the qualified
      standalone ones (``verify_perky_3algo_equivalence``);
    * the FX sacrifice must be the measured minimum
      (``verify_perky_3algo_sacrifice``).

    The rest are the repository's own DSP and image checks.
    """
    print(f"=== {REMIX} 0/4: composed-renderer and sacrifice preflight ===")
    run("composed renderer equivalence",
        ROOT / "tools/verify/verify_perky_3algo_equivalence.py")
    run("measured FX sacrifice",
        ROOT / "tools/verify/verify_perky_3algo_sacrifice.py")


def build(work: Path, mainos: Path, *, build_number: int, version: str) -> None:
    preflight()
    work.mkdir(parents=True, exist_ok=True)

    builder = load("three_algo_builder", ROOT / "tools/perky/build_dsp_3algo_source.py")
    composed_entry = builder.P.rstrip("_") + "_source"
    dsp_source = work / "perky_3algo.asm"
    text = builder.normalize(builder.compose())
    # The module declaration's DspHook names the probe's seam label. The
    # composed machine's entry point is the same seam under the composer's
    # name, so publish it under the label the hook expects.
    if "\npk_probe_source:" in text:
        die("the composed source already defines pk_probe_source")
    text = text.replace("\n" + composed_entry + ":",
                        "\n" + composed_entry + ":\npk_probe_source:", 1)
    if "\npk_probe_source:" not in text:
        die(f"could not publish pk_probe_source from {composed_entry}")
    dsp_source.write_text(text)
    words = builder.measure(text, dsp_source)
    print(f"=== {REMIX} 1/4: composed DSP source: {words} P words ===")

    # The ColdFire side is the repository's existing source-machine plumbing:
    # The ColdFire side is generated from the authoritative `control.c`, and it
    # MUST be generated with the three-algorithm defines: the Fold dispatch is
    # behind PK_FOLD_CANDIDATE and the Resonant family behind
    # PK_RESONANT_CANDIDATE, and both default to 0. Built without them the
    # artifact silently contains no fold and no resonant path, and all three of
    # this machine's algorithms fall through to the `else` that zeroes every
    # prepared control -- the source would look right and the image would not be.
    control_source = work / "control.s"
    generator = load("perky_control_generate", ROOT / "modules/perky/generate.py")
    generator.write(control_source, defines=generator.THREE_ALGORITHM_DEFINES)
    if not control_source.exists() or control_source.stat().st_size == 0:
        die("ColdFire generator returned no control assembly")
    # Assert the ARTIFACT, not the intent: a define that did not reach the
    # compiler leaves a file that still assembles and still links.
    control_text = control_source.read_text()
    for symbol in ("pk_fold_prepare", "pk_resonant_prepare"):
        if symbol not in control_text:
            die(f"generated control.s does not contain {symbol} -- it was "
                f"compiled without the three-algorithm defines")

    print(f"=== {REMIX} 2/4: install the composed source and build ===")
    # The tracked manifest is the impulse probe. The composed machine is
    # installed IN MEMORY ONLY, exactly as the repository's other canary
    # builders do: machine.s + generated control ABI as DRAM-linked ColdFire
    # units, the measured source-machine detour/poke map, and the composed DSP
    # source in place of the probe glue.
    import remix.registry as registry
    machine_module = load("perky_machine_module",
                          ROOT / "tools/perky/perky_machine_module.py")
    modules = registry.modules()
    key = "PERKY PROBE"
    if key not in modules:
        die(f"registry has no {key!r}")
    original = modules[key]
    full = machine_module.build(
        original,
        control_source=repo_relative(control_source),
        dsp_source=repo_relative(dsp_source),
    )
    # The composed source is a full machine, not the isolated seam probe: it
    # carries its own entry point, so the hook is installed against it.
    prior = {k: os.environ.get(k) for k in ("REMIX", "BUILD")}
    try:
        modules[key] = full
        os.environ["REMIX"] = REMIX
        os.environ["BUILD"] = str(build_number)
        runpy.run_path(str(ROOT / "tools/build/build_bus.py"), run_name="__main__")
    finally:
        modules[key] = original
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    normal_image = ROOT / "out/mainos_bus.bin"
    if not normal_image.exists():
        die("the build returned without out/mainos_bus.bin")

    print(f"=== {REMIX} 3/4: image structure ===")
    print(f"  MAIN OS  : {normal_image} ({normal_image.stat().st_size:,} bytes)")
    print(f"  sha256   : {sha256(normal_image)}")
    print(f"  composed : {words} P words")

    print(f"=== {REMIX} 4/4: validate the shipped artifact ===")
    run("composed image placement and admission",
        ROOT / "tools/verify/verify_perky_3algo_image.py",
        IMAGE=str(normal_image))
    print("  Next: the T1/T5 algorithm-selection control law on the ColdFire")
    print("  path, then the boot/port gates against this image.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK)
    ap.add_argument("--mainos", type=Path, default=DEFAULT_MAINOS)
    ap.add_argument("--build", type=int, default=1)
    ap.add_argument("--version", default=None)
    args = ap.parse_args()
    if not 0 <= args.build <= 99:
        die("--build must be 0..99")
    version = args.version or f"PK3A{args.build}"
    if not (1 <= len(version) <= 10 and version.isascii()
            and not any(c.isspace() for c in version)):
        die("--version must be 1..10 ASCII non-whitespace characters")
    build(args.work, args.mainos, build_number=args.build, version=version)


if __name__ == "__main__":
    main()
