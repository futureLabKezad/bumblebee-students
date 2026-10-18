#!/usr/bin/env bash
# restore_snapshot.sh - restore the Bumblebee work folder (bbsim-work) on the Windows PC, inside
# WSL2 Ubuntu 24.04, as the NORMAL user (no sudo). SIMULATOR ONLY: nothing here starts a simulator
# or talks to a drone. Nothing is deleted; replaced files are kept in /work/_overlay_replaced_20261017.
#
#   bash restore_snapshot.sh all        = clone repo extract overlay accept
#   bash restore_snapshot.sh clone      ~/bumblebee-backup: branch backup/bbsim-complete-2026-10-15
#                                       (single branch, depth 1) + verify_snapshot.py (the 21 archive parts)
#   bash restore_snapshot.sh repo       ~/bumblebee-students: branch feat/sim-trial, checked at b31ca69
#   bash restore_snapshot.sh extract    archive -> /work (~/bbsim-work is a link to /work), then
#                                       verify_snapshot.py /work (all 66 791 entries of 15.10)
#   bash restore_snapshot.sh overlay    the 17.10 update, by update_20261017/MANIFEST_SHA256.json only:
#                                       bbsim-work/<p>         -> /work/<p> (= ~/bbsim-work/<p>)
#                                       workspace_root_docs/<p> -> ~/bumblebee-workspace-docs/<p>
#                                       every sha256 checked before and after copying; nothing deleted;
#                                       a replaced file is kept in /work/_overlay_replaced_20261017/
#   bash restore_snapshot.sh accept     offline acceptance checks (stdlib Python only, no ROS)
#
# MANIFEST_SHA256.json format (written by the Mac side; nothing else is accepted):
#   {"schema": 1, "root": "update_20261017",
#    "files": {"<path relative to update_20261017>": "<sha256, 64 hex>", ...}}
#   Paths are POSIX-relative: no leading "/", no "..", no "." or empty parts, no backslashes, no symlinks.
#   Every regular file under update_20261017/ except the manifest itself must be listed.
#
# /work must be a REAL directory owned by you (created by the owner's root phase:
#   sudo bash setup_wsl_ubuntu2404.sh root). It must not be a symlink and must not be on /mnt/c.
# Exit code 10 = the owner must do something first (the message says what).
# Not run on a real WSL yet: the overlay's manifest handling was tested on the Mac with sample trees only.

set -uo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
HERE="$(dirname "$SCRIPT_PATH")"

readonly GH_URL=https://github.com/futureLabKezad/bumblebee-students.git   # public repository (checked 17.10)
readonly BACKUP_BRANCH=backup/bbsim-complete-2026-10-15
readonly BACKUP_SNAPSHOT_COMMIT=1c2ba48aa8a1e1d107d12247f2d37252b880b8ce    # 15.10 snapshot commit (the update commit is its child)
readonly REPO_BRANCH=feat/sim-trial
readonly REPO_COMMIT=b31ca69c174a360273f75a5257ced0a5ac56bd3b
BACKUP_DIR="${BACKUP_DIR:-$HOME/bumblebee-backup}"
REPO_DIR="${REPO_DIR:-$HOME/bumblebee-students}"
readonly WORK=/work
# sha256 of the snapshot's own manifest files as committed in 1c2ba48 (pinned here so a changed
# branch cannot silently swap the archive):
readonly SHA_SHA256SUMS_JSON=e41e12d658f5b9ca72e3f4b9902c20135a9fad7b755df4ca30f1f046b33cb1c5
readonly SHA_FILES_JSON=f127e7d4a285f5be73896d4762c213237aecfd1afd27971ad34de8ddef0bacc2
readonly SHA_VERIFY_SNAPSHOT=222c48383a2caf6594c055683244b9af568904c0c17aa66c4a8204d0e5fa2fcf
readonly STAMP_EXTRACT="$WORK/.pc_restore_extract_ok"
readonly STAMP_OVERLAY="$WORK/.pc_restore_overlay_ok"
DOCS_DIR="${DOCS_DIR:-$HOME/bumblebee-workspace-docs}"    # the 4 workspace-root documents (outside bbsim-work)

