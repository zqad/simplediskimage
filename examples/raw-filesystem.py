#!/usr/bin/env python3
# Copyright 2020  Jonas Eriksson
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

import logging
import os

import simplediskimage

from common import generate_bb_testdata

logging.basicConfig(level=logging.DEBUG)

def main():
    ext4_source = "./null-partitioner.ext4"
    # Make sure the raw ext4 image has been created by running the
    # null-partitioner example
    if not os.path.exists(ext4_source):
        print("Run the null-partitioner.py example first")

    # Generate test data
    generate_bb_testdata()

    # Create image
    image = simplediskimage.DiskImage("raw-filesystem-on-p2.img",
                                      partition_table='msdos',
                                      partitioner=simplediskimage.Sfdisk)
    part_fat = image.new_partition("fat16", partition_flags=["BOOT"])
    part_ext = image.new_partition("ext4", raw_filesystem_image=True)

    # Copy the files to the root, could also be written:
    # part_fat.copy("file1", "file2", destination="/"), or without destination
    part_fat.copy("generated/u-boot.img")
    part_fat.copy("generated/MLO")

    # Make sure that the partition is always 48 MiB
    part_fat.set_fixed_size_bytes(48 * simplediskimage.SI.Mi)

    # Copy the ext image into the raw partition
    part_ext.copy(ext4_source)

    # The partition can be expanded beyond the size of the image, but beware
    # the warnings in the documentation before doing something like this!
    #part_ext.set_extra_bytes(16 * simplediskimage.SI.Mi)

    image.commit()
    print("sudo kpartx -av raw-filesystem-on-p2.img")
    print("...")
    print("sudo kpartx -dv raw-filesystem-on-p2.img")

if __name__ == '__main__':
    main()
