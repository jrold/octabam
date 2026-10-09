/* Windows shim for <sys/wait.h>. ot_emu's only fork/wait user is the
 * --scenario isolation mode, which a gated batch run does not use; these
 * declarations let main.cpp compile. */
#ifndef OCTABAM_WIN_SYS_WAIT_H
#define OCTABAM_WIN_SYS_WAIT_H

#include <sys/types.h>

#define WIFEXITED(s)   1
#define WEXITSTATUS(s) ((s) & 0x7f)
#define WIFSIGNALED(s) 0
#define WTERMSIG(s)    0
#define WNOHANG        1

static __inline pid_t fork(void) { return -1; }
static __inline pid_t wait(int* _status) { (void)_status; return -1; }
static __inline pid_t waitpid(pid_t, int*, int) { return -1; }

#endif /* OCTABAM_WIN_SYS_WAIT_H */
