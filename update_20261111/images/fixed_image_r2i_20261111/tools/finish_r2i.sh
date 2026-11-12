#!/bin/bash
# finish_r2i.sh - manifest rows, DIFFs and checksums for r2i (T46). Order: build, tests, then this. Re-runnable.
set -euo pipefail
D=/work/fixed_image_r2i_20261111
cd $D
python3 -I - <<'EOF'
import hashlib, os
D = '/work/fixed_image_r2i_20261111'
P = 'drone/ros2_ws/src/bumblebee/'
H2 = 'test/vpe_fix_h2_r2/'
def sha(rel):
    return hashlib.sha256(open(D + '/src/bumblebee/' + rel, 'rb').read()).hexdigest()
notes = {
    'src/python/vpe_fix.py': '; r2i: publishes in AUTO.LAND on the same vision condition (owner 11.11)',
    'src/cpp/simple_offboard.cpp': '; r2i: state watchdog counts the link silence with state_link.h (S9)',
    'examples/flight/flight_marker.py': '; r2i: takeoff 0.9 m (owner 11.11, T41)',
    'CMakeLists.txt': '; r2i: code pins round 4',
    H2 + 'README.md': '; r2i: round 4 row',
    'test/test_simple_offboard_px4model_launch.py': '; r2i: S9 realtime long gap 6.0 s (state_link.h)',
}
new_rows = {'src/cpp/state_link.h': 'r2i', H2 + 'ref/vpe_fix_r2h_66d806ba.py': 'r2i', H2 + 'tests_r4/test_pins_r4.py': 'r2i'}
path = D + '/image_manifest_r2.tsv'
rows = open(path, encoding='utf-8').read().split('\n')
out, seen = [], set()
for r in rows:
    f = r.split('\t')
    rel = f[0][len(P):] if f[0].startswith(P) else None
    if rel in new_rows:
        continue
    if rel in notes:
        f[2] = sha(rel)
        if notes[rel] not in f[4]:
            f[4] += notes[rel]
            f[3] += ' + r2i'
            if f[4].startswith('same'):
                f[4] = 'changed' + f[4][4:]
        seen.add(rel)
        r = '\t'.join(f)
    out.append(r)
    if rel == 'src/cpp/simple_offboard.cpp':
        out.append('\t'.join([P + 'src/cpp/state_link.h', '-', sha('src/cpp/state_link.h'), 'r2i', 'new']))
    if rel == H2 + 'ref/vpe_fix_r2g_3b8a93d4.py':
        out.append('\t'.join([P + H2 + 'ref/vpe_fix_r2h_66d806ba.py', '-', sha(H2 + 'ref/vpe_fix_r2h_66d806ba.py'), 'r2i', 'new']))
    if rel == H2 + 'tests_r3/test_pins_r3.py':
        out.append('\t'.join([P + H2 + 'tests_r4/test_pins_r4.py', '-', sha(H2 + 'tests_r4/test_pins_r4.py'), 'r2i', 'new']))
assert seen == set(notes), set(notes) - seen
assert sum(1 for r in out if r.split('\t')[0][len(P):] in new_rows) == 3
open(path, 'w', encoding='utf-8').write('\n'.join(out))
bad = []
for r in out:
    f = r.split('\t')
    if len(f) < 5 or not f[0].startswith(P):
        continue
    rel = f[0][len(P):]
    if os.path.isfile(D + '/src/bumblebee/' + rel) and f[2] != sha(rel):
        bad.append(rel)
# inherited, not changed by T46: fcu_detect (row = the file on the drone since 05.11; src holds a45a264). camera_fix: now closed.
assert bad == ['scripts/fcu_detect.py'], bad
print('tsv rows updated:', sorted(seen), '+ 3 new; known row/src mismatch (inherited):', bad)
EOF
diff -ruN /work/fixed_image_r2h_20261110/src src > notes/DIFF_r2i_vs_r2h_src.txt || true
diff -ruN -x __pycache__ /work/fixed_image_r2h_20261110/test test > notes/DIFF_r2i_vs_r2h_test.txt || true
diff -u /work/fixed_image_r2h_20261110/image_manifest_r2.tsv image_manifest_r2.tsv > notes/DIFF_r2i_vs_r2h_tsv.txt || true
diff -ruN /work/fixed_image_r1_20261109/src src > DIFF_vs_r1.txt || true
(cd install/bumblebee/lib/bumblebee && sha256sum $(ls)) > INSTALL_SHA256.txt
find . -path ./build -prune -o -path ./install -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
find . -type f ! -path './install/*' ! -path './build/*' ! -path './log/*' ! -name MANIFEST_SHA256.txt \
    ! -name SHA256SUMS ! -path '*/.pytest_cache/*' -print0 | sort -z | xargs -0 sha256sum > MANIFEST_SHA256.txt
sha256sum -c --quiet MANIFEST_SHA256.txt && echo MANIFEST_OK $(wc -l < MANIFEST_SHA256.txt) files $(sha256sum MANIFEST_SHA256.txt | cut -c1-8)
(cd install/bumblebee/lib/bumblebee && sha256sum -c --quiet ../../../../INSTALL_SHA256.txt) && echo INSTALL_OK
sha256sum MANIFEST_SHA256.txt INSTALL_SHA256.txt README.md image_manifest_r2.tsv > SHA256SUMS
sha256sum -c --quiet SHA256SUMS && echo SUMS_OK $(sha256sum SHA256SUMS | cut -c1-8)
grep -c '^diff ' notes/DIFF_r2i_vs_r2h_src.txt notes/DIFF_r2i_vs_r2h_test.txt DIFF_vs_r1.txt
