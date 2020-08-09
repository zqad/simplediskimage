#!/bin/sh -e
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

# This example might look a bit convoluted as we create an archive here just to
# extract it in the companion python script, but we are simulating a situation
# where a separate build system delivers a tar (might as well be a cpio
# archive), which the python script will unpack and use as the basis of a
# partition. There are multiple variants to this, for example:
#
# - The rootfs is delivered as a directory. In this case, the image creation
#   script might be run in the same fakeroot session, or the -s and -i
#   arguments to fakeroot may be used.
# - The rootfs is created using some python scripts under a fakeroot session.
#   If so, just add some calls to simplediskimage when the rootfs has been
#   created to turn it into an image.

TEMPDIR=./.rootfs-in-p2.tmp
EXAMPLE_USER=nobody
if ! id nobody &> /dev/null; then
  EXAMPLE_USER=$USER
fi

# Create rootfs.tar, this is usually done in a build system
rm -rf $TEMPDIR
mkdir $TEMPDIR
fakeroot <<EOF
set -e
cd $TEMPDIR
mkdir rootfs
mkdir -p rootfs/{root,dev,home/nobody}
echo data > rootfs/home/nobody/data
chown -R nobody:$(id -gn nobody) rootfs/home/nobody
mknod rootfs/dev/null c 1 3
dd if=/dev/urandom bs=1M count=16 of=rootfs/large_file
ln rootfs/large_file rootfs/large_file_link
tar -cf rootfs.tar -C rootfs .
EOF
rm -rf $TEMPDIR/rootfs

set -x
ls $TEMPDIR

# Invoke the example under fakeroot
fakeroot ./_rootfs-in-p2.py $TEMPDIR

rm -rf $TEMPDIR
