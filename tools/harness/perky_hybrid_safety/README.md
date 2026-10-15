# Bounded hybrid safety observer

These tools inspect the existing hybrid; they do not build or qualify firmware.
Read `modules/perky/hybrid/SAFETY_QUALIFICATION.md` for the verdict and limits.

The observer stages two emulator translation units under the selected `--work`
directory and links their replacement objects before the existing libraries.
The shared `out/emu/ot_emu`, its libraries and firmware stay unchanged. Staging
requires the existing macOS arm64 CMake build and local compiler. Source markers
must match exactly. The staged header and all linked inputs are hash-recorded.

Use the existing `safety-final/fixture/card.img` when present. To reproduce that
private generated fixture from the existing baseline project:

```sh
.venv/bin/python3 - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, 'tools/verify')
import verify_perky_hybrid_workload as w
base = json.loads(Path('modules/perky/hybrid/BASELINE.json').read_text())
work = Path('out/perky/hybrid/safety-final').resolve()
w.stage_integrated_fixture(Path(base['project']['root']), work/'fixture',
    'snare', 'snare', tone_path=work/'tone.wav',
    allow_family_transitions=True, first_trig_delay=0)
PY
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety.py --work out/perky/hybrid/safety-final/final-observer
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety.py --work out/perky/hybrid/safety-final/final-observer --panel
.venv/bin/python3 tools/verify/verify_perky_hybrid_lifecycle_safety.py
.venv/bin/python3 tools/verify/verify_perky_hybrid_saved_project.py
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_assessment.py --selftest
```

The working-bank invocation is recorded verbatim in the assessment's
`positive_evidence.working_bank.command`; run it with stdout redirected to
`safety-final/banks/port.log` before consolidation. It exercises the stock sys
working-bank message; it does not claim a full playing-bank transition.

The assessment entry point verifies input/output/source hashes and refuses
missing software obligations with exit 1. An observed stack maximum is never
accepted as a ceiling. `--reuse-save` reanalyzes an already hash-verified SAVE
and executes a new cold reload; it does not skip the reload.

The instruction observer reads RAM/registers and records host state. It never
writes target canaries or advances target time. Calibration alone writes its
own synthetic test machine: four entry/step variants test real nested IRQ/RTE
behavior, plus deliberate stack/guard/DMA failures and non-overlap controls.

Known limits: vector mappings refresh at scheduler/main-spin boundaries; only
the leading LEA and immediate SR-write entries used here are decoded; nested
scheduler/task-switch behavior is not a general exception unwinder. Source-DMA
extents follow the existing model's contiguous host-port snapshot behavior,
not every physical eDMA stride/modulo/cache mode. Stack bottom watches start
on first task execution and do not establish untouched-stack capacity. UI queue
peaks are observations, not lost-event or saturation guarantees. The current
assessment intentionally remains BLOCKED.
