# Bounded hybrid safety observer

These tools inspect the existing hybrid; they do not authorize installation.
The authorized IPL3 operand guard has scoped local passes. Real chooser/Part/
playing-bank and dense delivery/lock/UI/DMA checks now pass their bounded cases.
The combined all-path stock-task/ISR stack bound remains **UNVERIFIED**, and
the current assessment is **BLOCKED**. No firmware defect is invented from it.
Read `modules/perky/hybrid/SAFETY_QUALIFICATION.md` for the verdict and limits.

Current entry points, using the retained private artifacts:

```sh
.venv/bin/python3 tools/perky/apply_hybrid_ipl_guard.py out/perky/hybrid/probe/mainos_PKHYB2P.bin out/perky/hybrid/ipl3/trial-mainos.bin
.venv/bin/python3 tools/verify/verify_perky_hybrid_ipl_guard.py --selftest
.venv/bin/python3 tools/verify/verify_perky_hybrid_ipl_guard.py --unit
.venv/bin/python3 tools/verify/verify_perky_hybrid_ipl_guard.py
```

The final command reuses recorded runs and intentionally exits1 for the missing
stack ceiling after its scoped assertions pass. `--unit` executes the actual
handler and original-image negative controls; it does not repeat the workload
matrix. `--revert` on the patch tool restores the exact old hash into a separate
output. Original inputs are never overwritten. The module factory's additional
poke is compared with the previous factory and reproduces the exact trial.

`guard_audit.h` augments a staged copy of the existing observer: actual source
tuples, CF delivered-trigger counters and sys queue posts/returns. CF preparation
is inlined in the renderer, so its exported wrapper PC is not used as an event
oracle. `dense_fixture.py NEW_OUTPUT_DIR` regenerates the 300 BPM fixture from the
existing private safety card and was checked byte-identical to the used card.
`verify_perky_hybrid_guard_lifecycle.py` drives the real chooser/Part/bank path;
`bank_panel.py` is the separately accepted bank-only panel trace. It selects the
pattern trig directly from BANK B: SELECT PTN, without reopening PATTERN, and
waits at most four seconds for queued changes.

Recorded runs and hashes are in `out/perky/hybrid/ipl3/IPL3_QUALIFICATION.json`.
Sources, compiler/link commands and all accepted inputs stay in this checkout;
no proprietary image/project bytes belong in Git. The current verdict does not
qualify a fresh rebuild or any flash wrapper.

Historical pre-authorization stack check (original unguarded image):

```sh
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_stop.py --selftest
.venv/bin/python3 tools/verify/verify_perky_hybrid_safety_stop.py
```

The C++ test process must exit 0. The assessment exits 1 deliberately for the
structural safety stop. It checks existing receipt hashes, boots the unchanged
image, reaches the real keyrepeat task, and forces nine sequencer arrivals through
the modeled controller. It stops before a tenth would overflow. Arrivals are
adversarial, not a natural-playback overflow reproduction. A second disposable
machine changes the existing IPL operand to 3 and checks local request deferral;
the input image is never changed. That counterfactual is not an approved or
fully qualified firmware fix. No long workload or lifecycle rerun is performed.
`FINAL_SAFETY_STOP.json` records commands, inputs, linked libraries and outputs.

The older consolidation tool now labels missing evidence UNVERIFIED rather than
calling it a demonstrated defect. Historical receipt bytes retain their old label
and are explicitly superseded by the final report.

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
assessment does not establish a software safety pass.
