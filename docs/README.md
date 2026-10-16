# Documentation

Where each doc is, by who reads it. A module's own page is
`modules/<name>/README.md`, a remix's `remixes/<name>/README.md`, a tool's
`tools/<dir>/README.md`.

**Current PERKY firmware:** [PERKY4S status and source entry point](../modules/perky/README.md)
and [PERKY4S release evidence](../modules/perky/PERKY4S_RELEASE.md).
Earlier PERKY3R/PERKY4 and ColdFire research docs below describe historical
checkpoints, not the current MKII firmware or free DSP memory.

## Building and flashing a remix

| doc | what it is |
|---|---|
| [site/index.md](site/index.md) | the manual site (MkDocs, deployed to GitHub Pages on merges to main): choosing a remix, BRAIN, build and flash, safety — written for musicians |
| [guide/BUILDING.md](guide/BUILDING.md) | what to install (macOS, Linux/WSL2), the toolchain, your own OS 1.40C, building an image, flashing from the card or over MIDI, after the flash, recovery, back to stock |
| [../remixes/README.md](../remixes/README.md) | the remixes you can flash, with where each has run |
| [guide/REMIXER.md](guide/REMIXER.md) | composing your own remix: the `make remix` TUI, or a `remix.py` by hand |
| [../modules/perky/PERKY3R_AUDIT.md](../modules/perky/PERKY3R_AUDIT.md) | PERKY2F hardware-regression investigation, three-engine repair candidate, local evidence and short T1/T5 hardware checklist |

| [../modules/perky/PERKY4_RELEASE.md](../modules/perky/PERKY4_RELEASE.md) | Four-algorithm local candidate, provenance workflow and MKII checklist |
| [../modules/perky/PERKY4R_AU_REPAIR.md](../modules/perky/PERKY4R_AU_REPAIR.md) | Direct installed-AU capture, three demonstrated Complex control defects, repair gates and hardware comparison |
| [../modules/perky/PERKY4R_RUNTIME_REGRESSION.md](../modules/perky/PERKY4R_RUNTIME_REGRESSION.md) | PERKY4R trigger stall, guarded placement, hardware results and controlled builds |
| [../modules/perky/PERKY4S_RELEASE.md](../modules/perky/PERKY4S_RELEASE.md) | Current working MKII DSP release; guarded P placement, final P ledger, qualification and physical test scope |
| [../modules/perky/PERKY4_MEMORY.md](../modules/perky/PERKY4_MEMORY.md) | Historical PERKY4 DSP ledger and timing; **not** the PERKY4S occupancy (see PERKY4S_RELEASE.md) |
| [../modules/perky/hybrid/CLOSEOUT.md](../modules/perky/hybrid/CLOSEOUT.md) | Final Goal 2 engineering assessment: closed unqualified; exact gate matrix, timing scope, hardware risks and probe decision |
| [../modules/perky/hybrid/SAFETY_QUALIFICATION.md](../modules/perky/hybrid/SAFETY_QUALIFICATION.md) | Historical IPL3-only safety qualification: timing, cold-init, identities and then-open stack blocker; successor below |
| [../modules/perky/hybrid/PRIVATE_STACK_QUALIFICATION.md](../modules/perky/hybrid/PRIVATE_STACK_QUALIFICATION.md) | Original private-stack qualification and packages; later MKII observations and optimization evidence below |
| [../modules/perky/hybrid/CF_OPTIMIZATION_HARDWARE.json](../modules/perky/hybrid/CF_OPTIMIZATION_HARDWARE.json) | Eight real MKII PRFs: exact layout, cumulative intervals, timing and limits |
| [../modules/perky/hybrid/CF_OPTIMIZATION.json](../modules/perky/hybrid/CF_OPTIMIZATION.json) | ColdFire optimization experiments, preserved checkpoints, exact tests and final qualification status |
| [../modules/perky/hybrid/CF_OPTIMIZATION_QUALIFICATION.json](../modules/perky/hybrid/CF_OPTIMIZATION_QUALIFICATION.json) | PKH3O3 final local qualification, artifact hashes, completed sustained tests and hardware limits |
| [../modules/perky/hybrid/CF_OPTIMIZATION_20261016.txt](../modules/perky/hybrid/CF_OPTIMIZATION_20261016.txt) | PKH4O2 target improvements, complete paired/sustained/continuous local qualification, diagnostic artifact identities and physical A/B limits |
| [../modules/perky/hybrid/CF_OPTIMIZATION_20261016.json](../modules/perky/hybrid/CF_OPTIMIZATION_20261016.json) | Machine-readable accepted/rejected experiments, provenance, exactness and qualification receipts |
| [../modules/perky/hybrid/CF_OPTIMIZATION_20261016_QUALIFICATION.json](../modules/perky/hybrid/CF_OPTIMIZATION_20261016_QUALIFICATION.json) | Final requirement-by-requirement local diagnostic verdict, source/artifact identities and remaining hardware uncertainties |
| [../modules/perky/hybrid/CF_OPTIMIZATION_20261016_STACK_CONTRACTS.json](../modules/perky/hybrid/CF_OPTIMIZATION_20261016_STACK_CONTRACTS.json) | Image-pinned reviewed runtime spill callees for PKH4O2's static private-stack analysis |
| [../modules/perky/hybrid/STACK_CORRECTION.md](../modules/perky/hybrid/STACK_CORRECTION.md) | Bounded stack correction: verified task/driver ownership and DRAM; historical private audio-stack architecture/cost proposal, subsequently approved |
| [../modules/perky/hybrid/PHASE2.md](../modules/perky/hybrid/PHASE2.md) | Hybrid Goal 2 implementation/measurement history; final status in CLOSEOUT.md, **not qualified** |
| [../modules/perky/hybrid/ITERATION3.md](../modules/perky/hybrid/ITERATION3.md) | Additional authorized CF empty-render experiment: exact but rejected for worse peak timing; prior runtime restored |
| [../modules/perky/hybrid/HW_PROBE_REQUEST.md](../modules/perky/hybrid/HW_PROBE_REQUEST.md) | Withheld hybrid hardware request, unqualified artifact hashes and preserved rollback references |
| [../modules/perky/hybrid/GOAL2_RESUME_HANDOFF.md](../modules/perky/hybrid/GOAL2_RESUME_HANDOFF.md) | Resume audit, preserved dirty work, executed commands and timing-review stopping gate |
| [../modules/perky/PICKUP_FEASIBILITY.md](../modules/perky/PICKUP_FEASIBILITY.md) | Conditional ColdFire census only; Pickup and shared recorders preserved |

