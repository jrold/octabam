#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)

"$HERE/bootstrap_cf_toolchain.sh"
exec python3 "$HERE/build_cf_final.py" "$@"
