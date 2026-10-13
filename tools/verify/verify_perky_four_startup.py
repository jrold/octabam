#!/usr/bin/env python3
"""Run unchanged startup differentials on the actual PERKY4 placement."""
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/perky')]
import verify_perky_fragment_clear as memory
import verify_perky_clear_registers as registers

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'out/perky/four')
    asm=p.parse_args().build/'multi.asm'
    assert asm.is_file()
    memory.shipping_payload=registers.shipping_payload=lambda:asm
    memory.main()
    registers.main()

if __name__=='__main__':main()
