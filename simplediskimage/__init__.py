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
Module used to create simpler disk images, typically to boot embedded systems.

For more information see:
https://github.com/zqad/simplediskimage/
"""

import os
import logging
import shutil

from .tools import get_tool
from . import cfr
from .common import *
from .partitioners import PyParted, Sfdisk

def _copy_file_to_offset(source, destination, destination_offset_blocks,
                         block_size):
    copy_file_range = cfr.get_copy_file_range()
    length = os.path.getsize(source)
    destination_offset_bytes = destination_offset_blocks * block_size
    # Open destination in 'rb+', as this will allow us to write without
    # truncating the file.
    with open(source, 'rb') as f_src, open(destination, 'rb+') as f_dst:
        total_copied = 0
        while total_copied < length:
            offset = destination_offset_bytes + total_copied
            ncopied = copy_file_range(f_src.fileno(), f_dst.fileno(), length,
                                      offset_src=total_copied,
                                      offset_dst=offset)
            if ncopied < 0:
                logger.error("copy_file_range failed, aborting")
            total_copied += ncopied

def _round_up_to_blocksize(nbytes, blocksize):
    return nbytes + blocksize - nbytes % blocksize

def _create_sparse_file(path, size_bytes):
    with open(path, 'wb') as handle:
        handle.truncate(size_bytes)
        handle.flush()

class DiskImage():
    """
    Helper class to generate disk images.

    :param path: Path to the destination image file.
    :param partition_table: Partition table (label) format, `gpt` or `msdos`.
    :param temp_fmt: Format/path of the temp files containing format
                     strings for `path` and `extra`. Make sure the temp files
                     are on the same file system as the destination path.
    :param partitioner: Partitioner, for example PyParted or Sfdisk.
    """
    def __init__(self, path, partition_table='gpt',
                 temp_fmt="{path}-{extra}.tmp", partitioner=PyParted):
        self._path = path
        if partition_table not in ('gpt', 'msdos'):
            raise InvalidArguments("Partition table type {} is not "
                                   "supported".format(partition_table))
        self._partition_table = partition_table
        self._temp_fmt = temp_fmt

        self._partitioner = partitioner
        self._partitions = []
        self._blocksize = 512
        self._alignment_blocks = 32 # Align at 16k to make parted happy
        # Make sure we fit a GPT table at the beginning and end of the
        # disk, plus a MBR at the beginning
        if partition_table == 'gpt':
            self._padding_bytes = ((34 + 1) * 512, 34 * 512)
        elif partition_table == 'msdos':
            self._padding_bytes = (512, 0)

    def new_partition(self, filesystem, partition_label=None,
                      partition_flags=None, filesystem_label=None):
        """
        Create a new partition on this disk image.

        :param filesystem: File system, e.g. ext3 or fat32.
        :param partition_label: Partition label, only supported by GPT.
        :param partition_flags: Partition flags, e.g. BOOT.
        :param filesystem_label: File system label to be passed to mkfs.
        """
        if self._partition_table != 'gpt':
            if partition_label is not None:
                raise InvalidArguments("Partition labels are only "
                                       "supported by GPT")
        part_num = len(self._partitions) + 1
        part_suffix = "p" + str(part_num)
        temp_path = self._temp_fmt.format(path=self._path, extra=part_suffix)

        metadata = {}

        if partition_label is not None:
            metadata['partition_label'] = partition_label

        if filesystem_label is not None:
            metadata['filesystem_label'] = filesystem_label

        if partition_flags:
            metadata['flags'] = partition_flags

        if partition_label is not None:
            metadata['label'] = partition_label

        partition = Partition(self, temp_path, filesystem, self._blocksize,
                              metadata)

        self._partitions.append(partition)

        return partition

    def check(self):
        """
        Check this disk image for errors that will hinder us from doing a
        `commit()` later.

        Will call `.check()` for each partition too.
        """
        errors = 0

        # Check partitions
        for partition in self._partitions:
            if not partition.check():
                errors += 1
        return errors == 0

    def _bytes_to_blocks(self, nbytes, aligned=False):
        blocks = (nbytes + self._blocksize - 1) // self._blocksize
        if aligned and blocks % self._alignment_blocks > 0:
            blocks += self._alignment_blocks - blocks % self._alignment_blocks
        return blocks

    def commit(self):
        """
        Commit this disk image and create the image.
        """
        # Get total image size
        image_size_bytes = self.get_size_bytes()

        # Create sparse file of the correct size
        temp_path = self._temp_fmt.format(path=self._path, extra="image")
        _create_sparse_file(temp_path, image_size_bytes)

        # Create disk label and constraint
        partitioner = self._partitioner(temp_path, self._partition_table)

        # Create partitions
        start_blocks = self._bytes_to_blocks(self._padding_bytes[0],
                                             aligned=True)
        partitions_offset_blocks = []
        for partition in self._partitions:
            metadata = partition.metadata
            partitions_offset_blocks.append(start_blocks)
            partition_size_bytes = partition.get_total_size_bytes()
            partition_size_blocks = self._bytes_to_blocks(partition_size_bytes)

            partitioner.new_partition(start_blocks, partition_size_blocks,
                                      partition.filesystem,
                                      label=metadata.get('label', None),
                                      flags=metadata.get('flags', []))

            # Update start_blocks
            start_blocks += self._bytes_to_blocks(partition_size_blocks * 512,
                                                  aligned=True)

        partitioner.commit()

        # Write out partition files
        for partition in self._partitions:
            partition.commit()

        # Double check the file sizes
        for partition in self._partitions:
            if partition.get_total_size_bytes() < os.path.getsize(partition.path):
                raise UnknownError("Partition size changed during creation")

        # Copy partition files into image file
        for partition, offset_blocks in zip(self._partitions,
                                            partitions_offset_blocks):
            _copy_file_to_offset(partition.path, temp_path, offset_blocks,
                                 self._blocksize)

        # Clean up partition temp files
        for partition in self._partitions:
            partition.clean()

        # Move tempfile into place
        if os.path.exists(self._path):
            os.unlink(self._path)
        shutil.move(temp_path, self._path)

    def get_size_bytes(self):
        """
        Calculate and return the size of the disk image.
        """
        tot_blocks = self._bytes_to_blocks(self._padding_bytes[0],
                                           aligned=True)
        for partition in self._partitions:
            tot_blocks += self._bytes_to_blocks(partition.get_total_size_bytes(),
                                                aligned=True)
        tot_blocks += self._bytes_to_blocks(self._padding_bytes[1],
                                            aligned=True)
        return tot_blocks * self._blocksize

class Partition():
    """
    Create partition instance, do not call directly, use
    `Diskimage.new_partition()`.

    :param disk_image: Disk image instance.
    :param path: Path to the partition temp file.
    :param filesystem: File system for this partition.
    :param blocksize: Block (sector) size.
    :param metadata: Metadata.
    """
    def __init__(self, disk_image, path, filesystem, blocksize, metadata=None):
        self._disk_image = disk_image
        self.path = path
        self.filesystem = filesystem
        self.metadata = metadata
        self._blocksize = blocksize
        self._mkfs = get_tool(filesystem, 'mkfs')
        self._populate_actions = None
        self._content_size_bytes = 0
        self._extra_bytes = 0
        self._fixed_size_bytes = None
        self._fs_metadata_bytes = 1 * SI.Mi
        self._populate = None

    def _init_populate(self):
        if self._populate_actions is None:
            self._populate = get_tool(self.filesystem, 'populate')
            self._populate_actions = []

    def mkdir(self, *dirs):
        """
        Create one or many directories.

        :param dirs: The directories to create.
        """
        self._init_populate()
        self._populate_actions.append(('mkdir', list(dirs)))

    def copy(self, *source_paths, destination='/'):
        """
        Copy one or more files or directories recursively to the destination
        directory.

        :param source_paths: The files to copy.
        :param destination: The destination to which to copy, default `/`.
        """
        self._init_populate()
        recursive_paths = []
        non_recursive_paths = []
        for source_path in source_paths:
            # Determine if this is a recursive or non-recursive copy
            if os.path.isdir(source_path):
                recursive_paths.append(source_path)
                # Add upp the file sizes recursively
                for parent, _dirs, files in os.walk(source_path):
                    for filename in files:
                        path = os.path.join(parent, filename)
                        self._content_size_bytes += os.path.getsize(path)
            elif os.path.isfile(source_path):
                non_recursive_paths.append(source_path)
                self._content_size_bytes += os.path.getsize(source_path)
            else:
                Exception("Unsupported file type: {}", source_path)

        if recursive_paths:
            self._populate_actions.append(('copy recursive', recursive_paths,
                                           destination))
        if non_recursive_paths:
            self._populate_actions.append(('copy', non_recursive_paths,
                                           destination))

    def set_extra_bytes(self, num):
        """
        Set the extra bytes to be added to the size on top of the content size.

        :param num: The number of bytes, see the SI class for conversion.
        """
        self._extra_bytes = num

    def set_fixed_size_bytes(self, num):
        """
        Set a fixed size of this partition.

        :param num: The number of bytes, see the SI class for conversion.
        """
        self._fixed_size_bytes = _round_up_to_blocksize(num, self._blocksize)

    def get_content_size_bytes(self):
        """
        Get the size of all content copied into this image so far.
        """
        return self._content_size_bytes

    def get_total_size_bytes(self):
        """
        Get the total size of this image, using the fixed size if set, or the
        content + extra bytes if not.
        """
        if self._fixed_size_bytes is None:
            return _round_up_to_blocksize(self._content_size_bytes +
                                          self._extra_bytes +
                                          self._fs_metadata_bytes,
                                          self._blocksize)
        return self._fixed_size_bytes

    def commit(self):
        """
        Commit this partition to it's temp file, do not call directly.
        """
        if not self.check():
            raise CheckFailed("Check failed during commit")

        self.clean()
        file_size = self.get_total_size_bytes()

        _create_sparse_file(self.path, file_size)
        self._mkfs.mkfs(self.path, label=self.metadata.get('filesystem_label',
                                                           None))
        if self._populate_actions:
            self._populate.run(self.path, self._populate_actions)

    def clean(self):
        """
        Clean up all temp files of this partition.
        """
        if os.path.exists(self.path):
            os.unlink(self.path)

    def check(self):
        """
        Run a check of this partition, also called by DiskImage.
        """
        if not self._mkfs.check():
            logger.error("Could not find mkfs for file system %s",
                         self.filesystem)
            return False
        if self._populate_actions and not self._populate.check():
            logger.error("Could not find populate tool for file system %s",
                         self.filesystem)
            return False

        if self._fixed_size_bytes is not None:
            if self._fixed_size_bytes < self.get_total_size_bytes():
                logger.error("Could not fit everything into partition %s",
                             self.path)
                return False

        return True
