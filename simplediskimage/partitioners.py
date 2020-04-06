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
Abstraction of different partitioning tools used by simple disk image
"""

from .common import logger, SI, DiskImageException, InvalidArguments, \
        UnknownError
from .tools import get_tool

class Partitioner():
    """
    Partitioner abstraction class

    :param image_path: Path to the image to be created
    :param table_type: Partition table type (label type), 'gpt' or 'msdos'
    """
    def __init__(self, image_path, table_type):
        raise DiskImageException("Not implemented!")

    def new_partition(self, offset_blocks, size_blocks, filesystem, label=None,
                      flags=()):
        """
        Create new partition

        :param offset_blocks: Offset for the new partition in blocks (sectors)
        :param size_blocks: Size of the new partition in blocks (sectors)
        :param filesystem: File system of the new partition
        :param label: Partition label of the new partition, only for GPT
        :param flags: Flags for the new partition
        """
        raise DiskImageException("Not implemented!")

    def commit(self):
        """
        Commit the partition table to the image
        """
        raise DiskImageException("Not implemented!")

class PartitionerException(DiskImageException):
    """
    Generic partitioner error
    """

class SfdiskException(PartitionerException):
    """
    Sfdisk partitioner error
    """

class PyPartedException(PartitionerException):
    """
    PyParted partitioner error
    """

# pylint: disable=too-many-return-statements
def _get_filesystem_type(filesystem, size_bytes):
    if filesystem in ('ext2', 'ext3', 'ext4'):
        return 0x53

    if filesystem == 'fat12':
        return 0x01

    if filesystem == 'fat16':
        if size_bytes < SI.Mi * 32:
            return 0x04 # FAT16 <32M

        if size_bytes > SI.Gi * 8:
            return 0x0E # LBA

        return 0x06

    if filesystem == 'fat32':
        if size_bytes > SI.Gi * 8:
            return 0x0C # LBA

        return 0x0B

    # Fall through
    raise PartitionerException("Unknown file system: {}".format(filesystem))

class Sfdisk(Partitioner):
    """
    Sfdisk partitioner abstraction
    """
    _allowed_flags = set(['BOOT'])

    def __init__(self, image_path, table_type):
        if table_type != 'msdos':
            raise DiskImageException("Table type not supported by this "
                                     "partitioner!")
        self._image_path = image_path
        self._tool = get_tool('none', 'sfdisk')
        self._commands = [
            "unit: sectors",
            "label: dos",
            "grain: 512", # Take care of alignment elsewhere
        ]

    def new_partition(self, offset_blocks, size_blocks, filesystem, label=None,
                      flags=()):
        # Check label
        if label is not None:
            raise SfdiskException("Labels not supported for msdos type")

        # Parse filesystem
        fs_type = _get_filesystem_type(filesystem, size_blocks * 512)

        # Parse flags
        if not self._allowed_flags >= set(flags):
            errflags = set(flags) - self._allowed_flags
            raise SfdiskException("Disallowed flags: {}".format(errflags))
        bootable_string = ''
        if 'BOOT' in flags:
            bootable_string = ', bootable'

        # Generate command
        self._commands.append(
            'start={}, size={}, type={:x}{}'.format(offset_blocks, size_blocks,
                                                    fs_type, bootable_string)
        )

    def commit(self):
        stdin = "\n".join(self._commands)
        logger.debug("sfdisk input:\n%s", stdin)
        self._tool.call(self._image_path, '--no-reread', '--no-tell-kernel',
                        input=stdin.encode('utf-8'))

class PyParted(Partitioner):
    """
    PyParted partitioner abstraction
    """
    _allowed_flags = set(['BOOT'])

    def __init__(self, image_path, table_type):
        import parted
        self._pmod = parted

        if table_type not in ('msdos', 'gpt'):
            raise DiskImageException("Table type not supported by this "
                                     "partitioner!")
        self._table_type = table_type
        self._image_path = image_path
        self._tool = get_tool('none', 'sfdisk')
        self._blocksize = 512
        self._partitions = []
        self._commands = [
            "unit: sectors",
            "label: dos",
            "grain: 512", # Take care of alignment elsewhere
        ]

        self._parted_flag_map = {
            'BOOT':              parted.PARTITION_BOOT,
            'ROOT':              parted.PARTITION_ROOT,
            'SWAP':              parted.PARTITION_SWAP,
            'HIDDEN':            parted.PARTITION_HIDDEN,
            'RAID':              parted.PARTITION_RAID,
            'LVM':               parted.PARTITION_LVM,
            'LBA':               parted.PARTITION_LBA,
            'HPSERVICE':         parted.PARTITION_HPSERVICE,
            'PALO':              parted.PARTITION_PALO,
            'PREP':              parted.PARTITION_PREP,
            'MSFT_RESERVED':     parted.PARTITION_MSFT_RESERVED,
            'APPLE_TV_RECOVERY': parted.PARTITION_APPLE_TV_RECOVERY,
            'BIOS_GRUB':         parted.PARTITION_BIOS_GRUB,
            'DIAG':              parted.PARTITION_DIAG,
            'LEGACY_BOOT':       parted.PARTITION_LEGACY_BOOT,
        }

    def new_partition(self, offset_blocks, size_blocks, filesystem, label=None,
                      flags=()):
        partition = {
            'offset_blocks': offset_blocks,
            'size_blocks': size_blocks,
            'filesystem': filesystem,
        }
        if flags:
            partition['flags'] = []
        for flag in flags:
            if flag not in self._parted_flag_map:
                flags = ", ".join(self._parted_flag_map.keys())
                raise InvalidArguments("Flag {} invalid. Possible "
                                       "choices: {}".format(flag, flags))
            partition['flags'].append(self._parted_flag_map[flag])

        if label is not None:
            partition['label'] = label
        self._partitions.append(partition)

    def commit(self):
        # Create disk label and constraint
        parted_device = self._pmod.getDevice(self._image_path)
        logger.debug("Parted: Created device: %s", parted_device)
        parted_disk = self._pmod.freshDisk(parted_device, self._table_type)
        logger.debug("Parted: Created disk: %s", parted_disk)
        parted_constraint = parted_device.minimalAlignedConstraint

        # Sanity check
        if not parted_device.sectorSize == self._blocksize:
            raise PyPartedException("Parted sector size mismatches with our blocksize")

        for partition in self._partitions:
            # Create geometry
            geometry = self._pmod.Geometry(device=parted_device,
                                           start=partition['offset_blocks'],
                                           length=partition['size_blocks'])
            logger.debug('Parted: Created geometry: %s', geometry)

            # Create partition (= filesystem)
            fs_type = partition['filesystem']
            # Work around parted not knowing about fat12
            if fs_type == 'fat12':
                fs_type = 'fat16'
            filesystem = self._pmod.FileSystem(type=fs_type, geometry=geometry)
            logger.debug('Parted: Created filesystem: %s', filesystem)
            parted_partition = self._pmod.Partition(disk=parted_disk,
                                                    type=self._pmod.PARTITION_NORMAL,
                                                    fs=filesystem, geometry=geometry)

            # Set metadata
            if 'label' in partition:
                parted_partition.set_name(partition['label'])
            for flag in partition.get('flags', []):
                if not parted_partition.isFlagAvailable(flag):
                    raise InvalidArguments("Flag was valid but rejected by "
                                           "pyparted")
                parted_partition.setFlag(flag)
            logger.debug('Parted: Created partition: %s', parted_partition)
            parted_disk.addPartition(partition=parted_partition,
                                     constraint=parted_constraint)

            # Sanity check: Try to get the partition we just created, to make
            # sure that parted did not re-align the partition by itself. If
            # that would happen, our calculations would be off.
            fetched_partition = parted_disk.getPartitionBySector(partition['offset_blocks'])
            if parted_partition.number != fetched_partition.number:
                raise UnknownError("Failed to re-fetch partition! Expected "
                                   "{}, {}".format(parted_partition,
                                                   fetched_partition))

        parted_disk.commit()
