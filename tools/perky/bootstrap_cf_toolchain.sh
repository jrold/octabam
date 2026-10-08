#!/bin/sh
set -eu

need_tools='m68k-elf-gcc m68k-elf-as m68k-elf-ld m68k-elf-objcopy m68k-elf-nm'
missing=''
for tool in $need_tools; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        missing="$missing $tool"
    fi
done

if [ -n "$missing" ]; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "PERKY CF toolchain: missing:$missing" >&2
        echo "Install Homebrew, then rerun this script." >&2
        exit 2
    fi
    echo "PERKY CF toolchain: installing Homebrew m68k-elf-binutils + m68k-elf-gcc"
    brew install m68k-elf-binutils m68k-elf-gcc
fi

missing=''
for tool in $need_tools; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        missing="$missing $tool"
    fi
done
if [ -n "$missing" ]; then
    echo "PERKY CF toolchain: install completed but commands are still missing:$missing" >&2
    exit 3
fi

tmp=${TMPDIR:-/tmp}/perky-cf-toolchain-$$
trap 'rm -f "$tmp.c" "$tmp.s"' EXIT HUP INT TERM
cat > "$tmp.c" <<'EOF'
int perky_cf_toolchain_probe(unsigned a, unsigned b) { return (int)(a * b); }
EOF
m68k-elf-gcc -mcpu=54455 -msoft-float -O2 -ffreestanding -fno-builtin \
    -S "$tmp.c" -o "$tmp.s"
m68k-elf-as -mcpu=54455 "$tmp.s" -o /dev/null

version=$(m68k-elf-gcc -dumpfullversion)
echo "PERKY CF toolchain: PASS (m68k-elf-gcc $version; MCF54455 soft-float compile+assemble)"
