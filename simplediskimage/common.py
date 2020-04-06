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
Common parts shared between the simple disk image modules
"""
import logging

# pylint: disable=invalid-name
logger = logging.getLogger("simplediskimage")

class DiskImageException(Exception):
    """
    A generic DiskImage error
    """

class InvalidArguments(DiskImageException):
    """
    Invalid arguments was passed
    """

class CheckFailed(DiskImageException):
    """
    A check has failed
    """

class UnknownError(DiskImageException):
    """
    Unknown error, probably related to an underlying library
    """

# pylint: disable=too-few-public-methods
class SI:
    """
    Helper class with some constants for calculating sizes in bytes.
    """
    k = 1000**1
    M = 1000**2
    G = 1000**3
    T = 1000**4
    ki = 1024**1
    Mi = 1024**2
    Gi = 1024**3
    Ti = 1024**4
