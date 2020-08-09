# Copyright 2019, 2020  Jonas Eriksson
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

from distutils.dir_util import mkpath
import os

def generate_bb_testdata():
    """
    Generate beaglebone-inspired test data to `./generated`
    """
    mkpath("generated")
    for filename, iterations in [("u-boot.img", 119078), ("MLO", 40334)]:
        path = os.path.join("generated", filename)
        if os.path.exists(path):
            continue
        with open(path, 'wb') as f:
            data = filename.encode('ascii')
            for _ in range(0, iterations):
                f.write(data)
