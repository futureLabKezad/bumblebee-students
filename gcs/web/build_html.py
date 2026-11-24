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

"""Build the «Полёт» (Flight) web module into gcs/web/dist.

    python3 gcs/web/build_html.py

dist/flight.html           for a browser: talks to the drone's mission server itself (fetch)
dist/flight_embedded.html  for the GCS apps (WebView2, later WKWebView): a strict
                           Content-Security-Policy and no network to the drone at all --
                           the page only sends messages to the app, which talks to the drone

Pyodide (Python in the page) comes from cdn.jsdelivr.net unless dist/pyodide/pyodide.js
exists (python3 gcs/web/fetch_pyodide.py): then the embedded page uses the local copy and
its CSP allows no outside host. The Windows app copies the whole dist folder next to the exe.
"""
import base64
import glob
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_pyodide  # noqa: E402
from bbflight import apidoc, bbmap, codecheck  # noqa: E402

# Only this one package of the CDN, not the whole host (any npm package and GitHub repo lives there).
CDN = 'https://cdn.jsdelivr.net/npm/pyodide@%s/' % fetch_pyodide.VERSION
EXAMPLES = ('flight_marker_student.py', 'flight_marker_loop_student.py', 'corner_18_student.py')
INLINE_SCRIPT = re.compile(r'<script>(.*?)</script>', re.S)      # the executable one: no attributes


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def js_json(obj):
    return json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')


def csp(html, local_pyodide):
    """The policy of the embedded page. Hashes instead of 'unsafe-inline' for scripts;
    connect-src without the drone: fetch and WebSocket from the page AND from its blob
    worker (it inherits this policy) cannot reach the drone, rosbridge or MAVLink."""
    hashes = ["'sha256-%s'" % base64.b64encode(hashlib.sha256(m.group(1).encode('utf-8')).digest()).decode()
              for m in INLINE_SCRIPT.finditer(html)]
    outside = '' if local_pyodide else ' ' + CDN
    return '; '.join([
        "default-src 'none'",
        "script-src 'self' blob: 'wasm-unsafe-eval' %s%s" % (' '.join(hashes), outside),
        "worker-src blob:",
        "connect-src 'self'%s" % outside,
        "style-src 'unsafe-inline'",
        "img-src data: blob:",
        "base-uri 'none'",
        "form-action 'none'",
        "webrtc 'block'",                 # no peer connections either (a browser that does not know it ignores it)
    ])


def studio_js():
    """The page script: gcs/web/studio/*.js in name order (Flight studio 1.4). One inline script,
    so the embedded page keeps a single hash in its policy."""
    parts = []
    for p in sorted(glob.glob(os.path.join(HERE, 'studio', '*.js'))):
        text = read(p)
        if re.search(r'</script|<!--', text, re.I):
            raise SystemExit('%s: "</script" or "<!--" would break the inline <script>' % os.path.basename(p))
        parts.append('// ===== %s =====\n%s' % (os.path.basename(p), text))
    if not parts:
        raise SystemExit('no gcs/web/studio/*.js files')
    return '\n'.join(parts)


def build(out_dir=None):
    out_dir = out_dir or os.path.join(HERE, 'dist')
    os.makedirs(out_dir, exist_ok=True)
    py = {}
    for p in sorted(glob.glob(os.path.join(HERE, 'bbflight', '*.py'))):
        py['bbflight/' + os.path.basename(p)] = read(p)
    py['_api'] = ', '.join(sorted(codecheck.STUDENT_API))
    examples = {name: read(os.path.join(HERE, 'examples', name)) for name in EXAMPLES}
    mp = bbmap.from_map_txt(read(os.path.join(HERE, 'testdata', 'map_final.txt')), name='field_real')
    template = read(os.path.join(HERE, 'flight_template.html'))
    docs = {'commands': apidoc.docs(), 'groups': apidoc.GROUPS, 'words': apidoc.PY_WORDS}
    local_pyodide = os.path.exists(os.path.join(out_dir, 'pyodide', 'pyodide.js'))
    written = []
    for name, config in (('flight.html', {'embedded': False, 'pyodide': ''}),
                         ('flight_embedded.html', {'embedded': True, 'pyodide': 'pyodide/' if local_pyodide else ''})):
        html = template
        for key, val in (('/*__STUDIO_JS__*/', studio_js()), ('/*__API_DOCS__*/', js_json(docs)),
                         ('/*__PY_FILES__*/', js_json(py)), ('/*__EXAMPLES__*/', js_json(examples)),
                         ('/*__DEFAULT_MAP__*/', js_json(json.loads(bbmap.to_json(mp)))), ('/*__CONFIG__*/', js_json(config))):
            if html.count(key) != 1:
                raise SystemExit('placeholder %s must be in the template exactly once' % key)
            html = html.replace(key, val)
        if config['embedded']:
            if len(INLINE_SCRIPT.findall(html)) != 1:
                raise SystemExit('the embedded page must have exactly one inline <script>')
            meta = '<meta http-equiv="Content-Security-Policy" content="%s">' % csp(html, local_pyodide)
            if html.count('<meta charset="utf-8">') != 1:
                raise SystemExit('<meta charset="utf-8"> must be in the template exactly once')
            html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + meta)
        out = os.path.join(out_dir, name)
        with open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(html)
        written.append((out, len(html)))
    return written, local_pyodide


if __name__ == '__main__':
    files, local = build(sys.argv[1] if len(sys.argv) > 1 else None)
    for path, size in files:
        print('wrote', path, size, 'bytes')
    print('Pyodide:', 'local copy (dist/pyodide), the embedded page needs no internet' if local
          else 'from %s (the embedded page needs internet; run fetch_pyodide.py for an offline copy)' % CDN)
    if not local:
        template = read(os.path.join(HERE, 'flight_template.html')) + studio_js()
        if template.count("'%s'" % CDN) != 1:
            raise SystemExit('the template must load Pyodide from %s (the address its policy allows)' % CDN)
