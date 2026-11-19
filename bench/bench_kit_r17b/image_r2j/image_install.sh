#!/bin/bash
# МЕНЯЕТ ДРОН (Claude, 09.11.2026, ЗАГОТОВКА, r4). Запускается на Pi из 05_install_r2j.cmd, только после проверки условий на ПК.
# Что делает: проверяет SHA256 файлов в загруженной папке, сохраняет копии заменяемых файлов в BACKUP_ROOT/<метка>, ставит файлы
# по манифесту, проверяет SHA256 и режим на месте. Как вернуть: image_rollback.sh (06_rollback_r2j.cmd). Ничего не удаляет.
# Аргумент: папка с payload/, image_manifest.final.tsv и image_target.conf (загружена установщиком).
# Манифест: путь<TAB>sha256[<TAB>режим]. Режим: три цифры (755) или четыре с нулём (0755); setuid/setgid/sticky не принимаются.
set -u
set -o pipefail
if [ "$(hostname)" != "bumblebee-20ec" ]; then echo "=== STOP: wrong host $(hostname)"; exit 1; fi
S="${1:-}"
[ -d "$S" ] || { echo "=== STOP: no upload folder"; exit 1; }
# A-8 (r2, r3): файлы с Windows могут быть с \r и с BOM (UTF-8). Работаем с очищенными копиями, оригиналы не меняем.
clean() { tr -d '\r' < "$1" | sed -e '1s/^\xef\xbb\xbf//' -e '$a\' > "$2"; }   # r4 (Н-3): добавляет завершающий перевод строки, иначе последняя строка манифеста терялась
[ -f "$S/image_target.conf" ] || { echo "=== STOP: no image_target.conf"; exit 1; }
clean "$S/image_target.conf" "$S/.target.lf" || { echo "=== STOP: cannot clean image_target.conf"; exit 1; }
# shellcheck disable=SC1090
. "$S/.target.lf" 2>/dev/null
case "${DEST_ROOT:-TBD}${BACKUP_ROOT:-TBD}" in *TBD*) echo "=== STOP: DEST_ROOT or BACKUP_ROOT is TBD"; exit 1;; esac
case "$DEST_ROOT" in /*) ;; *) echo "=== STOP: DEST_ROOT must be an absolute path: $DEST_ROOT"; exit 1;; esac
case "$BACKUP_ROOT" in /*) ;; *) echo "=== STOP: BACKUP_ROOT must be an absolute path: $BACKUP_ROOT"; exit 1;; esac
PAY="$S/payload"
[ -f "$S/image_manifest.final.tsv" ] || { echo "=== STOP: no manifest"; exit 1; }
clean "$S/image_manifest.final.tsv" "$S/.manifest.lf" || { echo "=== STOP: cannot clean manifest"; exit 1; }
MAN="$S/.manifest.lf"
norm() { printf '%o' "$((8#$1))"; }   # 0755 и 755 одно и то же
n=0
while IFS=$'\t' read -r path sha mode; do
  case "$path" in ''|'#'*) continue;; esac
  case "$path" in /*|*..*) echo "=== STOP: unsafe path $path"; exit 1;; esac
  # r3 (замечание проверки 11.11): путь с сегментом «.» или двойным «/» (./a, a/./b, a//b, a/.) указывал бы на тот же файл, что «a»; проверка повторов по тексту его не поймала бы. Такие пути не принимаются.
  case "$path" in ./*|*/./*|*//*|*/.) echo "=== STOP: unsafe path (segment . or //): $path"; exit 1;; esac
  # решение чата 1 (22:00): fcu_detect.py образом не ставится (на дроне исправленный fcu_detect_fix_01, в src r2j прежний с ошибкой порта)
  case "$(printf '%s' "$path" | tr 'A-Z' 'a-z')" in fcu_detect.py|*/fcu_detect.py) echo "=== STOP: fcu_detect.py must not be installed by the image (on the drone the fixed one stays), nothing done: $path"; exit 1;; esac
  case "${mode:-000}" in [0-7][0-7][0-7]|0[0-7][0-7][0-7]) ;; *) echo "=== STOP: bad mode '${mode:-}' for $path"; exit 1;; esac
  # r3 (O-3): символьная ссылка на месте файла не поддерживается (режим и резерв читались бы неверно). Остановка ДО любых изменений.
  [ ! -L "$DEST_ROOT/$path" ] || { echo "=== STOP: $DEST_ROOT/$path is a symbolic link, not supported, nothing done"; exit 1; }
  [ -f "$PAY/$path" ] || { echo "=== STOP: missing in upload: $path"; exit 1; }
  got=$(sha256sum "$PAY/$path" | cut -d' ' -f1)
  [ "$got" = "$sha" ] || { echo "=== STOP: sha256 mismatch in upload: $path"; exit 1; }
  n=$((n+1))
