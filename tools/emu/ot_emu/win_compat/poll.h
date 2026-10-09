/* Windows shim for <poll.h>. winsock2.h already defines struct pollfd and the
 * POLL* bits at _WIN32_WINNT >= 0x0600, but not a poll() call. ot_emu polls
 * stdin (POSIX fd 0) to see whether a command line is waiting and to pace its
 * run; there is no stdin command channel on a gated batch run, so poll() sleeps
 * for the requested timeout and reports nothing ready. The slice pacing is
 * preserved and the deterministic image run never depends on a command. */
#ifndef OCTABAM_WIN_POLL_H
#define OCTABAM_WIN_POLL_H

#include <winsock2.h>
#include <windows.h>

static __inline int poll(struct pollfd* _fds, unsigned long _nfds, int _timeout)
{
    (void)_fds; (void)_nfds;
    if (_timeout > 0)
        Sleep(static_cast<DWORD>(_timeout));
    return 0;
}

#endif /* OCTABAM_WIN_POLL_H */
