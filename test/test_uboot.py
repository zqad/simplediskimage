#!/usr/bin/env python3

import tempfile
import os
import re
import logging
from queue import Queue, Empty
import hashlib
import tempfile

from distutils.dir_util import mkpath
import pytest

from uboot import setup_uboot, UBoot, PROMPT, PROMPT_RE_END, ENDL

import simplediskimage
from simplediskimage import SI

logger = logging.getLogger(__name__)

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_PREFIX = '/tmp/simplediskimage-test.XXXXXX'

# Helper class to simplify iterating over a queue
class QueueIter():
    def __init__(self, queue):
        self._queue = queue
    def __iter__(self):
        return self
    def __next__(self):
        try:
            return self._queue.get_nowait()
        except Empty:
            raise StopIteration

@pytest.fixture
def uboot_process():
    basedir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'tmp')
    mkpath(basedir)
    uboot_executable = os.path.join(basedir, 'u-boot')
    if not os.path.exists(uboot_executable):
        prefix = os.path.join(basedir, 'u-boot-')
        tempdir = tempfile.mkdtemp(prefix=prefix)
        setup_uboot(tempdir, uboot_executable)
    date = 'now' # TODO
    logfile_path = os.path.join(basedir, 'u-boot-{}.log'.format(date))
    proc = UBoot(uboot_executable, logfile_path)
    proc.search_output([re.compile(b'Hit any key to stop autoboot:')])
    proc.send_line(b'')
    return proc

def _generate_file(path, size=SI.Mi, data=None):
    if data is None:
        data = os.path.basename(path)
    mkpath(os.path.dirname(path))
    with open(path, 'w') as f:
        for _ in range(0, int(size / len(data))):
            f.write(data)
        if size % len(data) > 0:
            f.write(data[0:size % len(data)])

def _sha1sum(parent, filename):
    with open(os.path.join(parent, filename), 'rb') as f:
        m = hashlib.sha1()
        while True:
            data = f.read(1024*1024*16)
            if data is None or data == b'':
                break
            m.update(data)
        return m.hexdigest()

def _compare_sets(expected_set, observed_set, description, errors):
    missing = expected_set.difference(observed_set)
    superfluous = observed_set.difference(expected_set)
    if missing:
        errors.append("{} missing: {}".format(description,
                                              ", ".join(missing)))
    if superfluous:
        errors.append("{} got superfluous elements: {}".format(
            description, ", ".join(superfluous)))

