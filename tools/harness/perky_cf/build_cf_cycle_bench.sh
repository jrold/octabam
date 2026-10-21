#!/bin/sh
# Build cf_cycle_bench into out/perky/hybrid/cf-cycle-bench/ against the same
# patched Musashi library the frozen observer links (out/emu/mc68k/lib68kEmu.a)
# and an unmodified copy of ot_emu's v4e.cpp, whose "machine.h" include must
# resolve to the shim beside it.
set -e
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$ROOT/out/perky/hybrid/cf-cycle-bench
mkdir -p "$OUT/build"
cp "$ROOT/tools/emu/ot_emu/v4e.cpp" "$ROOT/tools/emu/ot_emu/v4e.h" "$OUT/build/"
cp "$ROOT/tools/harness/perky_cf/cf_cycle_bench_shim/machine.h" "$OUT/build/"
c++ -O2 -std=gnu++17 -arch arm64 -I "$OUT/build" -I "$ROOT/vendor" -I "$ROOT/vendor/mc68k" \
    -I "$ROOT/vendor/mc68k/Musashi" "$ROOT/tools/harness/perky_cf/cf_cycle_bench.cpp" \
    "$OUT/build/v4e.cpp" "$ROOT/out/emu/mc68k/lib68kEmu.a" -o "$OUT/cf_cycle_bench"
echo "$OUT/cf_cycle_bench"
