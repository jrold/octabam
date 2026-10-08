#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [[ "$BRANCH" != "codex/perky-hardware-feedback" ]]; then
  echo "PERKY release: wrong branch: ${BRANCH:-<unknown>} (expected codex/perky-hardware-feedback)" >&2
  exit 2
fi

if ! git diff --quiet -- || ! git diff --cached --quiet --; then
  echo "PERKY release: tracked working tree is dirty; commit/stash before release" >&2
  exit 2
fi

: "${PERKONS_FIRMWARE:?set PERKONS_FIRMWARE to exact PĒRKONS v1.2.1 image}"
: "${PERKYBITS_ROOT:?set PERKYBITS_ROOT to PerkyBits checkout}"

for tool in python3 gcc g++ git m68k-elf-gcc m68k-elf-as m68k-elf-ld m68k-elf-objcopy m68k-elf-nm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "PERKY release: missing required tool: $tool" >&2
    exit 2
  fi
done

VERSION="${PERKY_VERSION:-PK4CF1}"
BUILD="${PERKY_BUILD:-6}"
WORK="${PERKY_WORK:-$ROOT/out/perky/cf-final}"

echo "PERKY release preflight"
echo "  branch : $BRANCH"
echo "  commit : $(git rev-parse HEAD)"
echo "  firmware: $PERKONS_FIRMWARE"
echo "  PerkyBits: $PERKYBITS_ROOT"
echo "  version : $VERSION"
echo "  build   : $BUILD"

python3 tools/verify/verify_perky_cf_qualified_sources.py

exec python3 tools/perky/build_cf_final.py \
  --firmware "$PERKONS_FIRMWARE" \
  --perkybits "$PERKYBITS_ROOT" \
  --build "$BUILD" \
  --version "$VERSION" \
  --work "$WORK"
