#!/bin/bash
# МЕНЯЕТ ДРОН (Claude, 09.11.2026, ЗАГОТОВКА, r4). Откат установки образа из резервной копии BACKUP_ROOT/<метка>.
# Старые файлы возвращаются на место (SHA256 проверяется), файлы, которых раньше не было, переносятся в <метка>/rolled_back_new, не удаляются.
# Перед откатом то, что стоит на дроне, сохраняется в <метка>/before_rollback_<время> (A-9).
# Аргументы: папка с image_target.conf (загружена установщиком) и необязательно метка копии YYYYMMDD_HHMMSS (по умолчанию самая новая;
# если она неполная, STOP и явная метка предыдущей).
set -u
set -o pipefail
if [ "$(hostname)" != "bumblebee-20ec" ]; then echo "=== STOP: wrong host $(hostname)"; exit 1; fi
S="${1:-}"; WANT="${2:-}"
[ -d "$S" ] || { echo "=== STOP: no upload folder"; exit 1; }
# A-8: файл с Windows может быть с \r и с BOM; работаем с очищенной копией.
clean() { tr -d '\r' < "$1" | sed '1s/^\xef\xbb\xbf//' > "$2"; }
[ -f "$S/image_target.conf" ] || { echo "=== STOP: no image_target.conf"; exit 1; }
clean "$S/image_target.conf" "$S/.target.lf" || { echo "=== STOP: cannot clean image_target.conf"; exit 1; }
# shellcheck disable=SC1090
. "$S/.target.lf" 2>/dev/null
case "${DEST_ROOT:-TBD}${BACKUP_ROOT:-TBD}" in *TBD*) echo "=== STOP: DEST_ROOT or BACKUP_ROOT is TBD"; exit 1;; esac
case "$DEST_ROOT" in /*) ;; *) echo "=== STOP: DEST_ROOT must be an absolute path: $DEST_ROOT"; exit 1;; esac
case "$BACKUP_ROOT" in /*) ;; *) echo "=== STOP: BACKUP_ROOT must be an absolute path: $BACKUP_ROOT"; exit 1;; esac
STAMP=''
if [ -n "$WANT" ]; then
  case "$WANT" in [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]) STAMP="$WANT";; *) echo "=== STOP: bad backup label '$WANT' (expected YYYYMMDD_HHMMSS)"; exit 1;; esac
else
  # r4 (Н-2): берётся самая новая папка резерва. Если она неполная (установка упала на резервировании), тихо откатывать
  # более старую установку нельзя: STOP, метку нужно назвать явно.
  STAMP=$(ls -1 "$BACKUP_ROOT" 2>/dev/null | grep -E '^[0-9]{8}_[0-9]{6}$' | sort | tail -1)
fi
B="$BACKUP_ROOT/$STAMP"
if [ -n "$STAMP" ] && { [ ! -d "$B/files" ] || [ ! -f "$B/files.sha256" ] || [ -e "$B/BACKUP_FAILED" ]; }; then
  PREV=$(for c in $(ls -1 "$BACKUP_ROOT" 2>/dev/null | grep -E '^[0-9]{8}_[0-9]{6}$' | sort -r); do [ "$c" = "$STAMP" ] && continue; if [ -d "$BACKUP_ROOT/$c/files" ] && [ -f "$BACKUP_ROOT/$c/files.sha256" ] && [ ! -e "$BACKUP_ROOT/$c/BACKUP_FAILED" ]; then echo "$c"; break; fi; done)
  echo "=== STOP: the newest backup folder $STAMP is incomplete (the install there failed while saving old files; nothing was installed by it)."
  echo "=== The previous complete backup is: ${PREV:-none}. Tell Claude. To roll that one back on purpose run: 06_rollback_r2j.cmd ${PREV:-<label>}"
  exit 1
fi
[ -n "$STAMP" ] && [ -d "$B/files" ] && [ -f "$B/files.sha256" ] || { echo "=== STOP: no usable backup in $BACKUP_ROOT"; exit 1; }
[ ! -e "$B/ROLLED_BACK" ] || { echo "=== STOP: backup $STAMP was already rolled back"; exit 1; }
# r4 (Н-1): число записей в files.sha256 должно быть равно числу старых файлов по installed_manifest.tsv минус NEW_FILES.txt.
# Пустой список допустим только если старых файлов не было (установка только новых файлов) и в files/ ничего нет.
[ -f "$B/installed_manifest.tsv" ] && [ -f "$B/NEW_FILES.txt" ] || { echo "=== STOP: backup is missing installed_manifest.tsv or NEW_FILES.txt, nothing done"; exit 2; }
mn=$(grep -v -E '^(#|[[:space:]]*$)' "$B/installed_manifest.tsv" | grep -c . || true)
nn=$(tr -d '\r' < "$B/NEW_FILES.txt" | grep -c . || true)
sn=$(grep -c . "$B/files.sha256" || true)
fn=$(find "$B/files" -type f | grep -c . || true)
if [ "$sn" != "$((mn - nn))" ] || [ "$fn" != "$sn" ]; then echo "=== STOP: backup is inconsistent (manifest $mn, new $nn, listed $sn, files saved $fn), nothing done"; exit 2; fi
if [ -s "$B/files.sha256" ]; then
  ( cd "$B/files" && sha256sum -c --quiet "$B/files.sha256" ) || { echo "=== STOP: backup files are damaged, nothing done"; exit 2; }
fi
# A-9: перед откатом сохранить то, что стоит на дроне сейчас (установленную версию), чтобы откат тоже можно было отменить.
BR="$B/before_rollback_$(date +%Y%m%d_%H%M%S)"
[ ! -e "$BR" ] || { echo "=== STOP: $BR already exists, nothing done"; exit 1; }
mkdir -p "$BR/files" || { echo "=== STOP: cannot create $BR"; exit 1; }
while read -r sha path; do
  [ -n "$path" ] || continue
  p="${path#./}"; d="$DEST_ROOT/$p"
  if [ -e "$d" ]; then
    mkdir -p "$BR/files/$(dirname "$p")"
    cp -p "$d" "$BR/files/$p" || { echo "=== STOP: cannot save installed version of $p, nothing rolled back"; exit 2; }
  fi
done < "$B/files.sha256"
while IFS= read -r p; do
  [ -n "$p" ] || continue
  d="$DEST_ROOT/$p"
  if [ -e "$d" ]; then
    mkdir -p "$BR/files/$(dirname "$p")"
    cp -p "$d" "$BR/files/$p" || { echo "=== STOP: cannot save installed version of $p, nothing rolled back"; exit 2; }
  fi
done < <(tr -d '\r' < "$B/NEW_FILES.txt")
( cd "$BR/files" && find . -type f -exec sha256sum {} + ) > "$BR/files.sha256"
echo "=== installed version saved: $BR ($(wc -l < "$BR/files.sha256") files)"
bad=0; r=0
while read -r sha path; do
  [ -n "$path" ] || continue
  p="${path#./}"; d="$DEST_ROOT/$p"
  if cp -p "$B/files/$p" "$d.bbold" && mv -f "$d.bbold" "$d"; then r=$((r+1)); else echo "=== FAIL: cannot restore $p"; bad=1; fi
done < "$B/files.sha256"
mv_n=0
while IFS= read -r p; do
  [ -n "$p" ] || continue
  d="$DEST_ROOT/$p"
  if [ -e "$d" ]; then
    mkdir -p "$B/rolled_back_new/$(dirname "$p")"
    mv "$d" "$B/rolled_back_new/$p" && mv_n=$((mv_n+1)) || { echo "=== FAIL: cannot move aside $p"; bad=1; }
  fi
done < <(tr -d '\r' < "$B/NEW_FILES.txt")
if [ -s "$B/files.sha256" ]; then
  ( cd "$DEST_ROOT" && sed 's#  \./#  #' "$B/files.sha256" | sha256sum -c --quiet ) || { echo "=== FAIL: files at destination differ from backup"; bad=1; }
fi
if [ "$bad" != "0" ]; then echo "=== ROLLBACK INCOMPLETE. Do not fly. Tell Claude. Backup: $B"; exit 3; fi
date '+%F %T' > "$B/ROLLED_BACK"
echo "BB_IMAGE_ROLLBACK_DONE $STAMP restored=$r moved_aside=$mv_n saved_installed=$BR"
