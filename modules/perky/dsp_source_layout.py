"""Perky candidate source layout helpers; no binary or firmware data.

Center a 128-word scratch ABI on r5 so every X displacement is in -64..63.
The logical scratch layout is unchanged. The candidate advances r5 by 64;
its caller must supply the ABI base again on the next invocation. Derived
variable storage at ABI+128 remains outside this scratch span, based on r4.
"""
import re


def center_scratch(text, entry, *, variables=False, delay=False):
    label = entry + ':'
    assert text.count(label) == 1
    if variables:
        old = 'move r5,a\n        add #>$80,a\n        move a1,r4'
        assert text.count(old) == 1
        text = text.replace(old, 'move r5,a\n        add #>$40,a\n        move a1,r4')
    if delay:
        old = 'move    r5,a\n        add     #>$40,a\n        move    a1,r7'
        assert text.count(old) == 1
        text = text.replace(old, 'move    r5,r7')
    def address(match):
        displacement = int(match[1], 16) - 64
        assert -64 <= displacement <= 63, match[0]
        return f'x:(r5{"+" if displacement >= 0 else "-"}${abs(displacement):x})'
    text = re.sub(r'x:\(r5\+\$([0-9a-f]+)\)', address, text)
    return text.replace(label, label + '\n        move r5,a\n        add #>$40,a\n        move a1,r5', 1)
