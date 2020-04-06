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
import os
from distutils.dir_util import mkpath

import simplediskimage

logging.basicConfig(level=logging.DEBUG)

def main():
    # Generate test data
    mkpath("generated")
    for filename, iterations in [("u-boot.img", 119078), ("MLO", 40334)]:
        path = os.path.join("generated", filename)
        if os.path.exists(path):
            continue
        with open(path, 'wb') as f:
            data = filename.encode('ascii')
            for _ in range(0, iterations):
                f.write(data)

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
