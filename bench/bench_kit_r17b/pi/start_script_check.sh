#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2; решение чата 1 в 20:10). Читает нынешний ~/start_bumblebee.sh на дроне, чтобы ПК сравнил его с известным по набору s0b (image_r2j\START_BUMBLEBEE_BASELINE_s0b.sh, sha256 58c14783…).
# Ничего не пишет на дрон, файлов на Pi не создаёт, ничего не запускает. Запускается из run_overlay.ps1 (шаг 16) ДО любого изменения.
# stdout: SSC sha256 <sha> bytes <число>, SSC ros2_ws_lines <число>, SSC overlay_lines <число строк с bench_ws/>, SSC line <номер>:<строка source> (каждая строка source), BB_SSC_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_SSC_MARK
S="$HOME/start_bumblebee.sh"
if [ ! -f "$S" ]; then echo "SSC missing $S"; echo "BB_SSC_DONE"; exit 0; fi
echo "SSC sha256 $(sha256sum "$S" | cut -c1-64) bytes $(wc -c < "$S")"
echo "SSC ros2_ws_lines $(grep -c -x 'source /home/lb/ros2_ws/install/setup.bash' "$S")"
echo "SSC overlay_lines $(grep -c 'bench_ws/' "$S")"
grep -n '^source ' "$S" | cut -c1-200 | while IFS= read -r l; do echo "SSC line $l"; done
echo "BB_SSC_DONE"
