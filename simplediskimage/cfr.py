# Copyright 2019  Jonas Eriksson
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""
Wrappers and implementations of `copy_file_range`
"""

import sys
import platform
import ctypes
import os

from .common import SI, logger, UnknownError

# https://github.com/systemd/systemd/blob/v245/src/basic/missing_syscall.h#L329
_MACHINE_SYSCALL_NUM = {
    'x86_64': 326,
    'i386': 377,
    's390': 375,
    'arm': 391,
    'aarch64': 285,
    'powerpc': 379,
    'arc': 285,
}

_CACHED_WRAPPER = None

def _copy_file_range(src_fd, dst_fd, count, offset_src=None, offset_dst=None):
    """
    Naïve copy_file_range implementation, with some non-compatibilities

    This function does *not* behave exactly like the libc version, as it does
    not care about the position in the file; it will gladly change it no
    matter the values of offset_*.

    :param src_fd: Source/in file descriptor
    :param dst_fd: Destination/out file descriptor
    :param offset_src: Offset to seek to in source fd, or None to run from the
                       current position
    :param offset_dst: Offset to seek to in destination fd, or None to run from
                       the current position
    :type src_fd: int
    :type dst_fd: int
    :return: The amount copied
    """
    block_size = 16 * SI.Mi
    if offset_src is not None:
        if os.lseek(src_fd, offset_src, os.SEEK_SET) != offset_src:
            logger.error("Unable to seek to %d in source", offset_src)
            return -1
    if offset_dst is not None:
        if os.lseek(dst_fd, offset_dst, os.SEEK_SET) != offset_dst:
            logger.error("Unable to seek to %d in destination", offset_dst)
            return -1
    ncopied_total = 0
    while count > 0:
        buffer = os.read(src_fd, min(block_size, count))
        if not buffer:
            return ncopied_total
        ncopied = os.write(dst_fd, buffer)
        if ncopied < 0:
            return ncopied
        count -= ncopied
        ncopied_total += ncopied
    return ncopied_total

def _make_syscall_wrapper(machine):
    cfr = ctypes.CDLL(None, use_errno=True).syscall
    #    ssize_t copy_file_range(int fd_in, loff_t *off_in,
    #                       int fd_out, loff_t *off_out,
    #                       size_t len, unsigned int flags);
    cfr.restype = ctypes.c_ssize_t
    c_loff_t = ctypes.c_int64
    c_loff_t_p = ctypes.POINTER(c_loff_t)
    cfr.argtypes = [
        ctypes.c_long, # syscall num
        ctypes.c_int,
        c_loff_t_p,
        ctypes.c_int,
        c_loff_t_p,
        ctypes.c_size_t,
        ctypes.c_int
    ]
    def sc_copy_file_range(src_fd, dst_fd, count, offset_src=None,
                           offset_dst=None):
        off_in = ctypes.byref(c_loff_t(offset_src)) if offset_src is not None else None
        off_out = ctypes.byref(c_loff_t(offset_dst)) if offset_dst is not None else None
        result = cfr(_MACHINE_SYSCALL_NUM[machine], src_fd, off_in,
                     dst_fd, off_out, count, 0)
        error = ctypes.get_errno()
        if error != 0:
            raise UnknownError("Failed to copy data from fd {} to fd {}: {} ({})"
                               "".format(src_fd, dst_fd, os.strerror(error),
                                         error))
        return result

    return sc_copy_file_range

def _make_libc_wrapper():
    cfr = ctypes.CDLL(None, use_errno=True).copy_file_range
    #    ssize_t copy_file_range(int fd_in, loff_t *off_in,
    #                       int fd_out, loff_t *off_out,
    #                       size_t len, unsigned int flags);
    cfr.restype = ctypes.c_ssize_t
    c_loff_t = ctypes.c_int64
    c_loff_t_p = ctypes.POINTER(c_loff_t)
    cfr.argtypes = [
        ctypes.c_int,
        c_loff_t_p,
        ctypes.c_int,
        c_loff_t_p,
        ctypes.c_size_t,
        ctypes.c_int
    ]
    def lc_copy_file_range(src_fd, dst_fd, count, offset_src=None,
                           offset_dst=None):
        off_in = ctypes.byref(c_loff_t(offset_src)) if offset_src is not None else None
        off_out = ctypes.byref(c_loff_t(offset_dst)) if offset_dst is not None else None
        result = cfr(src_fd, off_in, dst_fd, off_out, count, 0)
        if result < 0:
            error = ctypes.get_errno()
            raise UnknownError("Failed to copy data from fd {} to fd {}: {} ({})"
                               "".format(src_fd, dst_fd, os.strerror(error),
                                         error))
        return result

    return lc_copy_file_range

def get_copy_file_range():
    """
    Get best suited copy_file_range implementation

    :return: `copy_file_range` function
    """
    global _CACHED_WRAPPER

    # Quick exit if a cached C wrapper already exists
    if _CACHED_WRAPPER is not None:
        return _CACHED_WRAPPER

    # Try to return native version
    try:
        from os import copy_file_range
        return copy_file_range
    except ImportError:
        pass

    # Check the libc version
    libc_type, libc_ver = platform.libc_ver()
    if libc_type == 'glibc':
        slibc_ver = libc_ver.split(".")
        if int(slibc_ver[0]) > 2 or (int(slibc_ver[0]) == 2 and
                                     int(slibc_ver[1]) >= 27):
            logger.debug("Construcing libc wrapper for copy_file_range")
            lc_copy_file_range = _make_libc_wrapper()
            _CACHED_WRAPPER = lc_copy_file_range
            return lc_copy_file_range

    # Check that we are on linux
    # pylint: disable=unreachable
    if not sys.platform.startswith("linux"):
        logger.warning("Not Linux, falling back to naive "
                       "copy_file_range implementation")
        _CACHED_WRAPPER = _copy_file_range
        return _copy_file_range

    # Check the kernel version
    kernel_release = platform.release()
    srelease = kernel_release.split(".")
    if int(srelease[0]) < 4 or (int(srelease[0]) == 4 and
                                int(srelease[1]) < 5):
        logger.warning("Old kernel version (%s), falling back to naive "
                       "copy_file_range implementation", kernel_release)
        _CACHED_WRAPPER = _copy_file_range
        return _copy_file_range

    # Make sure that the syscall exists on this platform
    machine = platform.machine()
    if not machine in _MACHINE_SYSCALL_NUM:
        logger.warning("Unknown machine %s for copy_file_range, falling back "
                       "to naive copy_file_range implementation", machine)
        _CACHED_WRAPPER = _copy_file_range
        return _copy_file_range

    logger.debug("Construcing syscall wrapper for copy_file_range")
    sc_copy_file_range = _make_syscall_wrapper(machine)
    _CACHED_WRAPPER = sc_copy_file_range

    return sc_copy_file_range
