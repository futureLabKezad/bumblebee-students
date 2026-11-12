#!/bin/bash
# finish_r2f.sh - manifest rows, DIFFs and checksums for r2f (run after the build and tests). Re-runnable.
set -euo pipefail
D=/work/fixed_image_r2f_20261110
C=/work/fixed_image_r2e_20261109
cd $D
python3 -I - <<'EOF'
import hashlib
D = '/work/fixed_image_r2f_20261110'
P = 'drone/ros2_ws/src/bumblebee/'
def sha(rel):
    return hashlib.sha256(open(D + '/src/bumblebee/' + rel, 'rb').read()).hexdigest()
notes = {
    'examples/drone.py': '; r2f: T35 vision watchdog on new vpe_fix poses (vision_pose_age)',
    'examples/flight/flight.py': '; r2f: T35 hover watchdog on vision_pose_age',
    'examples/flight/flight_marker.py': '; r2f: T35 hover_vw on vision_pose_age',
    'examples/flight/flight_marker_loop.py': '; r2f: T35 hover watchdog on vision_pose_age',
    'src/cpp/simple_offboard.cpp': ' + r2f: T34 nav_from_sp flag after OFFBOARD',
    'test/test_drone_flight_guards.py': '; r2f: vision tests set _vpe_pose_time',
}
path = D + '/image_manifest_r2.tsv'
rows = open(path, encoding='utf-8').read().split('\n')
out, seen = [], set()
for r in rows:
    f = r.split('\t')
    rel = f[0][len(P):] if f[0].startswith(P) else None
    if rel in notes:
        f[2] = sha(rel)
        if 'r2f' not in f[4]:
            f[3] = f[3] + ' + r2f'
            f[4] = f[4] + notes[rel]
        seen.add(rel)
        r = '\t'.join(f)
    out.append(r)
print('tsv rows updated:', sorted(seen))
print('not in tsv:', sorted(set(notes) - seen))
open(path, 'w', encoding='utf-8').write('\n'.join(out))
EOF
diff -ruN $C/src src > notes/DIFF_r2f_vs_r2e.txt || true
diff -ruN /work/fixed_image_r1_20261109/src src > DIFF_vs_r1.txt || true
(cd install/bumblebee/lib/bumblebee && sha256sum $(ls)) > INSTALL_SHA256.txt
find . -type f ! -path './install/*' ! -path './build/*' ! -path './log/*' ! -name MANIFEST_SHA256.txt \
    ! -name SHA256SUMS ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum > MANIFEST_SHA256.txt
sha256sum -c --quiet MANIFEST_SHA256.txt && echo MANIFEST_OK $(wc -l < MANIFEST_SHA256.txt) files $(sha256sum MANIFEST_SHA256.txt | cut -c1-8)
(cd install/bumblebee/lib/bumblebee && sha256sum -c --quiet ../../../../INSTALL_SHA256.txt) && echo INSTALL_OK
sha256sum MANIFEST_SHA256.txt INSTALL_SHA256.txt README.md image_manifest_r2.tsv > SHA256SUMS
sha256sum -c --quiet SHA256SUMS && echo SUMS_OK $(sha256sum SHA256SUMS | cut -c1-8)
grep -c '^diff ' notes/DIFF_r2f_vs_r2e.txt DIFF_vs_r1.txt
