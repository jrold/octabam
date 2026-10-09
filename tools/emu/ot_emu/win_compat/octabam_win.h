/* Native-Windows compatibility shim for Octabam's ot_emu host.
 *
 * Force-included into the ot_machine/ot_emu translation units (see the WIN32
 * block in tools/emu/ot_emu/CMakeLists.txt). It supplies the small set of POSIX
 * names MinGW lacks and that ot_emu uses on its lockstep path. It is NOT applied
 * to the vendored mc68k/dsp56300 cores, which already build on Windows. */
#ifndef OCTABAM_WIN_COMPAT_H
#define OCTABAM_WIN_COMPAT_H

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

/* winsock2.h must precede windows.h, and _WINSOCKAPI_ keeps windows.h from
 * pulling the conflicting winsock.h. */
#include <winsock2.h>
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <process.h>
#include <time.h>
#ifdef __cplusplus
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#else
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#endif

#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif
#ifndef O_NONBLOCK
#define O_NONBLOCK 0
#endif
#ifndef F_GETFL
#define F_GETFL 0
#define F_SETFL 1
#endif

/* POSIX durability/flush + positional write used by card.cpp. */
static __inline int fsync(int _fd) { return _commit(_fd); }
static __inline long long pwrite(int _fd, const void* _buf, size_t _n, long long _off)
{
    if (_lseeki64(_fd, _off, SEEK_SET) < 0)
        return -1;
    return (long long)(_write(_fd, _buf, (unsigned)(_n)));
}
static __inline int ftruncate(int _fd, long long _len)
{
    return _chsize_s(_fd, _len) == 0 ? 0 : -1;
}

/* usb.cpp sets F_GETFL/F_SETFL/O_NONBLOCK on its (unused in a gated build)
 * listening socket; MinGW has no fcntl. */
static __inline int fcntl(int _fd, int _cmd, ...) { (void)_fd; (void)_cmd; return 0; }

/* Reentrant time conversions used by periph.cpp's DS1390 RTC. */
static __inline struct tm* gmtime_r(const time_t* _t, struct tm* _out)
{
    return gmtime_s(_out, _t) == 0 ? _out : 0;
}
static __inline struct tm* localtime_r(const time_t* _t, struct tm* _out)
{
    return localtime_s(_out, _t) == 0 ? _out : 0;
}

#endif /* _WIN32 */
#endif /* OCTABAM_WIN_COMPAT_H */
