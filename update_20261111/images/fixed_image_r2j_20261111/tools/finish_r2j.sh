#!/bin/bash
# finish_r2j.sh - manifest rows, DIFFs and checksums for r2j (T53). Order: build, this (rows), tests, this. Re-runnable.
set -euo pipefail
D=/work/fixed_image_r2j_20261111
cd $D
python3 -I - <<'EOF'
import hashlib, os
D = '/work/fixed_image_r2j_20261111'
P = 'drone/ros2_ws/src/bumblebee/'
def sha(rel):
    return hashlib.sha256(open(D + '/src/bumblebee/' + rel, 'rb').read()).hexdigest()
note = '; r2j: per the 20EC reference (T53: camera translation; flight.py takeoff 0.9 m)'
rels = {'launch/bumblebee.launch.py', 'launch/main_camera.launch.py', 'launch/second_camera.launch.py', 'examples/flight/flight.py'}
path = D + '/image_manifest_r2.tsv'
rows = open(path, encoding='utf-8').read().split('\n')
out, seen = [], set()
for r in rows:
    f = r.split('\t')
    rel = f[0][len(P):] if f[0].startswith(P) else None
    if rel in rels:
        f[2] = sha(rel)
        if note not in f[4]:
            if f[4].startswith('same'):
                f[4] = 'changed' + f[4][4:]
            f[4] += note
            f[3] += ' + r2j'
        seen.add(rel)
        r = '\t'.join(f)
    out.append(r)
assert seen == rels, rels - seen
open(path, 'w', encoding='utf-8').write('\n'.join(out))
bad = []
for r in out:
    f = r.split('\t')
    if len(f) < 5 or not f[0].startswith(P):
        continue
    rel = f[0][len(P):]
    if os.path.isfile(D + '/src/bumblebee/' + rel) and f[2] != sha(rel):
        bad.append(rel)
assert bad == ['scripts/fcu_detect.py'], bad      # inherited (the file on the drone since 05.11); not T53
print('tsv rows updated:', sorted(seen), '; known row/src mismatch (inherited):', bad)
EOF
diff -ruN /work/fixed_image_r2i_20261111/src src > notes/DIFF_r2j_vs_r2i_src.txt || true
diff -u /work/fixed_image_r2i_20261111/image_manifest_r2.tsv image_manifest_r2.tsv > notes/DIFF_r2j_vs_r2i_tsv.txt || true
diff -ruN /work/fixed_image_r1_20261109/src src > DIFF_vs_r1.txt || true
(cd install/bumblebee/lib/bumblebee && sha256sum $(ls)) > INSTALL_SHA256.txt
find . -type f ! -path './install/*' ! -path './build/*' ! -path './log/*' ! -name MANIFEST_SHA256.txt \
    ! -name SHA256SUMS ! -path '*/.pytest_cache/*' ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum > MANIFEST_SHA256.txt
sha256sum -c --quiet MANIFEST_SHA256.txt && echo MANIFEST_OK $(wc -l < MANIFEST_SHA256.txt) files $(sha256sum MANIFEST_SHA256.txt | cut -c1-8)
(cd install/bumblebee/lib/bumblebee && sha256sum -c --quiet ../../../../INSTALL_SHA256.txt) && echo INSTALL_OK
sha256sum MANIFEST_SHA256.txt INSTALL_SHA256.txt README.md image_manifest_r2.tsv > SHA256SUMS
sha256sum -c --quiet SHA256SUMS && echo SUMS_OK $(sha256sum SHA256SUMS | cut -c1-8)
grep -c '^diff ' notes/DIFF_r2j_vs_r2i_src.txt DIFF_vs_r1.txt