log() { echo "[restore $(date +%H:%M:%S)] $*"; }
warn() { echo "[restore $(date +%H:%M:%S)] WARNING: $*" >&2; }
die() { echo "[restore $(date +%H:%M:%S)] ERROR: $*" >&2; exit 1; }
need_owner() { echo "" >&2; echo "=== NEEDS THE OWNER (exit 10) ===" >&2; echo "$*" >&2; exit 10; }
sha_of() { sha256sum "$1" | cut -d' ' -f1; }
check_sha() { [ -f "$1" ] || die "missing: $1"; [ "$(sha_of "$1")" = "$2" ] || die "SHA256 mismatch: $1 (expected $2)"; }

[ "$(id -u)" != 0 ] || die "run as the normal user, not with sudo"

pc_inv() {
  local p
  if [ -f "$WORK/.pc_inventory_dir" ]; then p="$(cat "$WORK/.pc_inventory_dir")"
  else p="$WORK/pc_inventory_$(date +%Y%m%d)"; echo "$p" > "$WORK/.pc_inventory_dir"; fi
  mkdir -p "$p"; echo "$p"
}

require_work() {
  if [ -L "$WORK" ]; then
    die "$WORK is a symlink. It must be a real directory (trial code resolve()s /work paths). Ask the owner; do not work around it."
  fi
  [ -d "$WORK" ] || need_owner "There is no $WORK yet. Owner, in a SECOND Ubuntu window (not Claude's window; password typed there, once):
  sudo bash $HERE/setup_wsl_ubuntu2404.sh root
(or only the folder step:  sudo bash $HERE/setup_wsl_ubuntu2404.sh step r02_dirs )"
  [ -w "$WORK" ] && [ "$(stat -c %U "$WORK")" = "$(id -un)" ] \
    || need_owner "$WORK is not owned by $(id -un). Owner, in a SECOND Ubuntu window: sudo bash $HERE/setup_wsl_ubuntu2404.sh step r02_dirs"
  local fs; fs="$(findmnt -n -o FSTYPE -T "$WORK" || true)"
  [ "$fs" = ext4 ] || warn "$WORK is on '$fs', expected ext4 (never /mnt/c: slow, CRLF and permission problems)"
  if [ -L "$HOME/bbsim-work" ]; then
    [ "$(readlink "$HOME/bbsim-work")" = "$WORK" ] || die "~/bbsim-work points to $(readlink "$HOME/bbsim-work"), expected $WORK"
  elif [ -e "$HOME/bbsim-work" ]; then
    die "~/bbsim-work exists and is not a link to $WORK; move it aside (never delete) and re-run"
  else
    ln -s "$WORK" "$HOME/bbsim-work"; log "linked ~/bbsim-work -> $WORK"
  fi
}

