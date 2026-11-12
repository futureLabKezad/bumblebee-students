#!/usr/bin/env python3
"""A7 test: executor/vision_c8.launch.py (ROS sourced; builds the LaunchDescription, starts nothing).
1) accepts exactly the A7 package candidate and returns 4 actions; 2) refuses another candidate path (the A6 one and a
combined_* path); 3) refuses when the detector differs from the manifest (temporary copy of the candidate in a temp
dir under this test's own tmp, never touching the real candidate); 4) the file differs from the shared
vision.launch.py only in the header and the location check; 5) refuses outside the isolated env.
Run: python3 -B a7_vision_launch.py"""
import difflib
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

D = Path('/work/c8_judge_r2h_a10_20261110')
F = D / 'executor/vision_c8.launch.py'
SHARED = Path('/work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py')


def load():
    spec = importlib.util.spec_from_file_location('vision_c8_under_test', F)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(root, env_ok=True):
    os.environ.update(ROS_LOCALHOST_ONLY='1' if env_ok else '0', ROS_DOMAIN_ID='83', GZ_PARTITION='bbtrial',
                      BB_COMBINED_ROOT=str(root))
    try:
        ld = load().generate_launch_description()
        return 'ok', len(ld.entities)
    except RuntimeError as e:
        return 'refused', str(e)


r = run(D / 'candidate')
assert r == ('ok', 4), r
for other in (Path('/work/c8_judge_r2e_a6_20261110/candidate'), Path('/work/c8_judge_r2e_a7_20261110/candidate'),  # A8: A7 refused too
               Path('/work/parallel_work/20261015/integration/combined_13')):
    r = run(other)
    assert r == ('refused', 'C8 package candidate required'), (other, r)
assert run(D / 'candidate', env_ok=False) == ('refused', 'Isolated SITL environment required')
# changed detector: the check must still compare the detector with the manifest (code path test on a patched copy)
src = F.read_text().replace("Path('/work/c8_judge_r2h_a10_20261110/candidate')", 'Path(os.environ["A7_TEST_ROOT"])')
with tempfile.TemporaryDirectory(dir=str(D / 'tests')) as td:
    cand = Path(td) / 'candidate'
    shutil.copytree(D / 'candidate', cand)
    with open(cand / 'vision/aruco_detect.py', 'a') as h:
        h.write('\n# changed\n')
    f2 = Path(td) / 'vision_patched.launch.py'
    f2.write_text(src)
    os.environ['A7_TEST_ROOT'] = str(cand)
    os.environ['ROS_LOCALHOST_ONLY'] = '1'   # restore the isolated env after the env-refusal case
    os.environ['BB_COMBINED_ROOT'] = str(cand)
    spec = importlib.util.spec_from_file_location('vision_patched', f2)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    try:
        m.generate_launch_description()
        sys.exit('FAIL: changed detector accepted')
    except RuntimeError as e:
        assert str(e) == 'Detector differs from reviewed copy', e
diff = [l for l in difflib.unified_diff(SHARED.read_text().splitlines(), F.read_text().splitlines(), lineterm='', n=0)
        if l.startswith(('+', '-')) and not l.startswith(('+++', '---'))]
removed = [l for l in diff if l.startswith('-')]
assert removed == ['-"""Ground camera chain for a separately frozen integration candidate."""',
                   "-    parent = Path('/work/parallel_work/20261015/integration')",
                   "-    if not root.is_relative_to(parent) or not root.name.startswith('combined_'):",
                   "-        raise RuntimeError('Separate integration candidate required')"], removed
added = [l for l in diff if l.startswith('+')]
# review SHOULD 1: also the added lines must be exactly the header (5 lines) and the 2-line location check
assert len(added) == 7, added
assert added[0].startswith('+"""Ground camera chain') and added[1] == '+' and added[2].startswith('+C8 A7 copy') \
    and added[3].startswith('+check differs') and added[4].startswith('+only .../integration'), added[:5]
assert added[5:] == ["+    if root != Path('/work/c8_judge_r2h_a10_20261110/candidate'):   # C8 A7: only this package's frozen candidate",
                     "+        raise RuntimeError('C8 package candidate required')"], added[5:]
print('ok: accepts the A7 candidate (4 actions), refuses others, env and a changed detector; diff = header + location check')
