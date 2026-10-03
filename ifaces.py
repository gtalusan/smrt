#!/usr/bin/env python3
import ctypes
import os
import socket
import sys

AF_INET = socket.AF_INET
if sys.platform == 'linux':
    AF_LINK = 17  # AF_PACKET
else:
    AF_LINK = 18  # AF_LINK (macOS/BSD)

if sys.platform == 'linux':
    # Linux sockaddrs: 16-bit family at offset 0, no length byte
    class Sockaddr(ctypes.Structure):
        _fields_ = [('sa_family', ctypes.c_uint16),
                    ('sa_data', ctypes.c_char * 14)]
else:
    # macOS/BSD sockaddrs: length byte, then family byte
    class Sockaddr(ctypes.Structure):
        _fields_ = [('sa_len', ctypes.c_uint8),
                    ('sa_family', ctypes.c_uint8),
                    ('sa_data', ctypes.c_char * 14)]

class SockaddrDl(ctypes.Structure):
    _fields_ = [('sdl_len', ctypes.c_uint8),
                ('sdl_family', ctypes.c_uint8),
                ('sdl_index', ctypes.c_uint16),
                ('sdl_type', ctypes.c_uint8),
                ('sdl_nlen', ctypes.c_uint8),
                ('sdl_alen', ctypes.c_uint8),
                ('sdl_slen', ctypes.c_uint8),
                ('sdl_data', ctypes.c_char * 12)]

class Ifaddrs(ctypes.Structure):
    pass
Ifaddrs._fields_ = [('ifa_next', ctypes.POINTER(Ifaddrs)),
                    ('ifa_name', ctypes.c_char_p),
                    ('ifa_flags', ctypes.c_uint),
                    ('ifa_addr', ctypes.POINTER(Sockaddr)),
                    ('ifa_netmask', ctypes.POINTER(Sockaddr)),
                    ('ifa_dstaddr', ctypes.POINTER(Sockaddr)),
                    ('ifa_data', ctypes.c_void_p)]

libc = ctypes.CDLL(None, use_errno=True)
libc.getifaddrs.argtypes = [ctypes.POINTER(ctypes.POINTER(Ifaddrs))]
libc.getifaddrs.restype = ctypes.c_int
libc.freeifaddrs.argtypes = [ctypes.POINTER(Ifaddrs)]

def interfaces():
    return [name for index, name in socket.if_nameindex()]

def ifaddresses(interface):
    addrs = {}
    ptr = ctypes.POINTER(Ifaddrs)()
    if libc.getifaddrs(ctypes.byref(ptr)) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    ifa = ptr
    while ifa:
        ifa = ifa.contents
        if ifa.ifa_name and ifa.ifa_name.decode() == interface:
            sa = ifa.ifa_addr
            if sa:
                family = sa.contents.sa_family
                if family == AF_INET:
                    # sockaddr_in: len(1) family(1) port(2) addr(4)
                    raw = ctypes.string_at(sa, 16)
                    entry = {'addr': socket.inet_ntoa(raw[4:8]), 'broadcast': None}
                    if ifa.ifa_dstaddr and ifa.ifa_dstaddr.contents.sa_family == AF_INET:
                        entry['broadcast'] = socket.inet_ntoa(ctypes.string_at(ifa.ifa_dstaddr, 16)[4:8])
                    addrs.setdefault(AF_INET, []).append(entry)
                elif family == AF_LINK:
                    entry = {'addr': ''}
                    if sys.platform == 'linux':
                        # sockaddr_ll: halen(1) at 11, addr(8) at 12
                        raw = ctypes.string_at(sa, 20)
                        entry['addr'] = ':'.join('%02x' % b for b in raw[12:12 + raw[11]])
                    else:
                        dl = ctypes.cast(sa, ctypes.POINTER(SockaddrDl)).contents
                        entry['addr'] = ':'.join('%02x' % b for b in dl.sdl_data[dl.sdl_nlen:dl.sdl_nlen + dl.sdl_alen])
                    if entry['addr']:
                        addrs.setdefault(AF_LINK, []).append(entry)
        ifa = ifa.ifa_next
    libc.freeifaddrs(ptr)
    return addrs
