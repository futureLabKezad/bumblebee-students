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

"""Fetch Pyodide (Python in the page) for the «Полёт» web module: gcs/web/dist/pyodide.

    python3 gcs/web/fetch_pyodide.py               # download, verify, unpack
    python3 gcs/web/fetch_pyodide.py pyodide.tgz   # a tarball that is already on the disk
    python3 gcs/web/fetch_pyodide.py --keep FILE   # also save the verified tarball as FILE

The npm package pyodide@VERSION -- the very files cdn.jsdelivr.net/npm/pyodide@VERSION/
serves -- is checked against the SHA-512 the npm registry publishes for it (pinned below),
and only the five files the page needs are unpacked. Then run build_html.py again: the
embedded page uses the local copy and its Content-Security-Policy allows no outside host.
"""
import base64
import hashlib
import io
import os
import sys
import tarfile
import urllib.request

VERSION = '0.26.4'
URL = 'https://registry.npmjs.org/pyodide/-/pyodide-%s.tgz' % VERSION
# "dist.integrity" of https://registry.npmjs.org/pyodide/0.26.4
SHA512_B64 = 'z2CHsjVlhhJi5tYBF0AYAfNEPo3zq/z+xOpFtk1tweJkRaTqU4UK/7pLvo8DBU2VDPH31vB3pSI+8fnoqrVrFg=='
FILES = ('pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json')
MAX_BYTES = 64 * 1024 * 1024        # the tarball, and each file in it

HERE = os.path.dirname(os.path.abspath(__file__))


def verify(data, sha512_b64=SHA512_B64):
    got = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != sha512_b64:
        raise SystemExit('this is not pyodide@%s as published on npm: sha512 %s' % (VERSION, got))


def unpack(data, out_dir, files=FILES):
    """Write the wanted files of the npm tarball (package/<name>) into out_dir.
    A file that exists and differs is not overwritten: move the old folder aside first."""
    found = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        for member in tar:
            name = member.name[len('package/'):] if member.name.startswith('package/') else None
            if name not in files:
                continue
            if not member.isfile() or member.size > MAX_BYTES:
                raise SystemExit('unexpected entry in the tarball: %s' % member.name)
            found[name] = tar.extractfile(member).read()
    missing = [name for name in files if name not in found]
    if missing:
        raise SystemExit('the tarball has no %s' % ', '.join(missing))
    todo = []
    for name in files:
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            todo.append((path, found[name]))
            continue
        with open(path, 'rb') as f:
            if f.read() != found[name]:
                raise SystemExit('%s exists and differs: move the old folder aside first' % path)
    os.makedirs(out_dir, exist_ok=True)
    for path, content in todo:
        with open(path, 'wb') as f:
            f.write(content)
    return {name: len(found[name]) for name in files}


def keep(path, data):
    """Save the verified tarball (for builds without a network). Never overwrites another file."""
    if os.path.exists(path):
        with open(path, 'rb') as f:
            if f.read() == data:
                return
        raise SystemExit('%s exists and differs: move it aside first' % path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def main(argv):
    args = list(argv[1:])
    keep_as = None
    if '--keep' in args:
        i = args.index('--keep')
        if i + 1 >= len(args):
            raise SystemExit('--keep needs a file name')
        keep_as = args[i + 1]
        del args[i:i + 2]
    if args:
        with open(args[0], 'rb') as f:
            data = f.read()
    else:
        print('downloading', URL)
        with urllib.request.urlopen(URL, timeout=60) as r:
            data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise SystemExit('the tarball is larger than expected')
    verify(data)
    if keep_as:
        keep(keep_as, data)
        print('kept the verified tarball:', keep_as, len(data), 'bytes')
    sizes = unpack(data, os.path.join(HERE, 'dist', 'pyodide'))
    for name, size in sizes.items():
        print('  %-20s %9d bytes' % (name, size))
    print('pyodide %s is in gcs/web/dist/pyodide; now run: python3 gcs/web/build_html.py' % VERSION)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