do_clone() {
  if [ -d "$BACKUP_DIR/.git" ]; then
    local br; br="$(git -C "$BACKUP_DIR" rev-parse --abbrev-ref HEAD)"
    [ "$br" = "$BACKUP_BRANCH" ] || die "$BACKUP_DIR is on branch '$br', expected $BACKUP_BRANCH"
    log "using existing clone $BACKUP_DIR (HEAD $(git -C "$BACKUP_DIR" rev-parse HEAD))"
  elif [ -e "$BACKUP_DIR" ]; then
    die "$BACKUP_DIR exists but is not a git clone; move it aside (never delete) and re-run"
  else
    log "cloning $BACKUP_BRANCH (single branch, depth 1, ~1.4 GB) into $BACKUP_DIR"
    # core.autocrlf=false: any CRLF conversion would break the bash scripts and every SHA pin.
    git -c core.autocrlf=false clone --depth 1 --single-branch --branch "$BACKUP_BRANCH" "$GH_URL" "$BACKUP_DIR" \
      || die "clone failed (network? The repository was public on 17.10; if it asks for a login, the owner logs in himself)"
  fi
  [ "$(git -C "$BACKUP_DIR" config --get core.autocrlf || echo false)" != true ] || die "core.autocrlf=true in $BACKUP_DIR: re-clone with -c core.autocrlf=false"
  git -C "$BACKUP_DIR" log -1 --format='HEAD %H %ad %s' | cat
  [ "$(git -C "$BACKUP_DIR" rev-parse HEAD)" != "$BACKUP_SNAPSHOT_COMMIT" ] \
    || warn "HEAD is still the 15.10 snapshot commit: the 17.10 update (update_20261017/) has not been pushed yet"
  check_sha "$BACKUP_DIR/SHA256SUMS.json" "$SHA_SHA256SUMS_JSON"
  check_sha "$BACKUP_DIR/FILES.json" "$SHA_FILES_JSON"
  check_sha "$BACKUP_DIR/verify_snapshot.py" "$SHA_VERIFY_SNAPSHOT"
  log "snapshot manifests match the 15.10 commit; checking the 21 archive parts (reads 1.35 GB)"
  (cd "$BACKUP_DIR" && python3 -I verify_snapshot.py) || die "verify_snapshot.py failed on the archive parts"
  if [ -d "$BACKUP_DIR/update_20261017/bbsim-work" ]; then
    log "update_20261017 present: $(find "$BACKUP_DIR/update_20261017" -type f | wc -l) files"
    [ -f "$BACKUP_DIR/update_20261017/MANIFEST_SHA256.json" ] || warn "update_20261017/MANIFEST_SHA256.json is missing: the overlay step will refuse to run"
    if grep -rlI $'\r' "$BACKUP_DIR/update_20261017/bbsim-work/pc_handover_20261017/setup" 2>/dev/null | grep -q .; then
      die "CRLF line endings found in the update's setup scripts (Windows conversion?): re-clone inside WSL"
    fi
  else
    warn "update_20261017/bbsim-work is missing in this clone: the overlay step cannot run yet"
  fi
}

do_repo() {
  if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" remote get-url origin | grep -q 'futureLabKezad/bumblebee-students' || die "$REPO_DIR is not a clone of futureLabKezad/bumblebee-students"
    log "using existing clone $REPO_DIR"
  elif [ -e "$REPO_DIR" ]; then
    die "$REPO_DIR exists but is not a git clone; move it aside (never delete) and re-run"
  else
    log "cloning $REPO_BRANCH into $REPO_DIR"
    git -c core.autocrlf=false clone --single-branch --branch "$REPO_BRANCH" "$GH_URL" "$REPO_DIR" || die "clone failed"
  fi
  git -C "$REPO_DIR" cat-file -e "$REPO_COMMIT^{commit}" 2>/dev/null \
    || git -C "$REPO_DIR" fetch --quiet origin "$REPO_BRANCH" \
    || true
  git -C "$REPO_DIR" cat-file -e "$REPO_COMMIT^{commit}" 2>/dev/null || die "commit $REPO_COMMIT not found on $REPO_BRANCH (branch rewritten?): ask the owner"
  [ -z "$(git -C "$REPO_DIR" status --porcelain)" ] || die "$REPO_DIR has local changes; it must be clean (do not discard them: ask)"
  if [ "$(git -C "$REPO_DIR" rev-parse HEAD)" != "$REPO_COMMIT" ]; then
    warn "$REPO_BRANCH has moved on from $REPO_COMMIT; checking out $REPO_COMMIT (detached) for parity with the Mac VM"
    git -C "$REPO_DIR" checkout --quiet --detach "$REPO_COMMIT"
  fi
  log "$REPO_DIR at $(git -C "$REPO_DIR" rev-parse HEAD), clean"
  if [ -L /repo ] && [ "$(readlink /repo)" = "$REPO_DIR" ]; then log "/repo -> $REPO_DIR ok"
  else warn "/repo is not yet a link to $REPO_DIR (the owner's root phase step r02_dirs creates it)"; fi
}

