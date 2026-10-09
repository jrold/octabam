/* Windows shim for <dlfcn.h>. ot_emu includes it but never calls dlopen on any
 * path this port builds; the loader helpers are provided as inert stubs. */
#ifndef OCTABAM_WIN_DLFCN_H
#define OCTABAM_WIN_DLFCN_H

#ifndef RTLD_LAZY
#define RTLD_LAZY   0x00001
#define RTLD_NOW    0x00002
#define RTLD_GLOBAL 0x00100
#define RTLD_LOCAL  0x00000
#define RTLD_DEFAULT ((void*)0)
#endif

static __inline void* dlopen(const char* _file, int _mode) { (void)_file; (void)_mode; return 0; }
static __inline int   dlclose(void* _h) { (void)_h; return 0; }
static __inline void* dlsym(void* _h, const char* _s) { (void)_h; (void)_s; return 0; }
static __inline char* dlerror(void) { return (char*)"dlopen is not available on this host"; }

#endif /* OCTABAM_WIN_DLFCN_H */
