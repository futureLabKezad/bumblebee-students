#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 12.11.2026, набор r6). Есть ли на Pi папка ~/bench_ws/incoming/camera_fullrow_r6 с тремя файлами замера камеры полных строк и верны ли их sha256.
# Файлы (их суммы подставляет ПК вместо строки #@@CAMFILES@@): camera_fix.py (кандидат dabd5076), raw_layout_check.py, bench_recorder.py, SHA256SUMS_camera_fullrow.txt.
# Ничего не пишет, не копирует и не удаляет. Итог: CI_STATE absent | ok | bad, последняя строка BB_R6CI_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6CI_MARK
I="$HOME/bench_ws/incoming/camera_fullrow_r6"
FILES='
#@@CAMFILES@@
'
echo "CI_DIR $I"
if [ ! -e "$I" ] && [ ! -L "$I" ]; then echo "CI_STATE absent"; echo "BB_R6CI_DONE"; exit 0; fi
if [ -L "$I" ] || [ ! -d "$I" ]; then echo "CI_STATE bad (не папка или ссылка)"; echo "BB_R6CI_DONE"; exit 0; fi
bad=0; n=0
while read -r want name; do
  case "$want" in ''|\#*) continue;; esac
  n=$((n+1))
  f="$I/$name"
  if [ -L "$f" ] || [ ! -f "$f" ]; then echo "CI_FILE $name MISSING"; bad=1; continue; fi
  got=$(sha256sum "$f" 2>/dev/null | cut -c1-64)
  if [ "$got" = "$want" ]; then echo "CI_FILE $name OK"; else echo "CI_FILE $name DIFF got=$got"; bad=1; fi
done <<< "$FILES"
[ "$n" -ge 4 ] || { echo "CI_FILE список пуст или неполон ($n)"; bad=1; }
find "$I" -mindepth 1 -maxdepth 2 2>/dev/null | while IFS= read -r x; do
  b="${x#$I/}"
  printf '%s\n' "$FILES" | awk '{print $2}' | grep -qxF "$b" || echo "CI_EXTRA $b"
done
if [ "$bad" = 0 ]; then echo "CI_STATE ok"; else echo "CI_STATE bad"; fi
echo "BB_R6CI_DONE"
