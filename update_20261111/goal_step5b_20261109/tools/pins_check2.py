#!/usr/bin/env python3
"""pins_check2.py - goal step 5b (Claude, 09.11.2026). Reads files only. C1 evidence for one scenario run.

Copy of /work/goal_step5_20261106/tools/pins_check.py (unchanged logic) with ONE addition: SCRIPT may also be an
absolute path of a NEW scenario script (e.g. /work/goal_step5b_20261109/scenarios/hover_marker0.py). Such a script
is not part of the image: it is listed with its sha256 and status 'NEW (not in image)' and is not counted as a
difference of the image. Everything else (manifest, rows, statuses) is as in pins_check.py.
Usage: python3 -I pins_check2.py RUN_DIR SCRIPT   (SCRIPT = examples/flight/flight.py ... or /abs/path/new.py)
"""
import hashlib
import json
import os
import sys

MANIFEST = '/work/goal_20261106/image_manifest.tsv'
PRODUCT = '/work/ws_package1b_port_03'
REPO_PKG = 'drone/ros2_ws/src/bumblebee/'


def sha(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    run_dir, script = sys.argv[1:3]
    a = sys.argv
    global MANIFEST
    MANIFEST = a[a.index('--manifest') + 1] if '--manifest' in a else MANIFEST   # r2b (09.11)
    SRC = a[a.index('--src') + 1] if '--src' in a else os.path.join(PRODUCT, 'src/bumblebee')
    INST = a[a.index('--install') + 1] if '--install' in a else os.path.join(PRODUCT, 'install')
    man = {}
    for line in open(MANIFEST, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        path, on_drone, fixed, source, change = line.rstrip('\n').split('\t')
        man[path] = (on_drone, fixed, change)
    new_script = os.path.isabs(script)
    used_src = ['examples/drone.py', 'examples/flight_profile.py'] + ([] if new_script else [script]) + [
                'src/python/aruco_detect.py', 'src/python/camera_fix.py', 'src/python/vpe_fix.py',
                'src/python/setpoint_freshness.py', 'src/cpp/simple_offboard.cpp',
                'launch/mavros_scoped_config.py', 'launch/bumblebee.launch.py', 'launch/aruco.launch.py']
    rows = []
    if new_script:
        rows.append({'file': script, 'sim_path': script, 'sha_sim': sha(script), 'sha_fixed_image': None,
                     'status': 'NEW (not in image)', 'manifest_note': 'new scenario script, not part of the image'})
    for rel in used_src:
        p = os.path.join(SRC, rel)
        s = sha(p)
        on_drone, fixed, change = man.get(REPO_PKG + rel, (None, None, 'not in manifest'))
        rows.append({'file': rel, 'sim_path': p, 'sha_sim': s, 'sha_fixed_image': fixed, 'sha_on_drone': on_drone,
                     'status': 'same' if s == fixed else ('NOT IN MANIFEST' if fixed is None else 'DIFFERS'),
                     'manifest_note': change})
    for name in ('aruco_detect.py', 'camera_fix.py', 'vpe_fix.py', 'setpoint_freshness.py'):
        inst = os.path.join(INST, 'bumblebee/lib/bumblebee', name)
        src = os.path.join(SRC, 'src/python', name)
        rows.append({'file': 'install/lib/bumblebee/' + name, 'sim_path': inst, 'sha_sim': sha(inst),
                     'sha_fixed_image': sha(src), 'status': 'same' if sha(inst) == sha(src) else 'DIFFERS',
                     'manifest_note': 'installed copy vs its source'})
    mp = '/work/sim/worlds/aruco_map/map.input.txt'
    on_drone, fixed, change = man.get('drone/ros2_ws/src/aruco_pose/map/map.txt', (None, None, ''))
    rows.append({'file': 'aruco_pose/map/map.txt', 'sim_path': mp, 'sha_sim': sha(mp), 'sha_fixed_image': fixed,
                 'status': 'same' if sha(mp) == fixed else 'DIFFERS', 'manifest_note': change})
    for label, p in (('simple_offboard binary (PC build of the same source)',
                      os.path.join(INST, 'bumblebee/lib/bumblebee/simple_offboard')),
                     ('mavros_node binary (bp02 PC build)', '/work/ws_mavros214_bp02_rel/install/mavros/lib/mavros/mavros_node')):
        rows.append({'file': label, 'sim_path': p, 'sha_sim': sha(p), 'sha_fixed_image': None, 'status': 'recorded',
                     'manifest_note': 'binary for x86; compare by source'})
    out = {'manifest': MANIFEST, 'manifest_sha256': sha(MANIFEST), 'product': PRODUCT, 'src': SRC, 'install': INST, 'rows': rows,
           'differs': [r['file'] for r in rows if r['status'] in ('DIFFERS', 'NOT IN MANIFEST')],
           'new_scripts': [r['file'] for r in rows if r['status'] == 'NEW (not in image)']}
    with open(os.path.join(run_dir, 'pins.json'), 'x', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    print(f"pins: {sum(r['status'] == 'same' for r in rows)} same, differs: {out['differs']}, new: {out['new_scripts']}")


if __name__ == '__main__':
    main()
