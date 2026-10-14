# `stations-fx2` — SPECTRUM, CHARACTER and MODULATION on both menus

The fixture of `tools/verify/verify_stations_fx2.py`. The three stations with
their `SLOTS` build setting pinned to `FX1+FX2` (`tools/remix/stations.py`),
beside the stock DELAY; every other stock effect gives up its words. No bus:
fallback NONE, no SEND (CHARACTER only reads the bus scratch, and the build
turns its KEY = T1 into SELF when the remix has no bus server).

The gate renders each station at the FX1 position and at the FX2 position
under `dsp_host` with the same input and knobs (defaults, the module's
extremes, every MODE value) and requires the two renders to be bit-identical
and not the dry input. It is port-free: `dsp_host` places the FX2 slot by its
own model of the dispatcher, so the real allocator's bases are not shown.

Not on a unit.
