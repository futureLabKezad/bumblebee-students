#!/bin/bash
# МЕНЯЕТ ДРОН (Claude, 10.11.2026, набор r2; решение чата 1 в 19:45). Откат сборки MAVROS bp02 на Pi (12_otkat_mavros_bp02.cmd): переносит собранное в сторону, ничего не удаляет. Запускается только владельцем.
# Что делает: ~/bench_ws/mavros, ~/bench_ws/mavros_deps, ~/bench_ws/mavros_src_mode.txt, ~/bench_ws/incoming/rc3_mavros, журналы и отпечатки сборки (build_mavros_*.log, mavros_watch_*.txt, mavros_time_*.txt, mavros_build_*.txt,
# MAVROS_ARM64_*.txt, mavros_install_diff.txt) переносятся (mv) в новую папку ~/bench_ws/_aside_mavros_<метка>/. Штатный MAVROS из apt не тронут (его сборка не меняла), start_bumblebee.sh не менялся.
# Отказывается (STOP, ничего не перенесено), если: идёт сборка (colcon, cmake, make, cc1plus); start_bumblebee.sh уже подключает оверлей (в нём есть bench_ws/mavros): сначала его отключает шаг подключения (m4), не этот;
# нечего переносить (нет ~/bench_ws/mavros); папка назначения уже есть. Последняя строка при успехе: BB_ASIDE_DONE <папка>.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_ASIDE_MARK
busy=$(ps -eo comm= 2>/dev/null | grep -c -E '^(colcon|cmake|make|cc1plus)$')
[ "${busy:-0}" -eq 0 ] || { echo "STOP: идёт сборка ($busy процессов): сначала остановить сборку (m2_stop.sh), ничего не перенесено"; exit 1; }
if grep -q 'bench_ws/mavros' "$HOME/start_bumblebee.sh" 2>/dev/null; then echo "STOP: start_bumblebee.sh подключает оверлей bench_ws/mavros: сначала отключить подключение, ничего не перенесено"; exit 1; fi
[ -d "$HOME/bench_ws/mavros" ] || { echo "STOP: нет $HOME/bench_ws/mavros, нечего переносить"; exit 1; }
STAMP=$(date +%Y%m%d_%H%M%S)
A="$HOME/bench_ws/_aside_mavros_$STAMP"
[ ! -e "$A" ] || { echo "STOP: $A уже есть, ничего не перенесено"; exit 1; }
mkdir -p "$A" || { echo "STOP: не создать $A"; exit 1; }
n=0
for p in "$HOME/bench_ws/mavros" "$HOME/bench_ws/mavros_deps" "$HOME/bench_ws/mavros_src_mode.txt" "$HOME/bench_ws/incoming/rc3_mavros" "$HOME"/bench_ws/build_mavros_*.log "$HOME"/bench_ws/mavros_watch_*.txt "$HOME"/bench_ws/mavros_time_*.txt "$HOME"/bench_ws/mavros_build_*.txt "$HOME"/bench_ws/MAVROS_ARM64_*.txt "$HOME"/bench_ws/mavros_install_diff.txt; do
  [ -e "$p" ] || continue
  mv "$p" "$A/" && { echo "ASIDE $p"; n=$((n+1)); } || { echo "FAIL не перенесено: $p"; exit 2; }
done
echo "BB_ASIDE_DONE $A files=$n"
