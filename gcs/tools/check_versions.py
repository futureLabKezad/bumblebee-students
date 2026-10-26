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

"""Check that every copy of the GCS version agrees with gcs/VERSION.

The version lives in four files the builds read, plus the release tag:

    gcs/VERSION                                    1.2.0   <- change this first
    gcs/macos/Info.plist  CFBundleShortVersionString  1.2.0
    gcs/windows/src/BumblebeeGcs/BumblebeeGcs.csproj  <Version> 1.2.0
    gcs/windows/src/BumblebeeGcs/app.manifest      assemblyIdentity 1.2.0.0
    git tag                                        gcs-v1.2.0

    python3 gcs/tools/check_versions.py                 # files only
    python3 gcs/tools/check_versions.py --tag gcs-v1.2.0
"""
import argparse
import os
import plistlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SEMVER = re.compile(r'^\d+\.\d+\.\d+$')


def read_versions(root):
    gcs = os.path.join(root, 'gcs')
    found = {}
    with open(os.path.join(gcs, 'VERSION'), encoding='utf-8') as f:
        found['gcs/VERSION'] = f.read().strip()
    with open(os.path.join(gcs, 'macos', 'Info.plist'), 'rb') as f:
        found['Info.plist CFBundleShortVersionString'] = plistlib.load(f).get('CFBundleShortVersionString', '')
    proj = ET.parse(os.path.join(gcs, 'windows', 'src', 'BumblebeeGcs', 'BumblebeeGcs.csproj')).getroot()
    found['BumblebeeGcs.csproj <Version>'] = next((e.text or '').strip() for e in proj.iter('Version'))
    man = ET.parse(os.path.join(gcs, 'windows', 'src', 'BumblebeeGcs', 'app.manifest')).getroot()
    ident = next(e for e in man.iter() if e.tag.endswith('assemblyIdentity'))
    four = ident.get('version', '')
    found['app.manifest assemblyIdentity'] = four[:-2] if four.endswith('.0') and four.count('.') == 3 else four
    return found


def check(root, tag=None):
    found = read_versions(root)
    want = found['gcs/VERSION']
    problems = []
    if not SEMVER.match(want):
        problems.append('gcs/VERSION is "%s", expected X.Y.Z' % want)
    for where, value in found.items():
        if value != want:
            problems.append('%s is "%s", gcs/VERSION is "%s"' % (where, value, want))
    if tag is not None and tag != 'gcs-v' + want:
        problems.append('tag %s does not match gcs/VERSION %s (expected gcs-v%s)' % (tag, want, want))
    return want, problems


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--tag', help='release tag to check, e.g. gcs-v1.2.0')
    p.add_argument('--root', default=ROOT)
    a = p.parse_args(argv)
    want, problems = check(a.root, a.tag)
    for line in problems:
        print('check_versions: ' + line)
    print('check_versions: %s, %d problems' % (want, len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
