#!/bin/bash
# finish_r2h.sh - manifest rows, DIFFs and checksums for the r2h CANDIDATE (run after the build and tests). Re-runnable.
set -euo pipefail
D=/work/fixed_image_r2h_candidate_20261110
C=/work/fixed_image_r2g_20261110
cd $D
python3 -I - <<'EOF'
import hashlib
D = '/work/fixed_image_r2h_candidate_20261110'
P = 'drone/ros2_ws/src/bumblebee/'
def sha(rel):
    return hashlib.sha256(open(D + '/src/bumblebee/' + rel, 'rb').read()).hexdigest()
notes = {'examples/drone.py': '; r2h (candidate): navigate_wait looks at the vision watchdog every 0.1 s, hold clock',
         'src/python/vpe_fix.py': '; r2h (candidate): B1 gate >=1 marker in 1.5 s, decided per frame; B2 medoid of 3 after a pause'}
path = D + '/image_manifest_r2.tsv'
rows = open(path, encoding='utf-8').read().split('\n')
out, seen = [], set()
for r in rows:
    f = r.split('\t')
    rel = f[0][len(P):] if f[0].startswith(P) else None
    if rel in notes:
        f[2] = sha(rel)
        if 'r2h' not in f[3]:
            f[3] = f[3] + ' + r2h'
            f[4] = f[4] + notes[rel]
        seen.add(rel)
        r = '\t'.join(f)
    out.append(r)
assert seen == set(notes), seen
open(path, 'w', encoding='utf-8').write('\n'.join(out))
print('tsv rows updated:', sorted(seen))
EOF
diff -ruN $C/src src > notes/DIFF_r2h_vs_r2g.txt || true
diff -ruN /work/fixed_image_r1_20261109/src src > DIFF_vs_r1.txt || true
(cd install/bumblebee/lib/bumblebee && sha256sum $(ls)) > INSTALL_SHA256.txt
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . -type f ! -path './install/*' ! -path './build/*' ! -path './log/*' ! -name MANIFEST_SHA256.txt \
    ! -name SHA256SUMS ! -path '*/.pytest_cache/*' -print0 | sort -z | xargs -0 sha256sum > MANIFEST_SHA256.txt
sha256sum -c --quiet MANIFEST_SHA256.txt && echo MANIFEST_OK $(wc -l < MANIFEST_SHA256.txt) files $(sha256sum MANIFEST_SHA256.txt | cut -c1-8)
(cd install/bumblebee/lib/bumblebee && sha256sum -c --quiet ../../../../INSTALL_SHA256.txt) && echo INSTALL_OK
sha256sum MANIFEST_SHA256.txt INSTALL_SHA256.txt README.md image_manifest_r2.tsv > SHA256SUMS
sha256sum -c --quiet SHA256SUMS && echo SUMS_OK $(sha256sum SHA256SUMS | cut -c1-8)
grep -c '^diff ' notes/DIFF_r2h_vs_r2g.txt DIFF_vs_r1.txt
