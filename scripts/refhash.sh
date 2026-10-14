#!/usr/bin/env bash
#
# refhash.sh -- bit-identity baseline for the remix refactor.
#
# LOCAL DISCIPLINE, NOT CI. Every hash here depends on the operator's own copy
# of the stock OS (out/raw/section_3_MAIN_OS.bin), so the baseline is untracked
# and only means anything on the machine that saved it.
#
#   scripts/refhash.sh check    # every artifact and every build report must match
#                               # the baseline of this branch's merge-base with
#                               # origin/main (tools/verify/refhash_store.py: saved
#                               # once per merge-base, shared by every worktree)
#   scripts/refhash.sh save     # a LOCAL baseline of this tree, for
#                               # REFHASH_LOCAL=1 scripts/refhash.sh check
#
# Why this matrix: a refactor of build_bus.py breaks things that still build,
# still boot and still make sound. The cases pin the failure modes that have no
# other gate --
#
#   bus/plain        the two shipping layouts
#   render/*-delay   the DEV hatch, including the out-of-region delay record
#                    appended to the .mem dump
#   mode1            the ";_OVERRIDE" immediate-substitution path
#   noshim           the SHIMMER_BEGIN/END excision
#   marker           the MARKER splice (which requires NOSHIM -- so this case
#                    also pins the ORDER of excision vs splice)
#   burn             the BURN splice into the live engine. It DOES place
#                    (the Makefile's help text still says otherwise; what
#                    does not fit is the alias-probe combo in a plain layout)
#   delay-override   two delay overrides at once
#   hkb              the housekeeper flip
#
# Build stdout is hashed alongside the artifacts on purpose: verify_delay.py,
# verify_roll.py and verify_burn.py all parse the build report, so the report
# text is part of the build's API and a "harmless" rewording is a breaking
# change.

set -uo pipefail
cd "$(dirname "$0")/.."

CASES=(
  "bus|XBUS=1 SPEC=1"
  "plain|"
  "render|DEV=1 XBUS=1 SPEC=1"
  "render-delay|DEV=1 XBUS=1"
  "mode1|XBUS=1 SPEC=1 MODE=1"
  "noshim|XBUS=1 SPEC=1 NOSHIM=1"
  "marker|XBUS=1 NOSHIM=1 MARKER=1"
  "burn|XBUS=1 BURN=1"
  # XBUS with neither SPEC nor DEV is the one layout that renames the effects
  # to XVerb/NotUsed (and re-abbreviates them). Nothing else reaches that arm.
  "xbus-only|XBUS=1"
  "delay-override|DEV=1 XBUS=1 DMODE=2 DINT=7"
  "hkb|HKB=1 XBUS=1 SPEC=1"
  # Every remaining env-conditional effect NAME/table mutation gets a case.
  # The panel name is rewritten from six different places depending on the
  # flags, and a name is 13 bytes in a cloned descriptor -- exactly the kind
  # of thing that survives a refactor looking fine and ships the wrong string
  # to a unit whose running build you then cannot identify.
  # The three diagnostics that replace the reverb's engine. Under XBUS the
  # delay is stubbed, which leaves room for them, and they produce real
  # images -- so those cases pin the descriptor a probe build writes,
  # including the panel name that says which diagnostic is running.
  "xbus-probe|XBUS=1 PROBE=1"
  "xbus-xprobe|XBUS=1 XPROBE=1"
  "xbus-tprobe|XBUS=1 TPROBE=1"
  # The same three in a PLAIN layout, where the real delay overruns the
  # region. They pin the failure, which is a real thing to preserve: it is
  # the honest "no room" refusal, not a code defect.
  "probe|PROBE=1"
  "xprobe|XPROBE=1"
  "tprobe|TPROBE=1"
  "delayprobe-silence|XBUS=1 DELAYPROBE=silence"
  "delayprobe-send|XBUS=1 DELAYPROBE=send"
  "delayprobe-stock|XBUS=1 DELAYPROBE=stock"
  # TEMPO SYNC's CAVE setting (NOTEMPO=1 / TEMPOCAVE=replay until 11 Oct 2026)
  "notempo|XBUS=1 SPEC=1 REMIX=test/bus-notempo"
  "tempocave-replay|XBUS=1 SPEC=1 REMIX=test/bus-tempo-replay"
  "dnote|DEV=1 XBUS=1 DNOTE=84"
  "xbusbase|XBUS=1 SPEC=1 XBUS_BASE=35000"
)

# The artifacts a case leaves, their hashes and the normalised report (a
# traceback's source line numbers move with every refactor, so they are
# dropped; nothing else is touched, the report proper is compared verbatim
# because tools parse it) are tools/verify/refhash_run.py's.

run_matrix() {
  # tools/verify/refhash_run.py: the cases over REFHASH_JOBS trees (this one
  # and scratch worktrees of it); the manifest is the same one the cases run
  # one after another produced.
  local outdir="$1" jobs="${2:-1}"
  rm -rf "$outdir"; mkdir -p "$outdir"
  printf '%s\n' "${CASES[@]}" | python3 tools/verify/refhash_run.py "$outdir" --jobs "$jobs"
}

restore() {
  # Leave the shipping artifact on disk, the way `make check` does.
  REMIX=bus XBUS=1 SPEC=1 python3 tools/build/build_bus.py > /dev/null 2>&1 || true
}

case "${1:-}" in
  save)
    echo "refhash: saving baseline (${#CASES[@]} builds)"
    run_matrix out/refhash/baseline "${REFHASH_JOBS:-1}"
    echo local > out/refhash/baseline/KEY
    restore
    echo
    echo "  baseline -> out/refhash/baseline/manifest.txt"
    ;;
  check)
    # The baseline is the 24 builds of this branch's merge-base with
    # REFHASH_BASE (origin/main), saved once for every worktree
    # (tools/verify/refhash_store.py). REFHASH_LOCAL=1 compares against the
    # baseline `save` left in this tree instead.
    if [ "${REFHASH_LOCAL:-}" != "1" ]; then
      python3 tools/verify/refhash_store.py fetch || exit 2
    fi
    [ -f out/refhash/baseline/manifest.txt ] || {
      echo "refhash: no baseline -- run 'scripts/refhash.sh save' on a tree you trust"; exit 2; }
    echo "refhash: checking against baseline (${#CASES[@]} builds)"
    run_matrix out/refhash/current "${REFHASH_JOBS:-4}"
    restore
    echo
    if diff -u out/refhash/baseline/manifest.txt out/refhash/current/manifest.txt > out/refhash/manifest.diff; then
      rm -f out/refhash/manifest.diff
      echo "  ALL ${#CASES[@]} CASES BIT-IDENTICAL"
      exit 0
    fi
    echo "  MISMATCH -- the refactor is not behaviour-preserving"
    echo
    cat out/refhash/manifest.diff
    echo
    # A report-only mismatch is the common case and the manifest hash alone
    # does not say what changed, so diff the reports of the failing cases.
    for spec in "${CASES[@]}"; do
      local_name="${spec%%|*}"
      if ! cmp -s "out/refhash/baseline/$local_name.log" "out/refhash/current/$local_name.log"; then
        echo "--- report diff: $local_name ---"
        diff -u "out/refhash/baseline/$local_name.log" "out/refhash/current/$local_name.log" | head -60
      fi
    done
    exit 1
    ;;
  *)
    echo "usage: scripts/refhash.sh save|check"
    exit 2
    ;;
esac