def _compare_directory_with_partition(up, source_dir, dest_image,
                                      dest_partition,
                                      ignore_list=('lost+found',)):
    # Make sure paths are absolute
    if not dest_image.startswith('/'):
        # Path is relative to the test directory
        dest_image = os.path.join(TEST_DIR, dest_image)
    if not source_dir.startswith('/'):
        # Path is relative to the test directory
        source_dir = os.path.join(TEST_DIR, source_dir)

    # Initialize by getting a prompt and binding the file to a host device in
    # u-boot. We expect 0 not in use currently, or be ok to overwrite.
    up.send_line(b'')
    up.search_output([PROMPT_RE_END])
    up.send_line(b'host bind 0 ' + os.path.abspath(dest_image).encode('ascii'))
    up.search_output([PROMPT_RE_END])

    # Get a list of all files and directories in the source directory for later
    # comparison
    source_files = set()
    source_directories = set()
    source_sha1sums = {}
    eat_len = len(source_dir)
    if not source_dir.endswith('/'):
        eat_len += 1
    for dirpath, dirnames, filenames in os.walk(source_dir):
        trunc_dirpath = dirpath[eat_len:]
        for name in dirnames:
            source_directories.add('/' + os.path.join(trunc_dirpath, name))
        for name in filenames:
            path = '/' + os.path.join(trunc_dirpath, name)
            source_files.add(path)
            source_sha1sums[path] = _sha1sum(dirpath, name)

    errors = []

    # List all files in all directories in the image recursively and build up
    # lists of them
    dest_directories = set()
    dest_files = set()
    queue = Queue()
    queue.put('/')
    # Prepare a list of regexps to match different outputs
    match_list = [
        # A prompt
        PROMPT_RE_END,
        # . or .. directories
        re.compile(ENDL + rb'[ ]+\.{1,2}/'),
        # A entry ending in / (directory)
        re.compile(ENDL + rb'[ ]+([^/\r]+)/'),
        # An entry with a size and name (file)
        re.compile(ENDL + rb'[ ]+([0-9])+[ ]+([^/\r]+)'),
        # A summary, displayed after an ls
        re.compile(ENDL + rb'[0-9]+ file\(s\), [0-9]+ dir\(s\)'),
        # An error message
        re.compile(ENDL + rb'\*\*[^\n]+\*\*'),
    ]
    # Time to run. Since we will (probabaly) find more directories, use a queue
    # that may be amended on the fly.
    for directory in iter(QueueIter(queue)):
        # Send 'ls' for a directory
        up.send_line(b'')
        up.search_output([PROMPT_RE_END])
        up.send_line(b'ls host 0:' + str(dest_partition).encode('ascii') + \
            b' ' + directory.encode('ascii'))
        # Match/parse the output
        while True:
            num, mobj, _skipped, matched = up.search_output(
                match_list, return_on_first_matching_function=False)
            logger.debug('Match no %d: %s', num, matched)
            if num == 0: # Prompt
                break
            if num == 1: # . or ..
                continue
            if num == 2: # Directory
                logger.debug('directory: %s', str(mobj))
                if mobj.group(1) in ignore_list:
                    continue
                path = os.path.join(directory, mobj.group(1).decode('ascii'))
                queue.put(path)
                dest_directories.add(path)
            elif num == 3: # File
                logger.debug('file: %s', str(mobj))
                if mobj.group(2) in ignore_list:
                    continue
                path = os.path.join(directory, mobj.group(2).decode('ascii'))
                dest_files.add(path)
            elif num == 4: # summary
                pass
            elif num == 5: # . or ..
                continue
            elif num == 6: # Error
                # Return directly, we see this as a critical error
                return False, matched
        up.communicate()

    # Check that all entries (and no extra) were included
    _compare_sets(source_directories, dest_directories, "Directories", errors)
    _compare_sets(source_files, dest_files, "Files", errors)

    # Check the contents of all files found
    for file_path in dest_files:
        file_path_b = file_path.encode('ascii')
        up.send_line(b'load host 0:1 ${kernel_addr_r} ' + file_path_b
                     + b'; hash sha1 ${kernel_addr_r} ${filesize}')
        _num, mobj, _skipped, matched = up.search_output(
            [re.compile(b'==> ([0-9a-f]+)\r')])
        dest_sha1sum = mobj.group(1).decode('ascii')
        source_sha1sum = source_sha1sums.get(file_path, b'')
        if not source_sha1sum == dest_sha1sum:
            errors.append('{} found with sha1sum {} (expected {})'.format(
                file_path, dest_sha1sum, source_sha1sum))

    # Summarize
    if errors:
        raise Exception("{}".format("\n".join(errors)))

def test_single_part(uboot_process):
    up = uboot_process
    with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as tempdir:
        # Generate some files
        root = os.path.join(tempdir, 'root')
        _generate_file(os.path.join(root, 'small'), size=(4 * SI.ki))
        _generate_file(os.path.join(root, 'big'), size=(4 * SI.Mi))
        _generate_file(os.path.join(root, 'dir/mid'), size=(512 * SI.ki))

        # Create image
        image_path = os.path.join(tempdir, 'image.img')
        image = simplediskimage.DiskImage(image_path, partition_table='msdos',
                                          partitioner=simplediskimage.Sfdisk)
        part_fat = image.new_partition('fat32', partition_flags=['BOOT'])
        part_fat.mkdir('dir')
        part_fat.copy(os.path.join(root, 'small'))
        part_fat.copy(os.path.join(root, 'big'))
        part_fat.copy(os.path.join(root, 'dir/mid'), destination='dir')
        image.check()
        image.commit()

        # Send line and wait for prompt
        up.send_line(b'')
        up.search_output([PROMPT_RE_END])

        # Compare partition to image
        _compare_directory_with_partition(up, root, image_path, 1)
