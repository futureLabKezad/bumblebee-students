#!/bin/bash
# finish_r2h_final.sh - manifest rows, DIFFs and checksums for the FINAL r2h (T44). Order: build, tests, then this.
# Re-runnable.
set -euo pipefail
D=/work/fixed_image_r2h_20261110
cd $D
python3 -I - <<'EOF'
import hashlib, os
D = '/work/fixed_image_r2h_20261110'
P = 'drone/ros2_ws/src/bumblebee/'
H2 = 'test/vpe_fix_h2_r2/'
def sha(rel):
    return hashlib.sha256(open(D + '/src/bumblebee/' + rel, 'rb').read()).hexdigest()
# rows whose sha changes, with the note text (replaces the candidate's note, idempotent)
upd = {
    'examples/drone.py': None,                       # sha only (the candidate's bytes); source keeps '+ r2h'
    'src/python/vpe_fix.py': ('; r2h (candidate): B1 gate >=1 marker in 1.5 s, decided per frame; B2 medoid of 3 after a pause',
                              '; r2h: B1 gate >=1 marker in 1.5 s, decided per frame; B2 medoid of 3 after a pause, a tie -> the newest (T44)'),
    'CMakeLists.txt': (' + r2d: std_msgs for simple_offboard (T25)',
                       ' + r2d: std_msgs for simple_offboard (T25) + r2h: code pins round 3 (T44)'),
    H2 + 'README.md': None,
}
new_rows = {H2 + 'ref/vpe_fix_r2g_3b8a93d4.py': 'r2h', H2 + 'tests_r3/test_pins_r3.py': 'r2h'}
path = D + '/image_manifest_r2.tsv'
text = open(path, encoding='utf-8').read()
rows = text.split('\n')
out, seen = [], set()
for r in rows:
    f = r.split('\t')
    rel = f[0][len(P):] if f[0].startswith(P) else None
    if rel in new_rows:
        continue                                     # re-run: rebuilt below
    if rel in upd:
        f[2] = sha(rel)
        if upd[rel] and upd[rel][1] not in f[4]:
            assert f[4].count(upd[rel][0]) == 1, (rel, f[4])
            f[4] = f[4].replace(upd[rel][0], upd[rel][1])
        if rel == 'CMakeLists.txt' and '+ r2h' not in f[3]:
            f[3] += ' + r2h'
        seen.add(rel)
        r = '\t'.join(f)
    out.append(r)
    if rel == H2 + 'tests_r2/test_pins_r2.py':
        for n in sorted(new_rows):
            out.append('\t'.join([P + n, '-', sha(n), new_rows[n], 'new']))
assert seen == set(upd), seen
# the full TSV row list must be sorted by path where the candidate's was (insertion keeps the H2 block in order)
open(path, 'w', encoding='utf-8').write('\n'.join(out))
# consistency: every bumblebee row's fixed sha equals the file, except the pending camera fix
bad = []
for r in out:
    f = r.split('\t')
    if len(f) < 5 or not f[0].startswith(P):
        continue
    rel = f[0][len(P):]
    p = D + '/src/bumblebee/' + rel
    if os.path.isfile(p) and f[2] != sha(rel):
        bad.append(rel)
# known, inherited from the candidate and r2g (not changed by T44): the pending camera fix, and fcu_detect_fix_01
# (row = the file on the drone since 05.11 14:10; src holds the a45a264 file)
assert sorted(bad) == ['scripts/fcu_detect.py', 'src/python/camera_fix.py'], bad
print('tsv rows updated:', sorted(seen), 'new:', sorted(new_rows), 'known row/src mismatches (inherited):', sorted(bad))
EOF
diff -ruN /work/fixed_image_r2g_20261110/src src > notes/DIFF_r2h_vs_r2g.txt || true
diff -ruN /work/fixed_image_r2h_candidate_20261110/src src > notes/DIFF_r2h_final_vs_candidate_src.txt || true
diff -ruN -x __pycache__ /work/fixed_image_r2h_candidate_20261110/test test > notes/DIFF_r2h_final_vs_candidate_test.txt || true
diff -u /work/fixed_image_r2h_candidate_20261110/image_manifest_r2.tsv image_manifest_r2.tsv > notes/DIFF_r2h_final_vs_candidate_tsv.txt || true
diff -ruN /work/fixed_image_r1_20261109/src src > DIFF_vs_r1.txt || true
(cd install/bumblebee/lib/bumblebee && sha256sum $(ls)) > INSTALL_SHA256.txt
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . -type f ! -path './install/*' ! -path './build/*' ! -path './log/*' ! -name MANIFEST_SHA256.txt \
    ! -name SHA256SUMS ! -path '*/.pytest_cache/*' -print0 | sort -z | xargs -0 sha256sum > MANIFEST_SHA256.txt
sha256sum -c --quiet MANIFEST_SHA256.txt && echo MANIFEST_OK $(wc -l < MANIFEST_SHA256.txt) files $(sha256sum MANIFEST_SHA256.txt | cut -c1-8)
(cd install/bumblebee/lib/bumblebee && sha256sum -c --quiet ../../../../INSTALL_SHA256.txt) && echo INSTALL_OK
sha256sum MANIFEST_SHA256.txt INSTALL_SHA256.txt README.md image_manifest_r2.tsv > SHA256SUMS
sha256sum -c --quiet SHA256SUMS && echo SUMS_OK $(sha256sum SHA256SUMS | cut -c1-8)
grep -c '^diff ' notes/DIFF_r2h_vs_r2g.txt notes/DIFF_r2h_final_vs_candidate_src.txt notes/DIFF_r2h_final_vs_candidate_test.txt DIFF_vs_r1.txt
