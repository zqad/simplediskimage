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

logging.basicConfig(level=logging.DEBUG)

def main():
    image = simplediskimage.DiskImage("null-partitioner.ext4",
                                      partition_table='null',
                                      partitioner=simplediskimage.NullPartitioner)
    part = image.new_partition("ext4")

    # Allocate some extra data on top of what's taken up by the data on the
    # ext partition
    part.set_extra_bytes(2 * simplediskimage.SI.Mi)

    # Create two directories in the root of the partition
    part.mkdir("ext1", "ext2")

    # Copy some data from the testdata dir into the image
    datadir = os.path.abspath(os.path.join(os.path.dirname(__file__), "testdata"))
    part.copy(os.path.join(datadir, "x"), os.path.join(datadir, "y"))

    image.commit()
    print("sudo mount null-partitioner.ext4 /mnt")
    print("...")
    print("sudo umount /mnt")

if __name__ == '__main__':
    main()
