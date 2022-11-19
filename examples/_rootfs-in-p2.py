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
import sys
import os
import tarfile

import simplediskimage

from common import generate_bb_testdata

logging.basicConfig(level=logging.DEBUG)

def main():
    # Check our surroundings, we should be:
    # - Getting the tempdir containing rootfs.tar as the sole argument
    # - Be executed inside a fakeroot environment
    if len(sys.argv) != 2 or "FAKEROOTKEY" not in os.environ:
        print("Don't run me directly, use rootfs-in-p2.sh")
        sys.exit(1)

    # Generate some testdata for the boot partition
    generate_bb_testdata()

    # Create image
    image = simplediskimage.DiskImage("rootfs-in-p2.img",
                                      partition_table='msdos',
                                      partitioner=simplediskimage.Sfdisk)
    part_fat = image.new_partition("fat16", partition_flags=["BOOT"])
    part_ext = image.new_partition("ext4", filesystem_label="root")

    # Copy files to the boot partition and set a fixed size
    part_fat.copy("generated/u-boot.img")
    part_fat.copy("generated/MLO")
    part_fat.set_fixed_size_bytes(48 * simplediskimage.SI.Mi)

    # Unpack the rootfs.tar file into a temporary directory
    temp_dir = sys.argv[1]
    rootfs_tar = os.path.join(temp_dir, "rootfs.tar")
    rootfs_dir = os.path.join(temp_dir, "p2-rootfs-dir")
    with tarfile.open(rootfs_tar, 'r:') as tf:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(tf, rootfs_dir)

    # Use the rootfs directory as the initial data directory for the second
    # partition (the rootfs)
    part_ext.set_initial_data_root(rootfs_dir)

    image.commit()
    print("sudo kpartx -av rootfs-in-p2.img")
    print("...")
    print("sudo kpartx -dv rootfs-in-p2.img")

if __name__ == '__main__':
    main()