do_extract() {
  require_work
  if [ -f "$STAMP_EXTRACT" ]; then log "already extracted and verified: $(cat "$STAMP_EXTRACT")"; return 0; fi
  [ -f "$BACKUP_DIR/verify_snapshot.py" ] || die "no clone at $BACKUP_DIR: run '$0 clone' first"
  # /work may only contain the PC inventory written by the root phase.
  local unexpected; unexpected="$(cd "$WORK" && ls -A | grep -vE '^(pc_inventory_[0-9]+|\.pc_inventory_dir|\.pc_[A-Za-z0-9_]+)$' || true)"
  [ -z "$unexpected" ] || die "$WORK already contains: $(echo "$unexpected" | tr '\n' ' ')- refusing to extract over it. Check what it is (never delete)."
  local avail; avail="$(df -BG --output=avail "$WORK" | tail -1 | tr -dc 0-9)"
  [ "$avail" -ge 15 ] || die "only ${avail} GB free; the extracted tree is ~8.7 GB (+ builds later)"
  log "extracting 21 parts into $WORK (~8.7 GB, as $(id -un): file owners become you)"
  # GNU tar; the archive was written by Python tarfile (hard links for identical files, symlinks kept).
  # shellcheck disable=SC2086
  cat "$BACKUP_DIR"/workspace.tar.gz.part* | tar -xzf - -C "$WORK" || die "tar extraction failed"
  log "verifying every restored entry against FILES.json (66 791 entries)"
  python3 -I "$BACKUP_DIR/verify_snapshot.py" "$WORK" || die "verify_snapshot.py $WORK failed: do not continue; keep the tree for inspection"
  echo "$(date -Is) from $BACKUP_DIR HEAD $(git -C "$BACKUP_DIR" rev-parse HEAD)" > "$STAMP_EXTRACT"
  log "15.10 snapshot restored and verified"
}

do_overlay() {
  require_work
  [ -f "$STAMP_EXTRACT" ] || die "extract first ('$0 extract')"
  local UPD="$BACKUP_DIR/update_20261017"
  local MAN="$UPD/MANIFEST_SHA256.json"
  [ -d "$UPD" ] || die "$UPD missing: the 17.10 update is not in the clone (git -C $BACKUP_DIR pull, or ask the Mac side to push it)"
  [ -f "$MAN" ] || die "$MAN missing: the update must ship a SHA256 per file (delta_files.json lists paths only and is not used)"
  if [ -L "$UPD" ] || [ -L "$MAN" ]; then die "$UPD or its manifest is a symlink: refusing"; fi
  local inv; inv="$(pc_inv)"
  mkdir -p "$DOCS_DIR"
  log "overlay by $MAN (sha256 $(sha_of "$MAN")): bbsim-work/* -> $WORK, workspace_root_docs/* -> $DOCS_DIR"
  # One Python program: validate the manifest, verify every source file, copy, verify every copy.
  # Nothing is deleted: a file that the update replaces is moved to $WORK/_overlay_replaced_20261017/<path>.
  local rc=0
  python3 -I - "$MAN" "$UPD" "$WORK" "$DOCS_DIR" "$inv/overlay_manifest_check.json" <<'PY' || rc=$?
import hashlib, json, os, re, shutil, sys, time
from pathlib import Path, PurePosixPath
man, upd, work, docs, report = map(Path, sys.argv[1:])
stamp = time.strftime('%Y%m%d_%H%M%S')
result = {'manifest': str(man), 'manifest_sha256': None, 'errors': [], 'copied': [], 'unchanged': [],
          'replaced_kept_in': [], 'verified_only': [], 'unlisted': []}
def fail(msg):
    result['errors'].append(msg)
def finish(code):
    report.write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in result.items()}))
    for e in result['errors'][:30]: print('ERROR:', ascii(e))
    sys.exit(code)
