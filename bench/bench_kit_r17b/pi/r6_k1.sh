#!/bin/bash
# МЕНЯЕТ ДРОН: ТОЛЬКО НОВЫЕ ФАЙЛЫ (Claude, 12.11.2026, набор r6; критерий К-1 процедуры PI_PERF, /work/parallel_work/20261015/integration/camera_fullrow_01/PI_PERF_PROCEDURE_proposal.md, блок «К1»).
# Раскладка кадра камеры (главная посылка камеры полных строк): 5 сырых кадров /main_camera/image_raw_yuv; ждём step 1280, 614400 байт, нули в заполнении при шаге строки 1600.
# Что делает: raw_layout_check.py (только подписка, ничего не публикует) под timeout 60 с; он пишет кадр 0 (raw_frame_0.bin), две картинки и meta.json
# в НОВУЮ папку ~/bench_ws/camera_fullrow_r6/<метка>/K1 (если она уже есть: СТОП, ничего не перезаписывается). Стек, его файлы, службы и PX4 НЕ трогает.
# Без pgrep -f: процессы ищутся чтением /proc/<pid>/cmdline (свой процесс этого скрипта отбрасывается по метке BB_R6).
# Аргумент: метка ГГГГММДД_ЧЧММСС. Итог: строка «К1 ГОТОВО <папка>» или «К1 НЕ ГОТОВО», последняя строка BB_R6K1_DONE.
# Только для тестов на ПК: BB_TEST_PROC, BB_TEST_LOG, BB_TEST_NOROS.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6K1_MARK
export LC_ALL=C.UTF-8
PROC="${BB_TEST_PROC:-/proc}"; LOGF="${BB_TEST_LOG:-/tmp/bumblebee.log}"
STAMP="${1:-}"
case "$STAMP" in [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]) ;; *) echo "К1 НЕ ГОТОВО: метка '$STAMP' не ГГГГММДД_ЧЧММСС"; echo "BB_R6K1_DONE"; exit 2;; esac
stop() { echo "К1 НЕ ГОТОВО: $*"; echo "BB_R6K1_DONE"; exit 1; }
ros_env() {
  [ -n "${BB_TEST_NOROS:-}" ] && return 0
  source /etc/profile.d/bumblebee-ros.sh < /dev/null > /dev/null 2>&1
  source /opt/ros/jazzy/setup.bash < /dev/null > /dev/null 2>&1
  if [ -r /etc/bumblebee/ros.env ]; then set -a; . /etc/bumblebee/ros.env; set +a; fi
  export FASTDDS_BUILTIN_TRANSPORTS=UDPv4
}
# процессы замера (свой скрипт с меткой BB_R6 не считается)
scan_meas() {
  for d in "$PROC"/[0-9]*; do
    c=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null) || continue
    case "$c" in *BB_R6*) continue;; esac
    case "$c" in *aruco_detect_bench*|*main_camera_fix_full*|*bench_recorder.py*|*raw_layout_check.py*) echo "${d##*/} $(printf '%s' "$c" | cut -c1-160)";; esac
  done
}
# процессы стека (для записи «до»)
scan_stack() {
  for d in "$PROC"/[0-9]*; do
    c=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null) || continue
    case "$c" in *BB_R6*) continue;; esac
    case "$c" in *mavros_node*|*/lib/bumblebee/*|*v4l2_camera_node*|*bumblebee_controller*) echo "${d##*/} $(printf '%s' "$c" | cut -c1-160)";; esac
  done
}
I="$HOME/bench_ws/incoming/camera_fullrow_r6"
BD="$HOME/bench_ws/camera_fullrow_r6/$STAMP"
K="$BD/K1"
[ ! -e "$K" ] || stop "папка $K уже есть, ничего не перезаписываю"
[ -d "$I" ] || stop "нет $I (файлы замера не скопированы)"
( cd "$I" && sha256sum -c --quiet SHA256SUMS_camera_fullrow.txt ) > /dev/null 2>&1 || stop "sha256 файлов в $I не сходятся"
m=$(scan_meas)
[ -z "$m" ] || stop "уже работает процесс замера: $m"
ros_env
export RCUTILS_LOGGING_BUFFERED_STREAM=0 PYTHONUNBUFFERED=1
mkdir -p "$BD" && mkdir "$K" || stop "не создать $K"
echo "K1_DIR $K"
if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd get_throttled > "$K/throttled_start.txt" 2>&1; vcgencmd measure_temp > "$K/temp_start.txt" 2>&1
fi
echo "K1_THROTTLED_START $(cat "$K/throttled_start.txt" 2>/dev/null)"
echo "K1_TEMP_START $(cat "$K/temp_start.txt" 2>/dev/null)"
d0=$(grep -c 'process has died' "$LOGF" 2>/dev/null); echo "${d0:-0}" > "$K/died_start.txt"; echo "K1_DIED_START ${d0:-unknown}"
scan_stack > "$K/stack_start.txt"; echo "K1_STACK_PROCS $(grep -c . "$K/stack_start.txt")"
timeout -s INT 60 python3 -B "$I/raw_layout_check.py" --out "$K/raw_check" --candidate "$I/camera_fix.py" --n 5 < /dev/null > "$K/raw_check.log" 2>&1
echo "K1_PY_RC $?"
while IFS= read -r l; do echo "K1_OUT $l"; done < "$K/raw_check.log"
if [ -f "$K/raw_check/meta.json" ]; then
  echo "K1_META_SHA256 $(sha256sum "$K/raw_check/meta.json" | cut -c1-64)"
  tr -d '\n' < "$K/raw_check/meta.json" | cut -c1-6000 | while IFS= read -r l; do echo "K1_META $l"; done
fi
[ -f "$K/raw_check/raw_frame_0.bin" ] && echo "K1_FRAME0 bytes=$(stat -c %s "$K/raw_check/raw_frame_0.bin") sha256=$(sha256sum "$K/raw_check/raw_frame_0.bin" | cut -c1-64)"
if grep -q '^RAW CHECK ГОТОВО' "$K/raw_check.log"; then echo "К1 ГОТОВО $K"; else echo "К1 НЕ ГОТОВО: нет строки RAW CHECK ГОТОВО (раскладка не та или кадров нет)"; fi
echo "BB_R6K1_DONE"
