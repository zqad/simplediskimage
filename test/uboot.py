#!/usr/bin/env python3

import subprocess
import logging
import os
import time
import signal
import atexit
import hashlib
import select
import re
import pty
from distutils.dir_util import mkpath

import requests

logger = logging.getLogger(__name__)

PROMPT = rb'=>[ ]+'
PROMPT_RE = re.compile(PROMPT)
PROMPT_RE_END = re.compile(PROMPT + b'$')
ENDL = b'\r\n'

class UBoot():
    def __init__(self, bin_path, log_path):
        # Create a pty fd pair to use as stdin/stdout/stderr from the process
        # - If using Popen.stdout or .fd, we will lose some lines, probably due
        #   to Python moving it to a buffer
        # - If u-boot stdin is not a tty, it will not set it to non-blocking,
        #   meaning that in some magic cases, it will try to read from stdin
        #   instead of outputing to stdout. This is probably due to it
        #   considering a non-tty input to be non-interactive. But we are using
        #   it very much interactively, so we must set up a pty.
        parent_fd, child_fd = pty.openpty()
        os.set_blocking(parent_fd, False)
        os.set_inheritable(child_fd, True)
        # Save the parent fd
        self._comm_fd = parent_fd

        # Create poll object
        self._stdout_poll = select.poll()
        self._stdout_poll.register(self._comm_fd, select.POLLIN)

        logger.info('Running %s', bin_path)
        command = [bin_path]

        # Run setsid before exec to run the process in a new session
        self._proc = subprocess.Popen(command,
                                      stdin=child_fd,
                                      stdout=child_fd,
                                      stderr=child_fd,
                                      preexec_fn=os.setsid,
                                      bufsize=0)
        os.close(child_fd)

        # Create and register cleanup handler
        def cleanup():
            self.terminate()
        atexit.register(cleanup)

        # Open log and set up output buffers
        logger.info('Logging u-boot output to %s', log_path)
        self._log_handle = open(log_path, 'wb', buffering=0)
        self._stdout = bytearray()

        # The process is now running
        self.running = True

    def terminate(self):
        sigs = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)
        for sig in sigs:
            logger.debug("Sending signal %s to process", sig)
            self._proc.send_signal(sig)
            try:
                self._proc.wait(5)
            except subprocess.TimeoutExpired:
                logger.debug("Failed to kill process using %s", sig)
                continue
            self.running = False
            return

    def send_line(self, line, clear_output=True):
        send = bytearray(line)
        send += b'\r'
        if clear_output:
            # The caller probably expects to match on the output after this
            # command. Read all and clear the stdout buffer to make sure that
            # stale data is not matched.
            self.communicate()
            self._stdout.clear()
        self.communicate(send)

    def communicate(self, stdin_data=None):
        while stdin_data:
            nbytes = os.write(self._comm_fd, stdin_data)
            if nbytes < 0:
                # Process has died
                self.running = False
                return
            stdin_data = stdin_data[nbytes:]
        while self._stdout_poll.poll(0.2):
            # Make any busywait a bit less bad
            time.sleep(0.2)
            stdout = os.read(self._comm_fd, 4096)
            if stdout == '':
                # Process has died
                self.running = False
                return
            self._no_input_counter = 0
            self._log_handle.write(stdout)
            self._stdout += stdout


    def match_output(self, regexps, timeout=30,
                     return_on_first_matching_function=True):
        funcs = [r.match for r in regexps]
        return self._run_func_on_output(funcs, timeout,
                                        return_on_first_matching_function)

    def search_output(self, regexps, timeout=30,
                      return_on_first_matching_function=True):
        funcs = [r.search for r in regexps]
        return self._run_func_on_output(funcs, timeout,
                                        return_on_first_matching_function)

    def _run_func_on_output(self, funcs, timeout,
                            return_on_first_matching_function):
        timeout_time = time.monotonic() + timeout
        while True:
            matches = []
            for i, func in enumerate(funcs):
                mobj = func(self._stdout)
                if mobj:
                    skipped = self._stdout[:mobj.start()]
                    matched = self._stdout[mobj.start():mobj.end()]
                    match_tuple = (i, mobj, skipped, matched)
                    if return_on_first_matching_function:
                        self._stdout = self._stdout[mobj.end():]
                        return match_tuple

                    # Save match and see if there are more
                    matches.append(match_tuple)

            if matches:
                # If we did have a match, but has not returned yet, sort all
                # matches on the 'skipped' field, and return the one with the
                # lowest amount of bytes skipped before the match (return the
                # least greedy match)
                result = sorted(matches, key=lambda t: t[2])[0]
                self._stdout = self._stdout[result[1].end():]
                return result

            if time.monotonic() > timeout_time:
                raise Exception('Timeout!')
            # Poll for data
            self.communicate()

        raise Exception('Timeout while matching output. State: '
                        '{}'.format(str(self)))

    def __str__(self):
        return 'UBoot(_stdout={})'.format(self._stdout)


def setup_uboot(tempdir, final_path):
    uboot_version = '2020.07'
    uboot_source_sha256 = 'c1f5bf9ee6bb6e648edbf19ce2ca9452f614b08a9f886f1a566aa42e8cf05f6a'

    uboot_source_url = 'http://ftp.denx.de/pub/u-boot/u-boot-{}.tar.bz2'.format(uboot_version)

    uboot_source_dir = 'u-boot-{}'.format(uboot_version)
    uboot_source_dir_path = os.path.join(tempdir, uboot_source_dir)
    uboot_source_tar_path = os.path.join(tempdir, 'u-boot.tar.bz2')

    logs_path = os.path.join(tempdir, 'logs')
    mkpath(logs_path)

    logger.info('Downloading and validating u-boot source')
    req = requests.get(uboot_source_url)
    with open(uboot_source_tar_path + '.download', 'wb') as file_handle:
        mac = hashlib.sha256()
        mac.update(req.content)
        if mac.hexdigest() != uboot_source_sha256:
            raise Exception('Downloaded sources mismatch, expected {}, got '
                            '{}'.format(uboot_source_sha256, mac.hexdigest()))
        file_handle.write(req.content)
    os.rename(uboot_source_tar_path + '.download', uboot_source_tar_path)

    logger.info('Unpacking u-boot source')
    with open(os.path.join(logs_path, 'u-boot-unpack.log'), 'w') as log_handle:
        proc = subprocess.Popen(['tar', '-C', tempdir, '-jxvf',
                                 uboot_source_tar_path], stdout=log_handle,
                                stderr=log_handle)
        proc.communicate()
        if proc.returncode != 0:
            raise Exception('Unpack failed, see logs/u-boot-unpack.log')

    logger.info('Compiling u-boot')
    with open(os.path.join(logs_path, 'u-boot-build.log'), 'w') as log_handle:
        source_path = os.path.join(tempdir, uboot_source_dir)
        proc = subprocess.Popen(['make', '-C', source_path, 'sandbox_defconfig'],
                                stdout=log_handle, stderr=log_handle)
        proc.communicate()
        if proc.returncode != 0:
            raise Exception('make sandbox_defconfig failed, see '
                            'logs/u-boot-build.log')
        proc = subprocess.Popen(['make', '-C', source_path, '-j4', 'u-boot'],
                                stdout=log_handle, stderr=log_handle)
        proc.communicate()
        if proc.returncode != 0:
            raise Exception('make u-boot failed, see '
                            'logs/u-boot-build.log')

    logger.info('Linking u-boot binary into place')
    os.link(os.path.join(tempdir, uboot_source_dir, 'u-boot'),
            final_path)
