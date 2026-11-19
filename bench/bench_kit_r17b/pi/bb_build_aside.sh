#!/bin/bash
# МЕНЯЕТ ДРОН (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58). Откат сборки bumblebee r2j на Pi (14_otkat_sborki_bumblebee.cmd): переносит ~/bench_ws/r2j и журналы сборки в ~/bench_ws/_aside_bb_r2j_<метка>/, ничего не удаляет.
# ~/ros2_ws (прежняя сборка и исходники) не трогается: сборка r2j шла в отдельном оверлее. Исходники образа в ~/ros2_ws/src возвращает откат образа 06_rollback_r2j.cmd, а не этот файл.
# Отказывается (STOP, ничего не перенесено): идёт сборка (colcon, cmake, make, cc1plus); start_bumblebee.sh подключает оверлей (в нём есть bench_ws/r2j): сначала 17_otkljuchit_overlay.cmd; нечего переносить; папка назначения уже есть.
# Последняя строка при успехе: BB_BBASIDE_DONE <папка> files=<число>.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_BBASIDE_MARK
busy=$(ps -eo comm= 2>/dev/null | grep -c -E '^(colcon|cmake|make|cc1plus)$')
[ "${busy:-0}" -eq 0 ] || { echo "STOP: идёт сборка ($busy процессов), ничего не перенесено"; exit 1; }
if grep -q 'bench_ws/r2j' "$HOME/start_bumblebee.sh" 2>/dev/null; then echo "STOP: start_bumblebee.sh подключает оверлей bench_ws/r2j: сначала отключить (17_otkljuchit_overlay.cmd), ничего не перенесено"; exit 1; fi
[ -d "$HOME/bench_ws/r2j" ] || { echo "STOP: нет $HOME/bench_ws/r2j, нечего переносить"; exit 1; }
STAMP=$(date +%Y%m%d_%H%M%S)
A="$HOME/bench_ws/_aside_bb_r2j_$STAMP"
[ ! -e "$A" ] || { echo "STOP: $A уже есть, ничего не перенесено"; exit 1; }
mkdir -p "$A" || { echo "STOP: не создать $A"; exit 1; }
n=0
for p in "$HOME/bench_ws/r2j" "$HOME"/bench_ws/build_r2j_*.log; do
  [ -e "$p" ] || continue
  mv "$p" "$A/" && { echo "ASIDE $p"; n=$((n+1)); } || { echo "FAIL не перенесено: $p"; exit 2; }
done
echo "BB_BBASIDE_DONE $A files=$n"
