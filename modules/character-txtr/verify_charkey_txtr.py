#!/usr/bin/env python3
"""CHARACTER TXTR's gate: tools/verify/verify_charkey.py on this module (a Gate
takes no arguments, so the module names itself here)."""
import pathlib, runpy, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.argv = [str(ROOT / "tools/verify/verify_charkey.py"), "character-txtr"]
runpy.run_path(sys.argv[0], run_name="__main__")
