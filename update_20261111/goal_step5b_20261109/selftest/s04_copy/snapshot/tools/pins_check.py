#!/usr/bin/env python3
"""pins_check.py - goal step 5 (Claude, 06.11.2026). Reads files only. C1 evidence for one scenario run.

Compares the product files the SITL scenario stack really runs with the fixed-image manifest of goal step 1
(/work/goal_20261106/image_manifest.tsv, column sha256_fixed_image). Python/launch/config/map files must be
byte-identical; for C++ (simple_offboard) and MAVROS only the source can match (different CPU), so the built binary
sha is recorded and the source is compared. Writes RUN/pins.json and prints a one-line summary. Never fails the run:
the launcher prints the differences, the report explains them.
Usage: python3 -I pins_check.py RUN_DIR SCRIPT_RELPATH   (e.g. examples/flight/flight.py)
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
    man = {}
    for line in open(MANIFEST, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        path, on_drone, fixed, source, change = line.rstrip('\n').split('\t')
        man[path] = (on_drone, fixed, change)
    used_src = ['examples/drone.py', 'examples/flight_profile.py', script,
                'src/python/aruco_detect.py', 'src/python/camera_fix.py', 'src/python/vpe_fix.py',
                'src/python/setpoint_freshness.py', 'src/cpp/simple_offboard.cpp',
                'launch/mavros_scoped_config.py', 'launch/bumblebee.launch.py', 'launch/aruco.launch.py']
    rows = []
    for rel in used_src:
        p = os.path.join(PRODUCT, 'src/bumblebee', rel)
        s = sha(p)
        on_drone, fixed, change = man.get(REPO_PKG + rel, (None, None, 'not in manifest'))
        rows.append({'file': rel, 'sim_path': p, 'sha_sim': s, 'sha_fixed_image': fixed, 'sha_on_drone': on_drone,
                     'status': 'same' if s == fixed else ('NOT IN MANIFEST' if fixed is None else 'DIFFERS'),
                     'manifest_note': change})
    # installed python executables that ros2 launch really starts must equal their sources
    for name in ('aruco_detect.py', 'camera_fix.py', 'vpe_fix.py', 'setpoint_freshness.py'):
        inst = os.path.join(PRODUCT, 'install/bumblebee/lib/bumblebee', name)
        src = os.path.join(PRODUCT, 'src/bumblebee/src/python', name)
        rows.append({'file': 'install/lib/bumblebee/' + name, 'sim_path': inst, 'sha_sim': sha(inst),
                     'sha_fixed_image': sha(src), 'status': 'same' if sha(inst) == sha(src) else 'DIFFERS',
                     'manifest_note': 'installed copy vs its source'})
    mp = '/work/sim/worlds/aruco_map/map.input.txt'
    on_drone, fixed, change = man.get('drone/ros2_ws/src/aruco_pose/map/map.txt', (None, None, ''))
    rows.append({'file': 'aruco_pose/map/map.txt', 'sim_path': mp, 'sha_sim': sha(mp), 'sha_fixed_image': fixed,
                 'status': 'same' if sha(mp) == fixed else 'DIFFERS', 'manifest_note': change})
    for label, p in (('simple_offboard binary (PC build of the same source)',
                      os.path.join(PRODUCT, 'install/bumblebee/lib/bumblebee/simple_offboard')),
                     ('mavros_node binary (bp02 PC build)', '/work/ws_mavros214_bp02_rel/install/mavros/lib/mavros/mavros_node')):
        rows.append({'file': label, 'sim_path': p, 'sha_sim': sha(p), 'sha_fixed_image': None, 'status': 'recorded',
                     'manifest_note': 'binary for x86; compare by source'})
    out = {'manifest': MANIFEST, 'manifest_sha256': sha(MANIFEST), 'product': PRODUCT, 'rows': rows,
           'differs': [r['file'] for r in rows if r['status'] in ('DIFFERS', 'NOT IN MANIFEST')]}
    with open(os.path.join(run_dir, 'pins.json'), 'x', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    print(f"pins: {sum(r['status'] == 'same' for r in rows)} same, differs: {out['differs']}")


if __name__ == '__main__':
    main()
