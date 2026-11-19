#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 12.11.2026, набор r6; блок «Конец замера» процедуры PI_PERF без pgrep -f). Проверка, что после фаз A, C, A2 стек как был.
# Процессов замера не осталось; в стеке ровно по одному main_camera_fix, aruco_detect, mavros_node; троттлинг и температура; число «process has died» в /tmp/bumblebee.log
# (только чтение файла). Аргумент: метка ГГГГММДД_ЧЧММСС (только для вывода). Ничего не пишет. Итог: строка «КАМЕРА: ЗАМЕР ЗАКОНЧЕН, СТЕК КАК БЫЛ — ГОТОВО»
# или «КОНЕЦ ЗАМЕРА НЕ ГОТОВО: причина», последняя строка BB_R6END_DONE.
# Только для тестов на ПК: BB_TEST_PROC, BB_TEST_LOG.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6END_MARK
export LC_ALL=C.UTF-8
PROC="${BB_TEST_PROC:-/proc}"; LOGF="${BB_TEST_LOG:-/tmp/bumblebee.log}"
STAMP="${1:-}"
echo "END_STAMP $STAMP $(date '+%F %T %z')"
bad=""
m=""
for d in "$PROC"/[0-9]*; do
  c=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null) || continue
  case "$c" in *BB_R6*) continue;; esac
  case "$c" in *aruco_detect_bench*|*main_camera_fix_full*|*bench_recorder.py*|*raw_layout_check.py*) m="$m ${d##*/}"; echo "END_MEAS_LEFT ${d##*/} $(printf '%s' "$c" | cut -c1-160)";; esac
done
[ -z "$m" ] || bad="$bad процессы_замера_ещё_работают(подождите_минуту_и_повторите)"
for p in '__node:=main_camera_fix ' '__node:=aruco_detect ' 'mavros_node'; do
  n=0
  for d in "$PROC"/[0-9]*; do
    c=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null) || continue
    case "$c" in *BB_R6*) continue;; esac
    case "$c" in *"$p"*) n=$((n+1));; esac
  done
  echo "END_STACK '$p' $n"
  [ "$n" = 1 ] || bad="$bad не_ровно_один($p:$n)"
done
echo "END_THROTTLED $(vcgencmd get_throttled 2>&1)"
echo "END_TEMP $(vcgencmd measure_temp 2>&1)"
echo "END_DIED $(grep -c 'process has died' "$LOGF" 2>/dev/null)"
if [ -z "$bad" ]; then echo "КАМЕРА: ЗАМЕР ЗАКОНЧЕН, СТЕК КАК БЫЛ — ГОТОВО"; else echo "КОНЕЦ ЗАМЕРА НЕ ГОТОВО:$bad"; fi
echo "BB_R6END_DONE"
