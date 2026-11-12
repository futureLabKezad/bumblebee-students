#!/usr/bin/env python3
"""make_r2j.py - task T53 of chat 1 (11.11.2026): image r2j = r2i (/work/fixed_image_r2i_20261111, SHA256SUMS 38daf429;
reviewed: accept with notes, no MUST-FIX; not edited) + the camera mounts of the 20EC reference
(Documents\\Claude local\\model_measure_20261111\\ЭТАЛОН_РАЗМЕРОВ_20EC.md, owner's 1:1 model, owner 11.11: «...поправь все
остальное все размеры и чтоб без ошибок...»). base_link = centre B (between the motors, 0.217 m above the feet);
program axes X forward, Y left, Z up. Translations only; the rotation angles are not touched.
  1. down camera, base_link -> main_camera_optical: (0.05, 0, -0.07) -> (0.081, 0, -0.034):
     launch/bumblebee.launch.py (main_camera_frame) and the two «down» variants of launch/main_camera.launch.py;
  2. forward camera, base_link -> second_camera_optical: (0.05, 0, 0.05) -> (0.113, 0, -0.002):
     launch/bumblebee.launch.py (second_camera_frame) and launch/second_camera.launch.py.
  3. flight.py: takeoff 0.8 -> 0.9 m and its header line (chat 1, owner 11.11 «0,9 м, как flight_marker»); the Q6 test E1
     follows (0.8 -> 0.9).
Not changed: drone.py (DRONE_REST_Z_OFFSET 0.32 is defined but used nowhere -- see README), the «up», «forward» and
«backward» mounting variants of main_camera.launch.py (other mountings, not the 20EC down camera), everything else.
EDITS is the single table of changes; test/test_r2j_changes.py applies it backwards and must get r2i's bytes.
Usage: python3 -I make_r2j.py   (refuses to overwrite; then colcon, tools/finish_r2j.sh, tools/test_all_r2j.sh, finish)
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

WORK = Path('/work')
R2I = WORK / 'fixed_image_r2i_20261111'
DST = WORK / 'fixed_image_r2j_20261111'
HERE = Path(__file__).resolve().parent
R2I_SUMS = '38daf42986a93e361128fc05fc8d05315320e8cff6fca4d2bbd63381a22d0204'
R2I_MANIFEST = '855f9f93e2166d8cde1156f6f010728210919882337e30fade4d7ba63f58412b'
S = 'src/bumblebee/'
L = S + 'launch/'
REF = '# r2j (T53): translation per ЭТАЛОН_РАЗМЕРОВ_20EC (owner model 1:1, 11.11.2026); angles unchanged\n'
DOWN = "['0.081', '0', '-0.034',"
FWD = "['0.113', '0', '-0.002',"

EDITS = [
    (L + 'bumblebee.launch.py',
     "        # down + backward orientation\n        arguments=['0.05', '0', '-0.07', '-1.5707963', '0', '3.1415926',\n",
     "        # down + backward orientation\n        " + REF + "        arguments=" + DOWN + " '-1.5707963', '0', '3.1415926',\n",
     'main_camera_frame (down camera)'),
    (L + 'bumblebee.launch.py',
     "        name='second_camera_frame',\n        arguments=['0.05', '0', '0.05', '-1.5707963', '0', '0',\n",
     "        name='second_camera_frame',\n        " + REF + "        arguments=" + FWD + " '-1.5707963', '0', '0',\n",
     'second_camera_frame (forward camera)'),
    (L + 'main_camera.launch.py',
     "        # TF: down + backward (default)\n        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',\n"
     "             arguments=['0.05', '0', '-0.07', '-1.5707963', '0', '3.1415926', 'base_link', 'main_camera_optical'],\n",
     "        # TF: down + backward (default)\n        " + REF +
     "        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',\n"
     "             arguments=" + DOWN + " '-1.5707963', '0', '3.1415926', 'base_link', 'main_camera_optical'],\n",
     'down + backward'),
    (L + 'main_camera.launch.py',
     "        # TF: down + forward\n        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',\n"
     "             arguments=['0.05', '0', '-0.07', '1.5707963', '0', '3.1415926', 'base_link', 'main_camera_optical'],\n",
     "        # TF: down + forward\n        " + REF +
     "        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',\n"
     "             arguments=" + DOWN + " '1.5707963', '0', '3.1415926', 'base_link', 'main_camera_optical'],\n",
     'down + forward'),
    (L + 'second_camera.launch.py',
     "            name='second_camera_frame',\n            arguments=['0.05', '0', '0.05', '-1.5707963', '0', '0',\n",
     "            name='second_camera_frame',\n            " + REF + "            arguments=" + FWD + " '-1.5707963', '0', '0',\n",
     'second_camera_frame'),
    # chat 1, 11.11 (owner: «0,9 м, как flight_marker»): flight.py takes off to 0.9 m (the reference sensor positions make
    # PX4 see the height 5 cm lower; T49: dist_bottom 1.02 m at the 1 m hover-thrust threshold). C5: «as set in the script».
    (S + 'examples/flight/flight.py', "flight.py -- single- or multi-marker ArUco preflight, takeoff to 0.8m, hover, land.\n",
     "flight.py -- single- or multi-marker ArUco preflight, takeoff to 0.9m, hover, land.\n", 'flight.py header: 0.9m'),
    (S + 'examples/flight/flight.py', "    drone.takeoff(height=0.8, speed=0.4)\n", "    drone.takeoff(height=0.9, speed=0.4)\n",
     'flight.py takeoff 0.8 -> 0.9 m (owner 11.11)'),
    ('test/test_q6_fixes.py', "E1  flight.py takes off to 0.8 m.   E2",
     "E1  flight.py takes off to 0.9 m (r2j, owner 11.11; Q6: 0.8 m).   E2", 'Q6 E1 docstring: 0.9 m'),
    ('test/test_q6_fixes.py', "        self.assertIn('takeoff to 0.8m', t)\n        self.assertIn('drone.takeoff(height=0.8, speed=0.4)', t)\n",
     "        self.assertIn('takeoff to 0.9m', t)          # r2j: owner 11.11 «0,9 м, как flight_marker»\n"
     "        self.assertIn('drone.takeoff(height=0.9, speed=0.4)', t)\n", 'Q6 E1: 0.9 m'),
]
NEW_FILES = {'test/test_r2j_changes.py': 'test_r2j_changes.py'}
R2I_ONLY_TESTS = ['test/test_r2i_changes.py']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if sha(R2I / 'SHA256SUMS') != R2I_SUMS or sha(R2I / 'MANIFEST_SHA256.txt') != R2I_MANIFEST:
        sys.exit('STOP: r2i is not the reviewed one')
    for f in ('SHA256SUMS', 'MANIFEST_SHA256.txt'):
        subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=R2I, check=True)
    for rel, old, new, why in EDITS:
        t = (R2I / rel).read_text()
        if t.count(old) != 1:
            sys.exit('STOP: %s anchor %r: %d matches' % (rel, old[:60], t.count(old)))
    DST.mkdir()
    for d in ('src', 'test', 'tools', 'notes', 'reviews'):
        shutil.copytree(R2I / d, DST / d, symlinks=True)
    shutil.copy2(R2I / 'image_manifest_r2.tsv', DST / 'image_manifest_r2.tsv')
    prev = DST / 'notes/prev_r2i'
    prev.mkdir()
    for f in ('README.md', 'PROGRESS.md', 'SHA256SUMS', 'MANIFEST_SHA256.txt', 'INSTALL_SHA256.txt', 'DIFF_vs_r1.txt'):
        shutil.copy2(R2I / f, prev / f)
    shutil.move(str(DST / 'reviews'), str(prev / 'reviews'))
    shutil.move(str(DST / 'notes/test_logs'), str(prev / 'test_logs'))
    shutil.move(str(DST / 'notes/controls'), str(prev / 'controls'))
    (DST / 'test/r2i_only').mkdir()
    for t in R2I_ONLY_TESTS:
        shutil.move(str(DST / t), str(DST / 'test/r2i_only' / Path(t).name))
    log = []
    for rel, old, new, why in EDITS:
        p = DST / rel
        p.write_text(p.read_text().replace(old, new))
        log.append('%s: %s' % (rel, why))
    for rel, src in NEW_FILES.items():
        shutil.copy2(HERE / src, DST / rel)
        log.append(rel + ': new')
    for rel, old in (('test/test_r2h.py', 'fixed_image_r2i_20261111'), ('test/test_r2h_vpe.py', 'fixed_image_r2i_20261111'),
                     ('test/test_r2i_vpe.py', "'fixed_image_r2i_'")):
        p = DST / rel
        t = p.read_text()
        if t.count(old) != 1:
            sys.exit('STOP: folder anchor in ' + rel)
        p.write_text(t.replace(old, old.replace('r2i', 'r2j')))
        log.append(rel + ': folder -> r2j')
    for f in ('make_r2j.py', 'test_all_r2j.sh', 'finish_r2j.sh'):
        shutil.copy2(HERE / f, DST / 'tools' / f)
    (DST / 'notes/build_edits_r2j.txt').write_text('\n'.join(log) + '\n')
    print('\n'.join(log))


if __name__ == '__main__':
    main()
