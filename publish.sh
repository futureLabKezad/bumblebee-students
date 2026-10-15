#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python3 verify_snapshot.py
python3 verify_archive.py > archive_verification.json
python3 - <<'PY'
import json
from pathlib import Path
p=Path('publication.json');p.write_text(json.dumps({'repository':'futureLabKezad/bumblebee-students','branch':'backup/bbsim-complete-2026-10-15','kind':'complete workspace snapshot including unfinished work','flight_accepted':False,'archive_verified':True,'original_source_branches_modified':False},indent=2)+'\n')
PY
git add README.md STATUS.md FILES.json SHA256SUMS.json verify_snapshot.py verify_archive.py make_snapshot.py publication.json archive_verification.json creation.log publish.sh
git commit -m 'docs: preserve complete Bumblebee work state and unfinished flight qualification [skip ci]'
git push origin HEAD:refs/heads/backup/bbsim-complete-2026-10-15
count=0
for part in workspace.tar.gz.part*; do
 git add "$part"
 count=$((count+1))
 if [ $((count % 4)) -eq 0 ]; then
  git commit -m "backup: add workspace archive parts through $count [skip ci]"
  git push origin HEAD:refs/heads/backup/bbsim-complete-2026-10-15
 fi
done
if ! git diff --cached --quiet; then
 git commit -m 'backup: finish complete workspace archive [skip ci]'
 git push origin HEAD:refs/heads/backup/bbsim-complete-2026-10-15
fi
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/backup/bbsim-complete-2026-10-15 | cut -f1)
test "$LOCAL" = "$REMOTE"
printf 'VERIFIED_REMOTE_HEAD=%s\n' "$REMOTE"
git status --short
