/* Windows portability shim for the POSIX <sys/mman.h> usage in Octabam's
 * host runners (anonymous, fixed-address mappings of the emulated ColdFire
 * memory). Consumed via CPATH; the repo sources are not modified.
 *
 * Only the subset those runners use is provided: anonymous MAP_PRIVATE /
 * MAP_SHARED mappings, optionally pinned with MAP_FIXED (VirtualAlloc reserves
 * at the requested address), and munmap. No file-backed mapping is provided. */
#ifndef OCTABAM_WINDOWS_SYS_MMAN_H
#define OCTABAM_WINDOWS_SYS_MMAN_H

#include <windows.h>
#include <errno.h>
#include <stddef.h>
#include <sys/types.h>

/* ot_emu includes <sys/mman.h> in dsp.cpp (the shared window) and main.cpp
 * (the --scenario unshare). Both are outside the gated lockstep path; the
 * anonymous fixed mapping is real, and the fd-based calls are provided so the
 * code resolves. */
#ifndef _O_RDWR
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

static __inline void *mmap(void *addr, size_t length, int prot, int flags,
                           int fd, off_t offset)
{
    (void)prot; (void)fd; (void)offset;
    DWORD alloc_type = MEM_RESERVE | MEM_COMMIT;
    DWORD page = PAGE_READWRITE;
    void *result = (flags & MAP_FIXED)
        ? VirtualAlloc(addr, length, alloc_type, page)
        : VirtualAlloc(NULL, length, alloc_type, page);
    if (result == NULL)
    {
        errno = ENOMEM;
        return MAP_FAILED;
    }
    return result;
}

static __inline int munmap(void *addr, size_t length)
{
    (void)length;
    return VirtualFree(addr, 0, MEM_RELEASE) ? 0 : -1;
}

static __inline int mprotect(void *addr, size_t length, int prot)
{
    (void)addr; (void)length; (void)prot;
    return 0;
}

/* The shared window (dsp.cpp rtSetup) and the --scenario unshare (main.cpp) are
 * outside the gated lockstep path. shm_open reports failure so those paths
 * refuse cleanly instead of building a broken alias. */
static __inline int shm_open(const char *name, int oflag, int mode)
{
    (void)name; (void)oflag; (void)mode;
    return -1;
}

static __inline int shm_unlink(const char *name)
{
    (void)name;
    return 0;
}

#ifdef __cplusplus
}
#endif

#endif /* OCTABAM_WINDOWS_SYS_MMAN_H */
