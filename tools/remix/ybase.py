"""The shared-window base literal in module source.

`build_bus.py` rewrites the base literal to each payload's half of the shared
window. The match is the literal followed by a character that is not a hex
digit, so a longer immediate that begins with the same digits is left alone.
"""
import re

LITERAL = "$" + format(0x30000, "x")
_RE = re.compile(re.escape(LITERAL) + r"(?![0-9A-Fa-f])")

# Occurrences in each source the substitution touches, by module key. Counted
# on the source as the build holds it (after XBUS scratch moves, before the
# substitution). DELAY SERVER varies with the layout and is checked by the
# caller against its own expected count.
EXPECTED = {
    "SEND": 1,
    "REVERB SERVER": 5,
}


def count(src):
    return len(_RE.findall(src))


def substitute(src, base):
    """Rewrite each whole-token occurrence of the literal to `base` (an int)."""
    return _RE.sub(lambda m: f"${base:x}", src)


def check(key, src, want=None):
    """Return an error string when `src` holds a different count than expected."""
    want = EXPECTED.get(key) if want is None else want
    if want is None:
        return f"{key}: no expected base-literal count in tools/remix/ybase.py"
    found = count(src)
    if found != want:
        return (f"{key}: {found} base-literal occurrence(s), expected {want} "
                f"(tools/remix/ybase.py EXPECTED)")
    return None
