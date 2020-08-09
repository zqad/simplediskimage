.. Simple Disk Image documentation master file, created by
   sphinx-quickstart on Mon Apr  6 17:35:26 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Simple Disk Image Creation
==========================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   self
   examples
   modules/main
   modules/submodules


Introduction
============

When preparing installer images or root filesystems images for embedded
devices, the classic way is to create a file, `losetup` it, partition it, run
`mkfs`, mount it and copy data into it, unmount it, remember to remove the
loopback device, etc. Mostly requiring root privileges and the `CAP_SYSADM`
capability.

There are however tools to do most operations in user space, as long as you are
willing to do some copying, as the tools do not handle offsets into files that
well. It is however and error-prone operation, and out of those that do it by
hand: How many never remembers how many LBAs into the disk that the GPT
streches, and even when looking it up forgets to account for the extra LBA left
for MBR and DOS label compatibility, or the extra GPT at the end of the disk?
My estimate is most, since I tend to.

For the most times, you just need to set up a simple disk image with one or two
partitions, typically just with FAT and/or ext. This library aims to
simplify that task by removing some of the complex choices.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
