#!/usr/bin/env python3
"""Reclassify stock PCs with the already-proven unchanged cost observer.

Only the observer's external address-to-name map changes. This diagnostic uses
the full existing control row and retains every exact audio/state/cycle check.
"""
import json
from pathlib import Path

import profile_perky_remaining_cf_cost as previous

ROOT=previous.ROOT
WORK=ROOT/'out/perky/hybrid/stock-isr-next-profile-v1'


def prepare(work,candidate):
    previous.prepare_reused(work,candidate)
    symbols=work/'symbols.txt'
    runtime=symbols.read_text()
    # A fixed256-byte block is an address bucket, not a guessed function.
    stock=''.join(f'{address:x} {address+256:x} stock_{address:08x}\n'
                  for address in range(0x40000400,0x40c00000,256))
    symbols.write_text(stock+runtime)
    receipt=work/'PROFILE_OBSERVER.json'
    value=json.loads(receipt.read_text())
    value['status']='REUSED_PROVEN_OBSERVER_WITH_STOCK_ADDRESS_BUCKETS'
    value['symbols_sha256']=previous.calibration.sha(symbols)
    value['source_sha256'][str(Path(__file__).resolve())]=previous.calibration.sha(Path(__file__).resolve())
    value['stock_bucket_bytes']=256
    value['scope']='Only external bucket names/ranges change; unchanged observer binary and exact paired control-row checks retained.'
    previous.calibration.save(receipt,value)


def main():
    source=previous.adapted_main()
    namespace=dict(vars(previous.profile))
    namespace.update(__file__=str(Path(__file__).resolve()),_profile_module=previous.profile,
                     remaining=previous.remaining,DEFAULT_BUILD=previous.BUILD,
                     DEFAULT_WORK=WORK,prepare=prepare)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),namespace)
    namespace['main']()


if __name__=='__main__':main()
