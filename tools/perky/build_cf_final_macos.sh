#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  tools/perky/build_cf_final_macos.sh [build_cf_final.py arguments]

Examples:
  PERKONS_FIRMWARE=/path/to/perkons_both_v1.2.1-0-gbcccfd0.img \
  PERKYBITS_ROOT=/path/to/perkybits \
  tools/perky/build_cf_final_macos.sh

  tools/perky/build_cf_final_macos.sh \
    --firmware /path/to/perkons_both_v1.2.1-0-gbcccfd0.img \
    --perkybits /path/to/perkybits \
    --version PK4CF1

Environment:
  PERKY_NO_BREW_INSTALL=1   Refuse to install missing m68k-elf-gcc.
EOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build-perky-cf-final-macos: this launcher is for macOS" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "build-perky-cf-final-macos: python3 is required" >&2
  exit 2
fi

# Homebrew may be installed but absent from PATH in non-login shells.
if ! command -v brew >/dev/null 2>&1; then
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$candidate" ]]; then
      eval "$("$candidate" shellenv)"
      break
    fi
  done
fi

need_toolchain=0
for tool in m68k-elf-gcc m68k-elf-as m68k-elf-ld m68k-elf-objcopy m68k-elf-nm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    need_toolchain=1
    break
  fi
done

if (( need_toolchain )); then
  if [[ "${PERKY_NO_BREW_INSTALL:-0}" == "1" ]]; then
    echo "build-perky-cf-final-macos: ColdFire toolchain missing and PERKY_NO_BREW_INSTALL=1" >&2
    exit 2
  fi
  if ! command -v brew >/dev/null 2>&1; then
    echo "build-perky-cf-final-macos: Homebrew is required to install m68k-elf-gcc" >&2
    echo "Install Homebrew, then rerun this command." >&2
    exit 2
  fi
  echo "==> Installing Homebrew m68k-elf-gcc (includes m68k-elf-binutils dependency)"
  brew install m68k-elf-gcc
fi

# Fail here with a compact error rather than after the expensive PCM suite.
for tool in m68k-elf-gcc m68k-elf-as m68k-elf-ld m68k-elf-objcopy m68k-elf-nm; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "build-perky-cf-final-macos: missing $tool after toolchain setup" >&2
    exit 2
  }
done

printf 'int perky_cf_toolchain_probe(void){return 0;}\n' | \
  m68k-elf-gcc -mcpu=54455 -msoft-float -O2 -ffreestanding -fno-builtin \
    -x c -S - -o /dev/null

echo "==> ColdFire toolchain: $(m68k-elf-gcc -dumpfullversion)"
echo "==> Running guarded Perky final release build"
exec python3 tools/perky/build_cf_final.py "$@"