## Writing a module or changing the build

| doc | what it is |
|---|---|
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | the contract: the one rule, your first PR, the oracle rule, the gates before a PR |
| [contributing/MODULES.md](contributing/MODULES.md) | writing a module: manifests, descriptors, DSP and ColdFire declarations, the ledger |
| [contributing/PLACEMENT.md](contributing/PLACEMENT.md) | where a module's code goes and what is free, measured |
| [contributing/TESTING.md](contributing/TESTING.md) | every gate, what it proves and cannot see; `make check`, `make reach`, shards, `make accept`, bit-identity, CI |
| [contributing/TOOLING.md](contributing/TOOLING.md) | every tool by pipeline stage, and which README each tool directory has |
| [contributing/FAILURE_MODES.md](contributing/FAILURE_MODES.md) | what has gone wrong on a unit: symptom, cause, fix, the gate that catches it |
| [contributing/TRAPS.md](contributing/TRAPS.md) | the trap register: what has cost real work in the code, build, emulators and harness — symptom, fix, the gate that catches it |
| [../AGENTS.md](../AGENTS.md) | working rules, worktrees, build and check, and the trap index (for people and coding agents) |

## The tools

| doc | what it is |
|---|---|
| [../tools/remix/README.md](../tools/remix/README.md) | the remix engine: schema, registry, ledger, the DRAM platform, the remixer's internals |
| [../tools/harness/README.md](../tools/harness/README.md) | hearing and measuring the DSP side locally: `dsp_host`, `send_probe`, `rig_render`, `pressure`, the stress project |
| [../tools/emu/README.md](../tools/emu/README.md) | the ColdFire emulators: the port (`ot_emu`) and Tier-0 (Unicorn) |
| [../tools/panel/README.md](../tools/panel/README.md) | the virtual front panel over the port; [KEYMAP.md](../tools/panel/KEYMAP.md) the key and LED map |
| [../tools/ghidra/README.md](../tools/ghidra/README.md) | the Ghidra project over the OS and both DSP payloads |

## The firmware, reverse-engineered

[firmware/](firmware/): OS 1.40C as measured here. Start at
[ARCHITECTURE.md](firmware/ARCHITECTURE.md); [CHIP.md](firmware/CHIP.md)
is the silicon and the cycle budget, [DSP.md](firmware/DSP.md) the audio
DSP, and the rest one subsystem each (kernel, tables, parameter pages,
menus, panel, MIDI, LFO, level law, recorder, sample save, storage,
the MIDI tracks' setup record, writers, outgoing MIDI and CTRL labels in [MIDI_TRACKS.md](firmware/MIDI_TRACKS.md), Parts and pattern changes in [PARTS.md](firmware/PARTS.md), step locks, the ColdFire delay routine in [COLDFIRE_DELAY.md](firmware/COLDFIRE_DELAY.md),
REPITCH in [REPITCH.md](firmware/REPITCH.md)).

## Proposals

[proposals/](proposals/): [BRAIN.md](proposals/BRAIN.md), the design for
settings, defaults and templates (6 Oct 2026; `modules/brain` builds it and
measures it under the port, not on a unit), and the two
OTX documents it starts from, nordseele's shared settings store (draft, not
implemented): [OTX_PROJECT_PROPOSAL.md](proposals/OTX_PROJECT_PROPOSAL.md)
and [OTX_MODULE_GUIDELINES.md](proposals/OTX_MODULE_GUIDELINES.md).

[proposals/remixes/](proposals/remixes/README.md): remix proposals, each
taken on hardware to verified stable before it lands under `remixes/`.

## History

[../CHANGELOG.md](../CHANGELOG.md) has one entry per image that reached a
unit. Records that were closed and removed are cited in place as
`git show <sha>:<path>`.
