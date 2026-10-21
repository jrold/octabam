"""Versioned full-map project signature; legacy layouts require conversion."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SIGNATURE_VERSION=2
def once(text,old,new):
 assert text.count(old)==1,old[:80]
 return text.replace(old,new,1)
def generate(work):
 out=Path(work)/'project-abi';out.mkdir(exist_ok=True)
 control=(ROOT/'modules/perky/control.c').read_text()
 control=once(control,'signature[2] == 1u','signature[2] == 2u')
 (out/'control.c').write_text(control)
 three=(ROOT/'modules/perky/control_three_candidate.c').read_text()
 three=once(three,'#include "control.c"','#include "'+str(out/'control.c')+'"')
 (out/'control_three_candidate.c').write_text(three)
 four=(ROOT/'modules/perky/control_four_candidate.c').read_text()
 four=once(four,'#include "control_three_candidate.c"','#include "'+str(out/'control_three_candidate.c')+'"')
 (out/'control_four_candidate.c').write_text(four)
 machine=(ROOT/'modules/perky/machine.s').read_text()
 machine=once(machine,'        cmpi.b  #1,%d1\n','        cmpi.b  #2,%d1\n')
 machine=once(machine,'        move.b  #1,2(%a1)\n','        move.b  #2,2(%a1)\n')
 # Only a matching complete signature is a reselect. Creating a V2 machine
 # on legacy bytes initializes its six controls instead of reinterpreting ALGO.
 machine=once(machine,"        cmpi.b  #'P',%d2\n        beq.s   .sw_mark\n", """        cmpi.b  #'P',%d2
        bne.s   .sw_new_layout
        move.b  1(%a1),%d2
        cmpi.b  #'K',%d2
        bne.s   .sw_new_layout
        move.b  2(%a1),%d2
        cmpi.b  #2,%d2
        beq.s   .sw_mark
.sw_new_layout:
""")
 (out/'machine.s').write_text(machine)
 return out
