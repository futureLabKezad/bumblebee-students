#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2). Строки журнала службы bumblebee (vpe_fix, aruco_detect, сторожа) за последние N секунд, для разбора паузы зрения после взлёта (Ж3/Ж5).
# Ничего не пишет на дрон, файлов на Pi не создаёт, узлы и PX4 не трогает. Запускается из run_journal.ps1 через ssh после полёта, когда дрон разоружён.
# Аргумент 1: окно в секундах (60..1800). Время берётся по часам Pi («N секунд назад»), поэтому расхождение часов ПК и Pi не мешает.
# BB_JOURNAL_MARK
# stdout: строки журнала с временем (ISO, микросекунды) без изменений, потом BB_JOURNAL_DONE. Отбор по словам: vpe_fix, vpe_publisher, aruco_detect, detection, publish=, resume after, SEARCHING, NORMAL,
# single-marker, Vision lost, vision silent, vision_pose_age, SETTLE, OFFBOARD, land; не больше 8000 строк.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
W="${1:-300}"
case "$W" in ''|*[!0-9]*) echo "STOP: bad window '$W'" >&2; exit 1;; esac
[ "$W" -ge 60 ] && [ "$W" -le 1800 ] || { echo "STOP: window must be 60..1800 s" >&2; exit 1; }
echo "META script journal_window.sh window_s=$W pi_date=$(date '+%F %T %z')"
journalctl -u bumblebee --since "$W seconds ago" --no-pager -o short-iso-precise 2>&1 \
  | grep -E 'vpe_fix|vpe_publisher|aruco_detect|detection (ACTIVE|IDLE)|publish=|resume after|SEARCHING|NORMAL|single-marker|Vision lost|vision silent|vision_pose_age|SETTLE|OFFBOARD|land' \
  | cut -c1-400 | head -8000
if journalctl -u bumblebee -n 1 --no-pager 2>&1 | grep -q -i -E "not seeing messages|No journal files|Permission denied"; then echo "JOURNAL_ACCESS_DENIED (нет прав на journalctl или нет журнала: пустой результат не значит «событий не было»)"; fi
echo "BB_JOURNAL_DONE rc=${PIPESTATUS[0]}"
