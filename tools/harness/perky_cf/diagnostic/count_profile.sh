#!/bin/sh
# Diagnostic entry-count profile: count_profile.sh BUILD WORK CONTROL_ROW
# Reuses the frozen cost observer's prepare step for symbols, then swaps in the
# diagnostic counting observer. Not a qualification receipt.
set -e
ROOT=/Users/jrold/Downloads/octabam
BUILD=$1; WORK=$2; ROW=$3
cd $ROOT
.venv/bin/python tools/verify/profile_perky_stock_cf_cost.py --candidate $BUILD --work $WORK --build-observer
rm $WORK/observer
ln -s $ROOT/out/perky/hybrid/diagnostic-count-observer $WORK/observer  # build_diagnostic_observer.py count out/perky/hybrid/diagnostic-count-observer
python3 - "$WORK" <<'PY'
import json,hashlib,sys
from pathlib import Path
W=Path(sys.argv[1]);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=json.loads((W/'PROFILE_OBSERVER.json').read_text())
r['observer_sha256']=sha(W/'observer/ot_emu_safety');r['status']='DIAGNOSTIC_ENTRY_COUNT_OBSERVER_NOT_A_QUALIFICATION_RECEIPT'
(W/'PROFILE_OBSERVER.json').write_text(json.dumps(r,indent=2))
PY
CF_COUNT_SYMBOLS=$ROOT/$WORK/symbols.txt CF_COUNT_REPORT=$ROOT/$WORK/count.json .venv/bin/python tools/verify/profile_perky_stock_cf_cost.py --candidate $BUILD --work $WORK --control-row $ROW
