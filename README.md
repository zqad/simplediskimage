How to use
==========
See `examples/` or https://simplediskimage.readthedocs.io/en/latest/

Available on PyPI (`pip install simplediskimage`) or
https://pypi.org/project/simplediskimage/

Dependencies
============

Debian/Ubuntu
-------------
```
# Common
$ sudo apt install python3-parted python3-distutils
# FAT support
$ sudo apt install dosfstools mtools
# ext* support
$ sudo apt install e2fsprogs
# All
$ sudo apt install python3-parted python3-distutils dosfstools mtools e2fsprogs
```

Fedora/CentOS
-------------
```
# Common
$ sudo dnf install python3-pyparted
# FAT support
$ sudo dnf install dosfstools mtools
# ext* support
$ sudo dnf install e2fsprogs
# All
$ sudo dnf install python3-pyparted dosfstools mtools e2fsprogs
```


Known issues
============
`mtools` and `debugfs` is not good at error reporting, so if a copy fails it
might not show until you try to mount the image.

Parted misbehaves on some platforms (Debian 10), and shrinks partitions. Use
Sfdisk instead. Additionally, some FAT implementations expect the filesystem
to have exactly the same size as the partition, and thus padding them will not
work, unless done exactly.

`copy_file_range` seems to misbehave in containers sometimes, observed on
Fedora 30 + podman with Debian 10 container where it skips to copy some data.

Future ideas
============
- Configurable alignment, defaulting to 1MiB
- Proper naive `copy_file_range` function, using `dup()`
- Automated tests
- GPT for sfdisk partitioner (and set it as the default)
- sgdisk support?
- Multiboot images (iso, efi, bios)
- MTD-type partitions: Only offsets and a possibility to get a mtdparts=-type
  string
