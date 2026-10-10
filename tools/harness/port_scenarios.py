"""Can this host run the port's `--scenario` isolation mode?

That mode forks one child per scenario so every child starts from the same
loaded machine -- the process image is the snapshot -- and the parent returns
the worst exit status (`tools/emu/ot_emu/main.cpp`, "scenarios: the loaded
machine, forked"). Windows has no `fork`: `win_compat/sys/wait.h` stubs it to
-1, so the port prints `scenario   : fork failed for K` per scenario and exits
127 (measured 10 Oct 2026, `verify_kits` with a project on the merged tree).

A gate that needs the mode SKIPs on such a host rather than reporting a port
capability the platform does not have; POSIX hosts are unaffected, and the
fork path there is untouched.

The test is the port binary, not the python: `os.name` is "posix" under
MSYS/Cygwin, and a PE child cannot be forked out of that fd table either.
"""
import pathlib


def fork_capable(emu):
    """False when `emu` is a native-Windows PE, where fork() does not exist."""
    try:
        return pathlib.Path(emu).read_bytes()[:2] != b"MZ"
    except OSError:
        return True                 # not built: the gate's own [SKIP] covers it


def skip_line(gate, emu):
    return (f"  [SKIP] {gate}: the port ({emu}) is a native-Windows binary, and this gate "
            f"needs `ot_emu --scenario`, which forks one child per scenario. The Windows "
            f"shim stubs fork() to -1 (win_compat/sys/wait.h), so the port reports "
            f"\"fork failed\" per scenario and exits 127. Run this gate on macOS or Linux.")
