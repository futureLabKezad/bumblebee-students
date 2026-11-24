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

"""check_watch_only.py and the «Полёт» part: the six mission paths, the web module (gcs/web).

    python3 gcs/tools/test_check_watch_only_web.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_watch_only as cw  # noqa: E402

TEMPLATE = os.path.join(cw.ROOT, 'gcs', 'web', 'flight_template.html')
SIX = ('/api/map', '/api/map/status', '/api/mission/check', '/api/mission/start',
       '/api/mission/stop', '/api/mission/status')


def problems(text, name='flight_template.html'):
    return cw.check_text(name, text)


class MissionPaths(unittest.TestCase):
    def test_the_six_paths_pass_in_swift_cs_and_js(self):
        for p in SIX:
            self.assertEqual(problems('try await ok("POST", "%s")' % p, 'A.swift'), [], p)
            self.assertEqual(problems('SendAsync(HttpMethod.Post, "%s", body)' % p, 'A.cs'), [], p)
            self.assertEqual(problems('await fetch(url + \'%s\', {method: "POST"});' % p, 'a.js'), [], p)

    def test_other_paths_still_fail(self):
        self.assertTrue(problems('try await ok("POST", "/api/mission/launch")', 'A.swift'))
        self.assertTrue(problems("fetch(url + '/api/fcu/arm')", 'a.js'))
        self.assertTrue(problems("fetch(url + '/api/map/' + id)", 'a.js'))           # built at run time
        self.assertTrue(problems('fetch(`/api/mission/${what}`)', 'a.js'))
        # a path is seen anywhere in a literal, not only at its start (review 18.11, m15)
        self.assertTrue(problems('fetch(`${url}/api/fcu/arm`)', 'a.js'))
        self.assertTrue(problems("fetch('http://h:8766/api/fcu/arm')", 'a.js'))
        self.assertTrue(problems('await http.GetAsync("http://" + host + ":8766/api/fcu/arm");', 'A.cs'))
        self.assertTrue(problems('fetch(`${url}/api/mission/${what}`)', 'a.js'))
        self.assertEqual(problems("fetch('http://h:8766/api/mission/stop')", 'a.js'), [])

    def test_only_the_web_modules_own_dist_folder_is_skipped(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            for rel in ('gcs/windows/src/dist/X.cs', 'gcs/web/dist/flight.js', 'gcs/web/a.js', 'gcs/web/sub/dist/b.js',
                        'gcs/macos/Sources/dist/Y.swift', 'gcs/windows/src/obj/Z.cs'):
                path = os.path.join(root, *rel.split('/'))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    f.write('')
            seen = sorted(os.path.relpath(p, root).replace(os.sep, '/') for p in cw.source_files(root))
        self.assertEqual(seen, ['gcs/macos/Sources/dist/Y.swift', 'gcs/web/a.js', 'gcs/web/sub/dist/b.js',
                                'gcs/windows/src/dist/X.cs'])


class WebModule(unittest.TestCase):
    def test_flight_template_passes_and_names_only_the_six(self):
        with open(TEMPLATE, encoding='utf-8') as f:
            text = f.read()
        # 1.4 (Flight studio): the page script lives in gcs/web/studio/*.js; the check covers all of it
        studio = os.path.join(os.path.dirname(TEMPLATE), 'studio')
        for name in sorted(os.listdir(studio)):
            if name.endswith('.js'):
                with open(os.path.join(studio, name), encoding='utf-8') as f:
                    js = f.read()
                self.assertEqual(problems(js, name), [], name)
                text += '\n' + js
        self.assertEqual(problems(text), [])
        found = {m.group(1) for m in cw.API_LITERAL_JS.finditer(text)}
        self.assertEqual(found, set(SIX))

    def test_js_violations_are_found(self):
        for line in ["ros.send({ op: 'call_service', service: '/mavros/cmd/arming' })",
                     "const t = '/mavros/setpoint_position/local';",
                     "ws.send(JSON.stringify({op: 'publish', topic: '/x'}))",
                     "ws.send(JSON.stringify({'op': 'publish', topic: '/x'}))",
                     "m.op = 'publish';",
                     "callService('/navigate', args)",
                     "const s = '/mavros/mavros/arming';",
                     "fetch('http://drone:14550')"]:
            self.assertTrue(problems(line, 'a.js'), line)

    def test_js_comment_after_url_string_is_not_code(self):
        self.assertEqual(problems("const u = 'http://127.0.0.1:8766'; // /mavros/cmd/arming is never called", 'a.js'), [])

    def test_a_path_cannot_hide_behind_what_only_looks_like_a_comment(self):
        # review 2 (18.11), N9: a quote inside a regex, a char literal, "/*" inside a regex
        for line, name in (("const r = /'/; fetch('http://h:8766/api/fcu/arm')", 'a.js'),
                           ("/* it's */ fetch('http://h:8766/api/fcu/arm')", 'a.js'),
                           ('var c = \'"\'; var u = "http://h:8766/api/fcu/arm";', 'A.cs')):
            self.assertTrue(problems(line, name), line)
        hidden = "const re = /^\\/*api/;\nfetch(u + '/api/fcu/arm')\n"
        self.assertTrue(problems(hidden, 'a.js'))
        # a wildcard in prose is not a request
        self.assertEqual(problems("/// HTTP client for the drone's `/api/*` endpoints", 'A.swift'), [])
        self.assertEqual(problems('/// `/api/wifi/*` backend', 'A.swift'), [])
        # ...but a path spelled out in a comment must be an allowed one
        self.assertTrue(problems('// later: POST /api/fcu/arm', 'A.cs'))
        self.assertEqual(problems('// POST /api/map waits up to 3 s', 'A.cs'), [])

    def test_every_page_and_script_is_scanned_except_the_built_ones(self):
        # the built pages (gcs/web/dist) embed the Python sources, which name forbidden functions
        # to refuse them: that folder is skipped, see the test below
        for name in ('flight_template.html', 'tool.mjs', 'x.ts', 'a.js', 'A.cs', 'A.swift'):
            self.assertTrue(name.endswith(cw.EXTENSIONS), name)

    def test_whole_tree_with_the_web_module_and_the_flight_section_passes(self):
        self.assertEqual(cw.main(['check', cw.ROOT]), 0)


if __name__ == '__main__':
    unittest.main()
