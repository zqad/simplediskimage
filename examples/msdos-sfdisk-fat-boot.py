#!/usr/bin/env python3
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

import logging

import simplediskimage

from common import generate_bb_testdata

logging.basicConfig(level=logging.DEBUG)

def main():
    # Generate test data
    generate_bb_testdata()

    # Create image
    image = simplediskimage.DiskImage("bar.img", partition_table='msdos',
                                      partitioner=simplediskimage.Sfdisk)
    part_fat = image.new_partition("fat16", partition_flags=["BOOT"])

    # Copy the files to the root, could also be written:
    # part_fat.copy("file1", "file2", destination="/"), or without destination
    part_fat.copy("generated/u-boot.img")
    part_fat.copy("generated/MLO")

    # Make sure that the partition is always 48 MiB
    part_fat.set_fixed_size_bytes(48 * simplediskimage.SI.Mi)

    image.commit()
    print("sudo kpartx -av bar.img")
    print("...")
    print("sudo kpartx -dv bar.img")

if __name__ == '__main__':
    main()
