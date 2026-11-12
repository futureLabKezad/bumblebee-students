#!/bin/bash
# finish_r2d.sh - manifest rows, DIFFs and checksums for r2d (run after the build and tests). Re-runnable.
set -euo pipefail
D=/work/fixed_image_r2d_20261109
C=/work/fixed_image_r2c_20261109
cd $D
python3 -I - <<'EOF'
import hashlib
D = '/work/fixed_image_r2d_20261109'
P = 'drone/ros2_ws/src/bumblebee/'
def sha(rel):
    return hashlib.sha256(open(D + '/src/bumblebee/' + rel, 'rb').read()).hexdigest()
notes = {
    'CMakeLists.txt': ' + r2d: std_msgs for simple_offboard (T25)',
    'examples/drone.py': '; r2d: F7 settle_speed, T25 script lease',
    'examples/flight/flight_marker.py': '; r2d: F7 tolerance 0.12 + settle 0.05',
    'examples/flight/flight_marker_loop.py': '; r2d: F7 tolerance 0.12 + settle 0.05',
    'src/cpp/simple_offboard.cpp': ' + r2d: T25 script lease watchdog',
}
path = D + '/image_manifest_r2.tsv'
rows = open(path, encoding='utf-8').read().split('\n')
out, seen = [], set()
for r in rows:
    f = r.split('\t')
    rel = f[0][len(P):] if f[0].startswith(P) else None
    if rel in notes:
        if 'r2d' not in f[4]:
            f[2] = sha(rel)
            f[3] = f[3] + ' + r2d'
            f[4] = f[4] + notes[rel]
        else:
            f[2] = sha(rel)
        seen.add(rel)
        r = '\t'.join(f)
    if rel == 'src/cpp/script_lease.h':
        continue
    out.append(r)
    if rel == 'src/cpp/rc.cpp':
        out.append('\t'.join([P + 'src/cpp/script_lease.h', '-', sha('src/cpp/script_lease.h'), 'r2d',
                              'new (r2d: T25 script lease decision, no ROS)']))
assert seen == set(notes), seen
open(path, 'w', encoding='utf-8').write('\n'.join(out))
print('tsv rows updated:', len(seen), '+ script_lease.h')
EOF
diff -ruN $C/src src > notes/DIFF_r2d_vs_r2c.txt || true
diff -ruN /work/fixed_image_r1_20261109/src src > DIFF_vs_r1.txt || true
(cd install/bumblebee/lib/bumblebee && sha256sum $(ls)) > INSTALL_SHA256.txt
find . -type f ! -path './install/*' ! -path './build/*' ! -path './log/*' ! -name MANIFEST_SHA256.txt \
    ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum > MANIFEST_SHA256.txt
sha256sum -c --quiet MANIFEST_SHA256.txt && echo MANIFEST_OK $(wc -l < MANIFEST_SHA256.txt) files $(sha256sum MANIFEST_SHA256.txt | cut -c1-8)
(cd install/bumblebee/lib/bumblebee && sha256sum -c --quiet ../../../../INSTALL_SHA256.txt) && echo INSTALL_OK
grep -c '^diff ' notes/DIFF_r2d_vs_r2c.txt DIFF_vs_r1.txt
