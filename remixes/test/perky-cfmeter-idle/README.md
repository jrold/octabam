# `perky-cfmeter-idle` — Perky Machines with frame-cost and idle telemetry

> **ARCHIVED EXPERIMENT — NOT THE CURRENT PERKY FIRMWARE.** This README
> documents the original **earlier DSP canary or hardware audition**, including historical results and
> instructions for *that specific image*. The working MKII release is
> **PERKY4S** (T1/T5, Fold1/Fold2/Simple/Complex on DSP, 12 retained FX).
> Read the [current PERKY status](../../../modules/perky/README.md) before building or flashing.
> Do **not** treat older "flash next" instructions here as current guidance.

`perky-cfmeter` plus `CF METER IDLE`, so a single flash reports both the
ColdFire frame interrupt's cost and how much time main's idle loop gets.
Both readings are printed as audio on T8, which is the pair needed to price
a Perky workload against the UI/AED service latency it leaves behind.

Diagnostic only: FILTER and DARK REV are given up to the probe and are back
in `perky-cf-final`.
