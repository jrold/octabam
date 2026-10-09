#!/usr/bin/env bash
set -euo pipefail

# Local-only, fail-closed PERKY Machines release runner.
# No GitHub Actions/CI. This script deliberately builds and executes the real
# Octabam emulator on the operator's machine, then delegates to the strict
# release entry point. A flashable wrapper is refused unless all of these pass:
#   * bit/exact PerkyBits PCM qualification;
#   * long four-voice ot_emu sequencer + stock FLEX regression;
#   * real MKII panel selection from ordinary FLEX -> PERKY + audible T1 PCM.

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

fail() {
  echo "PERKY local release: FAIL: $*" >&2
  exit 1
}

branch="$(git branch --show-current)"
[[ "$branch" == "perky-machines" ]] || fail "must run on perky-machines (current: ${branch:-DETACHED})"

# Do not qualify bytes different from the checked-in branch. Ignore untracked
# build/output files; tracked edits would make the Git commit in the release
# manifest lie about what was actually built.
if ! git diff --quiet || ! git diff --cached --quiet; then
  git status --short
  fail "tracked working-tree/index changes present; commit or discard them first"
fi

echo "PERKY local release"
echo "  branch : $branch"
echo "  commit : $(git rev-parse HEAD)"

PERKONS_FIRMWARE="${PERKONS_FIRMWARE:-$HOME/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img}"
PERKYBITS_ROOT="${PERKYBITS_ROOT:-$HOME/Downloads/perkybits}"
OT_PROJECT="${OT_PROJECT:-$HOME/Documents/octatrack backup/##Scratch}"
BUILD_NO="${1:-80}"
VERSION="${2:-PK4CF${BUILD_NO}}"

[[ "$BUILD_NO" =~ ^[0-9]+$ ]] || fail "build number must be an integer"
[[ ${#VERSION} -le 10 ]] || fail "version '$VERSION' exceeds Octatrack's 10-character field"
[[ -f "$PERKONS_FIRMWARE" ]] || fail "missing PĒRKONS v1.2.1 image: $PERKONS_FIRMWARE"
[[ -f "$PERKYBITS_ROOT/Source/NativeV121FoldDrums.cpp" ]] || fail "missing PerkyBits checkout: $PERKYBITS_ROOT"
[[ -f "$OT_PROJECT/project.work" ]] || fail "missing Octatrack project: $OT_PROJECT"

echo "  PĒRKONS: $PERKONS_FIRMWARE"
echo "  PerkyBits: $PERKYBITS_ROOT ($(git -C "$PERKYBITS_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown))"
echo "  project: $OT_PROJECT"
echo "  version: $VERSION / build $BUILD_NO"

# The user's established Octabam setup already has these in normal use. Keep
# the runner self-healing for a cleaned checkout without ever invoking cloud CI.
if ! command -v m68k-elf-gcc >/dev/null 2>&1; then
  echo "== ColdFire toolchain missing; running local setup =="
  make setup
fi
command -v m68k-elf-gcc >/dev/null 2>&1 || fail "m68k-elf-gcc still unavailable after make setup"

if [[ ! -f out/raw/section_3_MAIN_OS.bin ]]; then
  echo "== Stock MAIN OS extraction missing; rebuilding locally =="
  make recon
fi
[[ -f out/raw/section_3_MAIN_OS.bin ]] || fail "stock MAIN OS extraction still missing"

if [[ ! -x .venv/bin/python3 ]]; then
  echo "== Emulator Python environment missing; provisioning locally =="
  make emu-setup
fi
[[ -x .venv/bin/python3 ]] || fail ".venv/bin/python3 missing after make emu-setup"

# Always re-pin/re-apply the exact emulator core sources before the release run.
# scripts/vendor.sh is idempotent and uses the commits pinned by Octabam.
echo "== Pin Octatrack emulator cores locally =="
scripts/vendor.sh mc68k dsp56300

# Always rebuild the actual whole-machine emulator from current source/vendor
# bytes. Do not reuse a mystery binary from an older PERKY experiment.
echo "== Build real Octatrack emulator =="
cmake --fresh -B out/emu -S tools/emu/ot_emu -DCMAKE_OSX_ARCHITECTURES="$(uname -m)"
cmake --build out/emu -j8
[[ -x out/emu/ot_emu ]] || fail "ot_emu build did not produce out/emu/ot_emu"

# Gate the emulator itself before trusting it with PERKY. These are Octabam's
# CPU/EMAC/peripheral/RTOS/DSP-upload contracts, run locally (never Actions).
echo "== Qualify emulator core =="
ctest --test-dir out/emu --output-on-failure -R '^(emac|periph|rtos|dsp)$'

mkdir -p out/perky/cf-final
LOG="out/perky/cf-final/release-${VERSION}.log"

echo "== Run strict PERKY PCM + four-voice + real-panel whole-machine release =="
set +e
.venv/bin/python3 tools/perky/build_cf_final_strict.py \
  --firmware "$PERKONS_FIRMWARE" \
  --perkybits "$PERKYBITS_ROOT" \
  --project "$OT_PROJECT" \
  --build "$BUILD_NO" \
  --version "$VERSION" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e

if [[ $rc -ne 0 ]]; then
  echo
  echo "PERKY local release: FAILED (no qualified firmware should be used)"
  echo "log: $LOG"
  exit "$rc"
fi

grep -q '^PERKY CF FINAL BUILD: PASS$' "$LOG" || fail "base builder exited 0 without final PASS marker"
grep -q '^  PCM qualification : PASS$' "$LOG" || fail "missing PCM PASS marker"
grep -q '^  emulator user path: PASS$' "$LOG" || fail "missing four-voice ot_emu PASS marker"
grep -q '^PERKY CF REAL PANEL USER PATH: PASS$' "$LOG" || fail "missing real-panel ot_emu PASS marker"
grep -q '^PERKY CF STRICT RELEASE: PASS$' "$LOG" || fail "missing strict release PASS marker"

echo
echo "============================================================"
echo "PERKY MACHINES: READY FOR OCTATRACK HARDWARE TEST"
echo "branch : perky-machines"
echo "commit : $(git rev-parse HEAD)"
echo "log    : $LOG"
echo "============================================================"
find out -maxdepth 1 -type f \( -name "*${VERSION}*.bin" -o -name "*${VERSION}*.syx" -o -name "*${VERSION}*.txt" \) -print | sort