def digest(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
result['manifest_sha256'] = digest(man)
try:
    data = json.loads(man.read_text(encoding='utf-8'))
except Exception as e:
    fail(f'manifest is not valid JSON: {e}'); finish(1)
if not isinstance(data, dict) or set(data) != {'schema', 'root', 'files'}:
    fail('manifest must be exactly {"schema", "root", "files"}'); finish(1)
if data['schema'] != 1 or data['root'] != 'update_20261017' or not isinstance(data['files'], dict) or not data['files']:
    fail('manifest needs schema 1, root "update_20261017" and a non-empty "files" object'); finish(1)
HEX = re.compile(r'^[0-9a-f]{64}$')
def safe_rel(path):
    """Return the path parts if the manifest path is a clean relative POSIX path, else None."""
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path or path.startswith('/'):
        return None
    parts = path.split('/')
    if any(p in ('', '.', '..') for p in parts):
        return None
    if PurePosixPath(path).is_absolute() or re.match(r'^[A-Za-z]:', path):
        return None
    return parts
def no_symlink_below(base, parts):
    """True if no component of base/parts (after base) is a symlink."""
    cur = base
    for p in parts:
        cur = cur / p
        if cur.is_symlink():
            return False
    return True
upd_real = upd.resolve()
entries = []
for path, sha in data['files'].items():
    parts = safe_rel(path)
    if parts is None:
        fail(f'unsafe path refused: {path!r}'); continue
    if not isinstance(sha, str) or not HEX.match(sha):
        fail(f'bad sha256 for {path}: {sha!r}'); continue
    src = upd.joinpath(*parts)
    if not no_symlink_below(upd, parts) or not src.resolve().is_relative_to(upd_real):
        fail(f'symlink in the update refused: {path}'); continue
    if not src.is_file():
        fail(f'listed but missing or not a regular file: {path}'); continue
    if digest(src) != sha:
        fail(f'sha256 mismatch in the update: {path}'); continue
    entries.append((parts, sha))
listed = {'/'.join(p) for p, _ in entries} | {k for k in data['files'] if isinstance(k, str)}
for p in sorted(upd.rglob('*')):
    rel = p.relative_to(upd).as_posix()
    if rel == 'MANIFEST_SHA256.json' or p.is_dir() and not p.is_symlink():
        continue
    if p.is_symlink():
        fail(f'symlink in the update refused: {rel}'); continue
    if rel not in listed:
        result['unlisted'].append(rel)
if result['unlisted']:
    fail(f"{len(result['unlisted'])} file(s) in update_20261017 are not in the manifest (first: {result['unlisted'][0]})")
if result['errors']:
    finish(1)   # nothing has been copied yet
targets = {'bbsim-work': work, 'workspace_root_docs': docs}
keep = {'bbsim-work': work / '_overlay_replaced_20261017', 'workspace_root_docs': docs / f'_replaced_{stamp}'}
plan = []
for parts, sha in entries:
    top = parts[0]
    if top not in targets or len(parts) < 2:
        result['verified_only'].append('/'.join(parts)); continue   # verified, not copied anywhere
    base, rest = targets[top], parts[1:]
    dest = base.joinpath(*rest)
    base_real = base.resolve()
    parent = dest.parent
    # The destination must stay inside its base even through symlinks of the restored tree.
    probe = parent
    while not probe.exists():
        probe = probe.parent
    if not probe.resolve().is_relative_to(base_real):
        fail(f'destination leaves {base}: {dest}'); continue
    if dest.is_symlink() or (dest.exists() and not dest.is_file()):
        fail(f'destination is a symlink or not a regular file, refusing to replace it: {dest}'); continue
    anc = dest.parent; bad = None
    while anc != base and anc != anc.parent:
        if anc.is_symlink() or (anc.exists() and not anc.is_dir()):
            bad = anc; break
        anc = anc.parent
    if bad is not None:
        fail(f'a parent of the destination is a file or symlink, refusing: {bad}'); continue
    plan.append((parts, sha, top, rest, dest))
if result['errors']:
    finish(1)   # still nothing copied
try:
  for parts, sha, top, rest, dest in plan:
    src = upd.joinpath(*parts)
    if dest.is_file() and digest(dest) == sha:
        result['unchanged'].append(str(dest)); continue
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        k = keep[top].joinpath(*rest)
        if k.exists():
            k = k.with_name(k.name + '.' + stamp)
        k.parent.mkdir(parents=True, exist_ok=True)
        os.replace(dest, k)
        result['replaced_kept_in'].append(str(k))
    tmp = dest.with_name('.' + dest.name + '.overlay_tmp')
    shutil.copy2(src, tmp)
    os.replace(tmp, dest)
    result['copied'].append(str(dest))
except Exception as e:
    fail(f'copy stopped: {e!r} (files listed in "copied" were replaced; old versions kept in "replaced_kept_in")')
    finish(1)
for parts, sha, top, rest, dest in plan:
    if not dest.is_file() or dest.is_symlink() or digest(dest) != sha:
        fail(f'after copying, {dest} does not match the manifest')
finish(1 if result['errors'] else 0)
PY
  [ "$rc" = 0 ] || die "overlay refused or failed (exit $rc): STOP and read $inv/overlay_manifest_check.json"
  echo "$(date -Is) from $BACKUP_DIR HEAD $(git -C "$BACKUP_DIR" rev-parse HEAD) manifest $(sha_of "$MAN")" > "$STAMP_OVERLAY"
  log "17.10 update overlaid and verified ($inv/overlay_manifest_check.json). Replaced 15.10 versions (if any): $WORK/_overlay_replaced_20261017"
  log "workspace-root documents: $DOCS_DIR"
}

