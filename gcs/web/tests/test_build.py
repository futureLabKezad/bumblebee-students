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

"""build_html.py and fetch_pyodide.py: the two pages, the policy of the embedded page, the
pinned Pyodide. Nothing is downloaded here."""
import base64
import hashlib
import io
import os
import re
import shutil
import sys
import tarfile
import tempfile
import unittest

WEB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WEB)
import build_html  # noqa: E402
import fetch_pyodide  # noqa: E402


def read(path, mode='r'):
    with open(path, mode, **({} if 'b' in mode else {'encoding': 'utf-8'})) as f:
        return f.read()


def tarball(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TempDirs(unittest.TestCase):
    def tmp(self):
        d = tempfile.mkdtemp(prefix='bbflight_test_')
        self.addCleanup(shutil.rmtree, d, True)
        return d


class Pages(TempDirs):
    def build(self, local_pyodide):
        d = self.tmp()
        if local_pyodide:
            os.makedirs(os.path.join(d, 'pyodide'))
            with open(os.path.join(d, 'pyodide', 'pyodide.js'), 'w'):
                pass
        build_html.build(d)
        return read(os.path.join(d, 'flight.html')), read(os.path.join(d, 'flight_embedded.html'))

    @staticmethod
    def policy(html):
        m = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', html)
        return m.group(1) if m else None

    def test_the_browser_page_has_no_policy_and_is_not_embedded(self):
        alone, embedded = self.build(False)
        self.assertIsNone(self.policy(alone))
        self.assertIn('"embedded": false', alone)
        self.assertIn('"embedded": true', embedded)

    def test_the_embedded_policy_allows_only_the_one_inline_script(self):
        _, embedded = self.build(False)
        policy = self.policy(embedded)
        scripts = build_html.INLINE_SCRIPT.findall(embedded)
        self.assertEqual(len(scripts), 1)
        digest = base64.b64encode(hashlib.sha256(scripts[0].encode('utf-8')).digest()).decode()
        rules = dict(part.strip().split(' ', 1) for part in policy.split(';'))
        self.assertEqual(rules['default-src'], "'none'")
        self.assertIn("'sha256-%s'" % digest, rules['script-src'])
        self.assertNotIn("'unsafe-inline'", rules['script-src'])
        self.assertNotIn("'unsafe-eval'", rules['script-src'])
        # the page and its worker reach the page's own files and one package of the CDN -- never the drone
        pyodide = 'https://cdn.jsdelivr.net/npm/pyodide@%s/' % fetch_pyodide.VERSION
        self.assertEqual(rules['connect-src'], "'self' " + pyodide)
        self.assertTrue(rules['script-src'].endswith(' ' + pyodide))
        self.assertEqual(rules['worker-src'], 'blob:')
        self.assertEqual(rules['form-action'], "'none'")
        self.assertEqual(rules['base-uri'], "'none'")
        self.assertEqual(rules['webrtc'], "'block'")
        self.assertNotIn('object-src', rules)            # default-src 'none' covers what is not listed

    def test_with_a_local_pyodide_no_outside_host_is_allowed(self):
        _, embedded = self.build(True)
        self.assertNotIn('https://', self.policy(embedded))
        self.assertIn('"pyodide": "pyodide/"', embedded)


class Pyodide(TempDirs):
    def test_the_page_and_the_fetcher_name_the_same_version(self):
        template = read(os.path.join(WEB, 'flight_template.html')) + build_html.studio_js()   # 1.4: the script is in studio/*.js
        self.assertEqual(re.findall(r'npm/pyodide@([0-9.]+)/', template), [fetch_pyodide.VERSION])
        self.assertIn('pyodide-%s.tgz' % fetch_pyodide.VERSION, fetch_pyodide.URL)

    def test_a_changed_tarball_is_refused(self):
        data = tarball({'package/pyodide.js': b'x'})
        with self.assertRaises(SystemExit):
            fetch_pyodide.verify(data)
        fetch_pyodide.verify(data, base64.b64encode(hashlib.sha512(data).digest()).decode())

    def test_only_the_wanted_files_are_unpacked_and_nothing_is_overwritten(self):
        files = {'package/' + name: name.encode() for name in fetch_pyodide.FILES}
        files.update({'package/pyodide.mjs': b'not needed', 'package/../evil.js': b'no', 'other/pyodide.js': b'no'})
        d = self.tmp()
        out = os.path.join(d, 'pyodide')
        sizes = fetch_pyodide.unpack(tarball(files), out)
        self.assertEqual(sorted(os.listdir(out)), sorted(fetch_pyodide.FILES))
        self.assertEqual(os.listdir(d), ['pyodide'])
        self.assertEqual(sizes['pyodide.js'], len('pyodide.js'))
        fetch_pyodide.unpack(tarball(files), out)               # the same again: nothing to do
        files['package/pyodide.js'] = b'another'
        with self.assertRaises(SystemExit):
            fetch_pyodide.unpack(tarball(files), out)
        self.assertEqual(read(os.path.join(out, 'pyodide.js'), 'rb'), b'pyodide.js')

    def test_the_kept_tarball_is_never_overwritten_by_another(self):
        d = self.tmp()
        path = os.path.join(d, 'sub', 'p.tgz')
        fetch_pyodide.keep(path, b'one')
        fetch_pyodide.keep(path, b'one')                    # the same again: nothing to do
        with self.assertRaises(SystemExit):
            fetch_pyodide.keep(path, b'two')
        self.assertEqual(read(path, 'rb'), b'one')

    def test_a_tarball_without_a_wanted_file_is_refused(self):
        d = self.tmp()
        with self.assertRaises(SystemExit):
            fetch_pyodide.unpack(tarball({'package/pyodide.js': b'x'}), os.path.join(d, 'pyodide'))
        self.assertEqual(os.listdir(d), [])


if __name__ == '__main__':
    unittest.main()
