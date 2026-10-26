#!/usr/bin/env python3
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for check_versions.py.

    python3 gcs/tools/test_check_versions.py
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_versions as cv  # noqa: E402

FILES = ['gcs/VERSION', 'gcs/macos/Info.plist',
         'gcs/windows/src/BumblebeeGcs/BumblebeeGcs.csproj', 'gcs/windows/src/BumblebeeGcs/app.manifest']


class Versions(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for rel in FILES:
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)), exist_ok=True)
            shutil.copy(os.path.join(cv.ROOT, rel), os.path.join(self.root, rel))
        self.version = cv.read_versions(cv.ROOT)['gcs/VERSION']

    def tearDown(self):
        shutil.rmtree(self.root)

    def edit(self, rel, old, new):
        p = os.path.join(self.root, rel)
        with open(p, encoding='utf-8') as f:
            s = f.read()
        self.assertIn(old, s)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(s.replace(old, new, 1))

    def test_repo_agrees(self):
        self.assertEqual(cv.check(cv.ROOT)[1], [])

    def test_matching_tag(self):
        self.assertEqual(cv.check(self.root, 'gcs-v' + self.version)[1], [])

    def test_wrong_tag(self):
        self.assertTrue(cv.check(self.root, 'gcs-v9.9.9')[1])

    def test_each_file_is_checked(self):
        for rel, old, new in [
            ('gcs/macos/Info.plist', '<string>%s</string>' % self.version, '<string>9.9.9</string>'),
            ('gcs/windows/src/BumblebeeGcs/BumblebeeGcs.csproj', '<Version>%s</Version>' % self.version, '<Version>9.9.9</Version>'),
            ('gcs/windows/src/BumblebeeGcs/app.manifest', 'version="%s.0"' % self.version, 'version="1.0.0.0"'),
        ]:
            with self.subTest(rel):
                self.tearDown()
                self.setUp()
                self.edit(rel, old, new)
                self.assertTrue(cv.check(self.root)[1], rel)

    def test_bad_version_format(self):
        with open(os.path.join(self.root, 'gcs/VERSION'), 'w') as f:
            f.write('1.2\n')
        self.assertTrue(cv.check(self.root)[1])


if __name__ == '__main__':
    unittest.main()