do_accept() {
  require_work
  local I="$WORK/parallel_work/20261015/integration" inv rc=0 out
  inv="$(pc_inv)"; out="$inv/restore_acceptance_$(date +%Y%m%d_%H%M%S).txt"
  {
    echo "== check_isolation.py (expected: ok true, 187 shared files; after the PC rebuild exactly ONE known"
    echo "   difference is expected: ws_package1b/install/bumblebee/lib/bumblebee/simple_offboard = aarch64 pin)"
    (cd "$WORK" && python3 -I -B parallel_work/20261015/integration/check_isolation.py) > "$inv/check_isolation_latest.json"
    python3 -I - "$inv/check_isolation_latest.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
errs = r.get('errors', [])
known = [e for e in errs if e.get('file') == 'ws_package1b/install/bumblebee/lib/bumblebee/simple_offboard']
other = [e for e in errs if e not in known]
print('shared_files_checked', r.get('shared_files_checked'), 'ok', r.get('ok'), 'errors', len(errs), 'known_simple_offboard', len(known))
for e in other: print('UNEXPECTED', e)
sys.exit(0 if r.get('shared_files_checked') == 187 and not other else 1)
PY
    echo "== flight_trial_02 / 03 SHA256SUMS.txt"
    (cd "$I/flight_trial_02" && sha256sum -c --quiet SHA256SUMS.txt) && echo "flight_trial_02 OK"
    (cd "$I/flight_trial_03" && sha256sum -c --quiet SHA256SUMS.txt) && echo "flight_trial_03 OK"
    echo "== test_rtf_guard.py (expected 15 PASS, 0 FAIL in each)"
    python3 -I -B "$I/flight_trial_02/tests/test_rtf_guard.py"
    python3 -I -B "$I/flight_trial_03/tests/test_rtf_guard.py"
    echo "== test_verifier.py (expected: Ran 17 tests ... OK; it was last run with Python 3.9, now 3.12)"
    (cd "$I/flight_verification_01" && python3 -B -m unittest test_verifier 2>&1 | tail -3)
    echo "== pinned inputs"
    sha256sum "$WORK/sim/bumblebee_model/models/bumblebee/model.sdf" "$WORK/sim/bumblebee_model/airframes/4030_gz_bumblebee" \
      "$WORK/sim/bumblebee_model/airframes/4031_gz_bumblebee_demo" "$WORK/sim/worlds/aruco_map/map.input.txt" \
      "$I/field_measurements_01/generated/map.input.txt" "$WORK/sim/ros_stack/mavros-2.14.0.tar.gz" \
      "$WORK/sim/ros_stack/geoids/egm96-5.pgm" "$I/combined_03/manifest.json" "$I/flight_trial_02/supervisor.py"
    echo "== CRLF check of shell scripts used by the trials (must print nothing)"
    grep -lI $'\r' "$WORK"/sim/*.sh "$I"/flight_trial_0*/*.sh "$I"/rtf_probe_01/*.sh 2>/dev/null || true
  } 2>&1 | tee "$out"
  # Hard pass/fail on the parts that must hold:
  (cd "$WORK" && python3 -I -B parallel_work/20261015/integration/check_isolation.py > /dev/null) \
    || grep -q 'known_simple_offboard 1' "$out" || { warn "check_isolation has unexpected errors"; rc=1; }
  grep -q 'UNEXPECTED' "$out" && rc=1
  grep -q 'shared_files_checked 187 ' "$out" || rc=1
  grep -q 'flight_trial_02 OK' "$out" && grep -q 'flight_trial_03 OK' "$out" || rc=1
  [ "$(grep -c '^FAIL ' "$out")" = 0 ] && [ "$(grep -c '^PASS ' "$out")" = 30 ] || rc=1
  grep -q 'Ran 17 tests' "$out" && grep -qx 'OK' "$out" || rc=1
  local want
  for want in 474fd2962efa69744ba747724e1e2c752179851a7b29c289b6fd60da69464729 c960b610480842c6207cc34b7ec8feef6070262210d9f217ea2303e28bf76279 \
              aae41a117943a520d37e56bac95da10da182ef08e70624087cdd703b5dacab3c 528b5adb467dc91e819e0c4cb9a5ff44439319fff23c3293799b8ee3fe43e611 \
              d52d2e07a9b511a31444de360161857f07d7ab7098b1093495f6e9e845d7a060 c4b25a03ec5845cec4778a54b580aeda676363f2205a89137e8677b2337af3ec \
              5262098fe1545462cf4d7e861324a5b7fe11fada3fca7225df0c32597a34a146 95d84234b9665a8ee4122d18069c79f1100c556217d9a241eacbecb64c63be53; do
    grep -q "^$want " "$out" || { warn "pinned sha $want not found"; rc=1; }
  done
  [ "$(grep -c "^528b5adb467dc91e819e0c4cb9a5ff44439319fff23c3293799b8ee3fe43e611 " "$out")" = 2 ] || rc=1
  if grep -lI $'\r' "$WORK"/sim/*.sh "$I"/flight_trial_0*/*.sh "$I"/rtf_probe_01/*.sh 2>/dev/null | grep -q .; then
    warn "CRLF line endings in trial shell scripts"; rc=1
  fi
  if [ "$rc" = 0 ]; then log "ACCEPTANCE OK - saved $out"; else die "ACCEPTANCE FAILED - see $out (do not continue to the build before this is understood)"; fi
}

main() {
  local cmd=${1:-}
  case "$cmd" in
    all) do_clone; do_repo; do_extract; do_overlay; do_accept ;;
    clone) do_clone ;;
    repo) do_repo ;;
    extract) do_extract ;;
    overlay) do_overlay ;;
    accept) do_accept ;;
    *) sed -n '2,/^$/p' "$SCRIPT_PATH"; exit 2 ;;
  esac
}

main "$@"
