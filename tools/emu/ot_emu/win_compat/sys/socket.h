/* Windows shim for <sys/socket.h>. The only socket user in ot_emu is the USB
 * bench (usb.cpp), which the release user-path gate never instantiates (it
 * passes no --usb-host). Winsock2 provides socket/bind/listen/accept/connect,
 * AF_UNIX and struct sockaddr_un, so the shim is just that include; the USB
 * path's SOCKET-to-int handles are never exercised in a gated build. */
#ifndef OCTABAM_WIN_SYS_SOCKET_H
#define OCTABAM_WIN_SYS_SOCKET_H

#include <winsock2.h>

#endif /* OCTABAM_WIN_SYS_SOCKET_H */
