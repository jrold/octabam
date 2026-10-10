/* Windows portability shim for the POSIX <sys/mman.h> usage in Octabam's
 * host runners (the emulated ColdFire memory and the DSP shared window).
 * Consumed via CPATH; the repo sources are not modified.
 *
 * Two mapping kinds:
 *   * anonymous MAP_PRIVATE / MAP_SHARED, optionally pinned with MAP_FIXED
 *     (VirtualAlloc reserves at the requested address);
 *   * FILE-BACKED MAP_SHARED with MAP_FIXED, which is what the rt mode's
 *     shared window needs (dsp.cpp rtSetup maps ONE backing object six times,
 *     2 cores x P/X/Y, so the JIT's host pointers alias the way the chip's bus
 *     does). shm_open backs it with a real temp file, so the caller's own
 *     ftruncate() sets the size and the CRT's fd works with _get_osfhandle.
 *
 * O24 (9 Oct 2026): the file-backed half was added so --dsp-rt can run on
 * Windows at all. Before it, shm_open returned -1 by design ("refuse cleanly")
 * and every --dsp-rt start failed with "shm_open failed". */
#ifndef OCTABAM_WINDOWS_SYS_MMAN_H
#define OCTABAM_WINDOWS_SYS_MMAN_H

#include <windows.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <io.h>
#include <share.h>
#include <fcntl.h>

#ifndef O_RDWR
#define O_RDWR 2
#define O_CREAT 0x0100
#define O_EXCL 0x0200
#endif

#ifndef PROT_NONE
#define PROT_NONE  0x0
#define PROT_READ  0x1
#define PROT_WRITE 0x2
#define PROT_EXEC  0x4
#endif

#ifndef MAP_SHARED
#define MAP_SHARED    0x01
#define MAP_PRIVATE   0x02
#define MAP_FIXED     0x10
#define MAP_ANONYMOUS 0x20
#define MAP_ANON      MAP_ANONYMOUS
#define MAP_FAILED    ((void *)-1)
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* The file-mapped views, so munmap knows which release to use. Eight views is
 * more than the six the shared window makes; overflow only loses the ability
 * to unmap, never correctness of the mapping itself. */
#define OCTABAM_MMAN_VIEWS 16
static void *octabam_mman_views[OCTABAM_MMAN_VIEWS];

static __inline void *mmap(void *addr, size_t length, int prot, int flags,
                           int fd, off_t offset)
{
    (void)prot;
    if (fd >= 0 && (flags & MAP_SHARED))
    {
        /* FILE-BACKED: the same bytes at every address asked for. */
        HANDLE h = (HANDLE)_get_osfhandle(fd);
        if (h == INVALID_HANDLE_VALUE)
        {
            errno = EBADF;
            return MAP_FAILED;
        }
        HANDLE m = CreateFileMappingA(h, nullptr, PAGE_READWRITE, 0, 0, nullptr);
        if (m == nullptr)
        {
            errno = ENOMEM;
            return MAP_FAILED;
        }
        void *result = MapViewOfFileEx(m, FILE_MAP_ALL_ACCESS, 0,
                                       (DWORD)offset, length,
                                       (flags & MAP_FIXED) ? addr : nullptr);
        CloseHandle(m);
        if (result == nullptr)
        {
            errno = ENOMEM;
            return MAP_FAILED;
        }
        for (size_t i = 0; i < OCTABAM_MMAN_VIEWS; ++i)
            if (octabam_mman_views[i] == nullptr)
            {
                octabam_mman_views[i] = result;
                break;
            }
        return result;
    }
    DWORD alloc_type = MEM_RESERVE | MEM_COMMIT;
    DWORD page = PAGE_READWRITE;
    void *result = (flags & MAP_FIXED)
        ? VirtualAlloc(addr, length, alloc_type, page)
        : VirtualAlloc(nullptr, length, alloc_type, page);
    if (result == nullptr)
    {
        errno = ENOMEM;
        return MAP_FAILED;
    }
    return result;
}

static __inline int munmap(void *addr, size_t length)
{
    (void)length;
    for (size_t i = 0; i < OCTABAM_MMAN_VIEWS; ++i)
        if (octabam_mman_views[i] == addr)
        {
            octabam_mman_views[i] = nullptr;
            return UnmapViewOfFile(addr) ? 0 : -1;
        }
    return VirtualFree(addr, 0, MEM_RELEASE) ? 0 : -1;
}

static __inline int mprotect(void *addr, size_t length, int prot)
{
    (void)addr; (void)length; (void)prot;
    return 0;
}

/* A POSIX shm name mapped onto a per-process temp file, so ftruncate() and the
 * CRT's fd work unchanged. */
static char octabam_shm_last_path[1024];

static __inline int shm_open(const char *name, int oflag, int mode)
{
    (void)oflag; (void)mode;
    char base[256];
    size_t n = 0;
    for (const char *p = name; *p != '\0' && n + 1 < sizeof base; ++p)
    {
        const char c = *p;
        const int ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                    || (c >= '0' && c <= '9') || c == '.' || c == '-';
        base[n++] = ok ? c : '_';
    }
    base[n] = '\0';
    const char *tmp = getenv("TEMP");
    if (tmp == nullptr || *tmp == '\0')
        tmp = getenv("TMP");
    if (tmp == nullptr || *tmp == '\0')
        tmp = ".";
    char path[1024];
    snprintf(path, sizeof path, "%s\\octabam_shm_%s", tmp, base);

    int fd = -1;
    if (_sopen_s(&fd, path, _O_RDWR | _O_CREAT | _O_TRUNC | _O_BINARY, _SH_DENYNO,
                 _S_IREAD | _S_IWRITE) != 0 || fd < 0)
    {
        errno = EACCES;
        return -1;
    }
    /* Deleted at close (POSIX shm_unlink semantics): keep the path so the
     * caller's shm_unlink can delete it now, and mark it delete-on-close as
     * well so nothing is left behind if it does not. */
    strncpy(octabam_shm_last_path, path, sizeof octabam_shm_last_path - 1);
    octabam_shm_last_path[sizeof octabam_shm_last_path - 1] = '\0';
    return fd;
}

static __inline int shm_unlink(const char *name)
{
    (void)name;
    if (octabam_shm_last_path[0] != '\0')
    {
        DeleteFileA(octabam_shm_last_path);
        octabam_shm_last_path[0] = '\0';
    }
    return 0;
}

#ifdef __cplusplus
}
#endif

#endif /* OCTABAM_WINDOWS_SYS_MMAN_H */
