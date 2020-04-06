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
Tool helpers; used to run commands for the simple disk image package
"""

import os
import re
import subprocess
import tempfile
import logging
import distutils.spawn

from .common import logger, DiskImageException

class ToolNotFound(DiskImageException):
    """
    The tool requested was not found (check $PATH and install all
    dependencies).
    """

class DoubleQuoteInExtFile(DiskImageException):
    """
    debugfs does not cope well with double quotes in file names, which was
    detected.
    """

class Tool():
    """
    Wrapper class for a runnable tool (command).

    :param command: Command to be run, e.g. `ls`.
    """
    def __init__(self, command):
        self._command = command
        self._command_path = None

    def check(self):
        """
        Check if the tool is available, i.e. in $path and executable.
        """
        if self._command_path is not None:
            return True
        self._command_path = distutils.spawn.find_executable(self._command)
        if self._command_path is None:
            logger.error("Unable to find %s", self._command)
        else:
            logger.debug("Found %s at %s", self._command, self._command_path)
        return self._command_path is not None

    def call(self, *args, **kwargs):
        """
        Call the tool with the given arguments, and debug-log the output

        :param args: Command-line arguments
        :param kwargs: Keyword arguments to pass to subprocess.check_output
        """
        if not self.check():
            raise ToolNotFound("Unable to find executable "
                               "{}".format(self._command))
        call_args = [self._command_path]
        call_args.extend(args)
        logger.debug("Running: '%s'", "' '".join(call_args))
        output = subprocess.check_output(call_args, stderr=subprocess.STDOUT,
                                         **kwargs)
        logger.debug("Output:\n%s", output.decode('utf-8', errors='ignore'))


class MkfsExt(Tool):
    """
    Tool wrapper for mkfs.ext*
    """
    def mkfs(self, device, label=None):
        """
        Create file system

        :param device: Device, typically a file in our use case
        :param label: File system label
        """
        args = []
        if label is not None:
            args.append('-L')
            args.append(label)
        args.append(device)
        self.call(*args)

class MkfsExt2(MkfsExt):
    """
    Tool wrapper for mkfs.ext2
    """
    def __init__(self):
        super(MkfsExt2, self).__init__('mkfs.ext2')

class MkfsExt3(MkfsExt):
    """
    Tool wrapper for mkfs.ext3
    """
    def __init__(self):
        super(MkfsExt3, self).__init__('mkfs.ext3')

class MkfsExt4(MkfsExt):
    """
    Tool wrapper for mkfs.ext4
    """
    def __init__(self):
        super(MkfsExt4, self).__init__('mkfs.ext4')

class MkfsFAT(Tool):
    """
    Tool wrapper for mkfs.fat
    """
    def __init__(self, fat_size):
        self._fat_size = str(fat_size)
        super(MkfsFAT, self).__init__('mkfs.fat')

    def mkfs(self, device, label=None):
        """
        Create file system

        :param device: Device, typically a file in our use case
        :param label: File system label
        """
        args = ['-F', self._fat_size]
        if label is not None:
            args.append('-n')
            args.append(label)
        args.append(device)
        self.call(*args)

class MkfsFAT12(MkfsFAT):
    """
    Tool wrapper for mkfs.fat -F 12
    """
    def __init__(self):
        super(MkfsFAT12, self).__init__(12)

class MkfsFAT16(MkfsFAT):
    """
    Tool wrapper for mkfs.fat -F 16
    """
    def __init__(self):
        super(MkfsFAT16, self).__init__(16)

class MkfsFAT32(MkfsFAT):
    """
    Tool wrapper for mkfs.fat -F 32
    """
    def __init__(self):
        super(MkfsFAT32, self).__init__(32)

def _dq_check(filename):
    if '"' in filename:
        raise DoubleQuoteInExtFile("The filename {} contains double quotes "
                                   "which are not supported by the Ext file "
                                   "system tools".format(filename))

def _ext_cmds_mkdir(directories):
    cmds = []
    for directory in directories:
        # Make directory path absolute and remove multiple slashes
        directory = re.sub(r'/+', '/', '/' + directory)
        _dq_check(directory)
        cmds.append('mkdir "{}"'.format(directory))
    return cmds

def _ext_cmds_write(sources, destination):
    # Quick exit if sources are empty
    if not sources:
        return []

    cmds = []
    # Make all cd:s absolute, and clean out multiple slashes as those will
    # break debugfs
    destination = re.sub(r'/+', '/', '/' + destination)
    _dq_check(destination)
    cmds.append('cd "{}"'.format(destination))
    for source in sources:
        file_name = os.path.basename(source)
        _dq_check(file_name)
        cmds.append('write "{}" "{}"'.format(source, file_name))
    return cmds

class PopulateExt(Tool):
    """
    Tool wrapper for debugfs
    """
    def __init__(self):
        super(PopulateExt, self).__init__('debugfs')

    def run(self, device, actions):
        """
        Perform the requested actions using the tool.

        :param device: Device to perfom the actions on
        :param actions: Actions to perform
        """
        commands = []
        for action_tuple in actions:
            action = list(action_tuple)
            verb = action.pop(0)
            if verb == 'mkdir':
                dirs = action[0]
                commands.extend(_ext_cmds_mkdir(dirs))
            elif verb == 'copy':
                sources = action[0]
                destination = action[1]
                commands.extend(_ext_cmds_write(sources, destination))
            elif verb == 'copy recursive':
                sources = action[0]
                destination = action[1]
                for src in sources:
                    base_path = os.path.join(destination,
                                             os.path.basename(src))
                    if os.path.isdir(src):
                        commands.extend(_ext_cmds_mkdir([base_path]))
                    for parent, _dirs, _files in os.walk(src):
                        current_dest = "{}/{}".format(base_path,
                                                      parent[len(src):])
                        dirs = [os.path.join(current_dest, _dir) for _dir in _dirs]
                        commands.extend(_ext_cmds_mkdir(dirs))
                        files = [os.path.join(parent, _files)
                                 for _files in _files]
                        commands.extend(_ext_cmds_write(files, current_dest))

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Compiled a debugfs script:")
            for command in commands:
                logger.debug("    %s", command)

        _fd, commands_file = tempfile.mkstemp()
        with open(commands_file, 'w') as handle:
            handle.write("\n".join(commands))
        self.call('-w', '-f', commands_file, device)
        os.unlink(commands_file)

def _fat_format_dest(path):
    if path[0] == '/':
        path = path[1:]
    return '::' + path

class Sfdisk(Tool):
    """
    Tool wrapper for sfdisk
    """
    def __init__(self):
        super(Sfdisk, self).__init__('sfdisk')

class PopulateFAT():
    """
    tool wrapper for mtools
    """
    def __init__(self):
        self._mcopy = Tool('mcopy')
        self._mmd = Tool('mmd')

    def check(self):
        """
        Check that both wrapped tools are available
        """
        return self._mcopy.check() and self._mmd.check()

    def run(self, device, actions):
        """
        Perform the requested actions using the tool.

        :param device: Device to perfom the actions on
        :param actions: Actions to perform
        """
        for action_tuple in actions:
            action = list(action_tuple)
            verb = action.pop(0)
            if verb == 'mkdir':
                dirs = [_fat_format_dest(p) for p in action[0]]
                self._mmd.call('-i', device, *dirs)
            elif verb == 'copy':
                sources = action[0]
                destination = _fat_format_dest(action[1])
                self._mcopy.call('-i', device, '-bQ', *sources, destination)
            elif verb == 'copy recursive':
                sources = action[0]
                destination = _fat_format_dest(action[1])
                self._mcopy.call('-i', device, '-bsQ', *sources, destination)

# pylint: disable=bad-whitespace
_TOOLS = {
    ('ext2',    'mkfs'):        MkfsExt2,
    ('ext3',    'mkfs'):        MkfsExt3,
    ('ext4',    'mkfs'):        MkfsExt4,
    ('fat12',   'mkfs'):        MkfsFAT12,
    ('fat16',   'mkfs'):        MkfsFAT16,
    ('fat32',   'mkfs'):        MkfsFAT32,
    ('ext2',    'populate'):    PopulateExt,
    ('ext3',    'populate'):    PopulateExt,
    ('ext4',    'populate'):    PopulateExt,
    ('fat12',   'populate'):    PopulateFAT,
    ('fat16',   'populate'):    PopulateFAT,
    ('fat32',   'populate'):    PopulateFAT,
    ('none',    'sfdisk'):      Sfdisk,
}

_TOOLS_CACHE = {}

def get_tool(file_system, action):
    """
    Get a tool to perform a certain action on a certain file system type.

    :param file_system: File system, e.g. "fat16"
    :param action: Action, e.g. "mkfs" or "populate"
    """
    tool_tuple = (file_system, action)
    if tool_tuple not in _TOOLS_CACHE:
        if tool_tuple not in _TOOLS:
            raise ToolNotFound("Unable to find tool {} "
                               "for {}".format(action, file_system))
        _TOOLS_CACHE[tool_tuple] = _TOOLS[tool_tuple]()

    return _TOOLS_CACHE[tool_tuple]
