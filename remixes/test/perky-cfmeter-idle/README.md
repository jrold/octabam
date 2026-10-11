# `perky-cfmeter-idle` — Perky Machines with frame-cost and idle telemetry

`perky-cfmeter` plus `CF METER IDLE`, so a single flash reports both the
ColdFire frame interrupt's cost and how much time main's idle loop gets.
Both readings are printed as audio on T8, which is the pair needed to price
a Perky workload against the UI/AED service latency it leaves behind.

Diagnostic only: FILTER and DARK REV are given up to the probe and are back
in `perky-cf-final`.
