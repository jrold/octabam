#!/usr/bin/env python3
from pathlib import Path
import build_perky_noise_hat_observer as base
ROOT=Path(__file__).resolve().parents[2]
if __name__=='__main__':base.build(ROOT/'out/perky/hybrid/noise-hat-async/observer',exact_header=ROOT/'tools/harness/perky_cf/noise_hat_async_observer.h')
