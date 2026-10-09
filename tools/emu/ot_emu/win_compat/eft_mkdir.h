/* MinGW portability shim for mischa85/elektron-firmware-tool: its
 * make_outdir() calls the POSIX two-argument mkdir(path, 0755), but MinGW's
 * <io.h> provides single-argument mkdir(). Include this after the system
 * headers (with -include) so only the call sites are rewritten. */
#ifndef OCTABAM_EFT_MKDIR_H
#define OCTABAM_EFT_MKDIR_H

#include <sys/stat.h>
#include <sys/types.h>
#include <io.h>
#include <direct.h>

static __inline int octabam_eft_mkdir(const char *path, int mode)
{
    (void)mode;
    return _mkdir(path);
}

#define mkdir(p, m) octabam_eft_mkdir((p), (m))

#endif /* OCTABAM_EFT_MKDIR_H */
