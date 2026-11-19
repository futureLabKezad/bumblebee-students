#!/bin/bash
# МЕНЯЕТ ДРОН: ТОЛЬКО НОВАЯ ПАПКА (Claude, 12.11.2026, набор r6). Создаёт пустую папку ~/bench_ws/incoming/camera_fullrow_r6 для трёх файлов замера камеры полных строк.
# Последняя папка создаётся БЕЗ -p: если она уже есть, mkdir откажет и ничего не будет перезаписано. Вызывается из run_r6_k1.ps1 и run_r6_cost.ps1 только после
# проверки r6_cam_incoming.sh (CI_STATE absent). Ничего не удаляет, стек и PX4 не трогает. Успех: строка MKDIR_OK.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6MK_MARK
mkdir -p "$HOME/bench_ws/incoming" && mkdir "$HOME/bench_ws/incoming/camera_fullrow_r6" && echo "MKDIR_OK $HOME/bench_ws/incoming/camera_fullrow_r6"
