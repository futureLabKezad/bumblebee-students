#!/usr/bin/env bash
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

# setup_venv.sh [VENV] - Python environment for the trial (PX4 v1.16.1 build
# dependencies + pymavlink), every package pinned by version and sha256.
# Default VENV: $VENV or ~/.venvs/bb-sim-trial. No root needed.
#
# --system-site-packages: the Gazebo Python bindings (python3-gz-transport13,
# python3-gz-msgs10 and their python3-protobuf) come from apt, not pip.
# --ignore-installed: every pinned package lands in the venv itself, even if
# apt happens to have the same one system-wide.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${1:-${VENV:-$HOME/.venvs/bb-sim-trial}}"
PIP_FLAGS=(--disable-pip-version-check --no-input --require-hashes --ignore-installed)

[ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install "${PIP_FLAGS[@]}" --no-deps -r "$HERE/requirements-bootstrap.txt"
"$VENV/bin/python" -m pip install "${PIP_FLAGS[@]}" --no-build-isolation -r "$HERE/requirements.txt"

# Everything the build and the trial scripts import must resolve.
"$VENV/bin/python" - <<'EOF'
import importlib, sys
mods = ["em", "jinja2", "yaml", "jsonschema", "kconfiglib", "genmsg", "packaging",
        "toml", "lxml", "pymavlink", "gz.transport13", "gz.msgs10"]
bad = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:  # report all at once
        bad.append(f"{m}: {e}")
print("python", sys.version.split()[0], "-", "all imports OK" if not bad else "MISSING:")
for b in bad:
    print("  ", b)
sys.exit(1 if bad else 0)
EOF
echo "venv ready: $VENV"
