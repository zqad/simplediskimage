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

import simplediskimage

logging.basicConfig(level=logging.DEBUG)

def main():
    image = simplediskimage.DiskImage("foo.img", partition_table='gpt')
    part_fat = image.new_partition("fat12", partition_flags=["BOOT"],
                                   partition_label="EFI System Partition")
    part_ext = image.new_partition("ext4", filesystem_label="hello")

    # Allocate some extra data on top of what's taken up by the data on the
    # ext partition
    part_ext.set_extra_bytes(16 * simplediskimage.SI.Mi)

    # Create two directories in the root of each partition
    part_fat.mkdir("fat1", "fat2")
    part_ext.mkdir("ext1", "ext2")

    # Copy the testdata dir into each partition in some interesting ways
    datadir = os.path.abspath(os.path.join(os.path.dirname(__file__), "testdata"))
    for part in (part_fat, part_ext):
        part.copy(os.path.join(datadir, "x"), os.path.join(datadir, "y"))
        part.mkdir("internet")
        part.copy(os.path.join(datadir, "internet/z"), destination="internet")
        part.copy(os.path.join(datadir, "internet/recursive_copy"), destination="internet")

    image.commit()
    print("sudo kpartx -av foo.img")
    print("...")
    print("sudo kpartx -dv foo.img")

if __name__ == '__main__':
    main()