done < "$MAN"
[ "$n" -gt 0 ] || { echo "=== STOP: manifest is empty"; exit 1; }
# r4: один путь дважды в манифесте не допускается (резерв и подсчёт были бы неверны)
dup=$(grep -v -E '^(#|[[:space:]]*$)' "$MAN" | cut -f1 | sort | uniq -d | head -1)
[ -z "$dup" ] || { echo "=== STOP: path listed twice in the manifest: $dup"; exit 1; }
STAMP=$(date +%Y%m%d_%H%M%S)
B="$BACKUP_ROOT/$STAMP"
[ ! -e "$B" ] || { echo "=== STOP: $B already exists, nothing done"; exit 1; }
mkdir -p "$B/files" || { echo "=== STOP: cannot create $B"; exit 1; }
: > "$B/NEW_FILES.txt"
while IFS=$'\t' read -r path sha mode; do
  case "$path" in ''|'#'*) continue;; esac
  d="$DEST_ROOT/$path"
  if [ -e "$d" ]; then
    mkdir -p "$B/files/$(dirname "$path")"
    cp -p "$d" "$B/files/$path" || { echo "=== STOP: backup of $path failed, nothing installed"; echo "backup of $path failed" > "$B/BACKUP_FAILED"; exit 2; }
  else
    echo "$path" >> "$B/NEW_FILES.txt"
  fi
done < "$MAN"
nold=$(( n - $(grep -c . "$B/NEW_FILES.txt") ))
( cd "$B/files" && find . -type f -exec sha256sum {} + ) > "$B/files.sha256"
cp "$MAN" "$B/installed_manifest.tsv"
# r4 (Н-1): список резервных файлов должен быть записан целиком, иначе ничего не ставим
if [ "$(wc -l < "$B/files.sha256")" != "$nold" ]; then echo "=== STOP: backup list has $(wc -l < "$B/files.sha256") entries, expected $nold, nothing installed"; echo "backup list incomplete" > "$B/BACKUP_FAILED"; exit 2; fi
echo "=== backup $B: $(wc -l < "$B/files.sha256") old files, $(wc -l < "$B/NEW_FILES.txt") new files"
bad=0
while IFS=$'\t' read -r path sha mode; do
  case "$path" in ''|'#'*) continue;; esac
  d="$DEST_ROOT/$path"
  mkdir -p "$(dirname "$d")"
  # A-7: бит исполнения. Порядок: режим из 3-й колонки манифеста; иначе режим старого файла на дроне; иначе 755 для файла с #! в первой строке; иначе 644.
  if [ -n "${mode:-}" ]; then want="$mode"
  elif [ -e "$d" ]; then want=$(stat -L -c %a "$d")
  elif [ "$(head -c 2 "$PAY/$path")" = '#!' ]; then want=755
  else want=644; fi
  if cp "$PAY/$path" "$d.bbnew" && chmod "$want" "$d.bbnew" && mv -f "$d.bbnew" "$d"; then
    got_mode=$(stat -c %a "$d")
    [ "$(norm "$got_mode")" = "$(norm "$want")" ] || { echo "=== FAIL: mode after install $got_mode, expected $want: $path"; bad=1; }
    got=$(sha256sum "$d" | cut -d' ' -f1)
    [ "$got" = "$sha" ] || { echo "=== FAIL: sha256 after install differs: $path"; bad=1; }
  else
    echo "=== FAIL: could not install $path"; bad=1
  fi
done < "$MAN"
if [ "$bad" != "0" ]; then echo "=== INSTALL FAILED. Run 06_rollback_r2j.cmd. Backup: $B"; exit 3; fi
echo "BB_IMAGE_INSTALL_DONE $STAMP files=$n"
