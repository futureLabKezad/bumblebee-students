#!/bin/bash
# МЕНЯЕТ ДРОН: ВРЕМЕННО (Claude, 12.11.2026, набор r6; фазы A, C, A2 процедуры PI_PERF, /work/parallel_work/20261015/integration/camera_fullrow_01/PI_PERF_PROCEDURE_proposal.md, п. 5,
# переписаны без ssh-окна и без pgrep -f). Цена камеры полных строк БЕЗ установки: стек работает как обычно, ни один его файл не меняется, ни один процесс стека не останавливается.
# Рядом на время фазы запускаются временные процессы (каждый под timeout, не дольше 4 минут; после записи они останавливаются сигналом INT по своему PID, без pkill/pgrep -f):
#   - только в фазе C: camera_fix.py (кандидат dabd5076) под именем main_camera_fix_full: читает /main_camera/image_raw_yuv, пишет НОВЫЕ темы /main_camera/image_raw_full и camera_info_full;
#   - aruco_detect_bench: тот же aruco_detect.py, что исполняет стек (из ros2 pkg prefix bumblebee), через /home/lb/opencv47_venv/bin/python3 (системный OpenCV 4.6 без ArucoDetector, P2/V2),
#     параметры как в aruco.launch.py r2j, но gate_by_flight_state:=false; ВСЕ его выходы уведены в /bench/... (markers, debug, map_pose, map_image, markers_used, yaw_locked, /tf),
#     поэтому до vpe_fix и PX4 они не доходят;
#   - bench_recorder.py: только подписка; частоты, задержки, CPU процессов и ядер, температура, троттлинг.
# Почему «МЕНЯЕТ ДРОН (временно)»: временные процессы добавляют нагрузку и новые темы, пишут НОВЫЕ файлы в ~/bench_ws/camera_fullrow_r6/<метка>/cost; стек, PX4 и файлы на путях запуска не меняются.
# Моторы выключены, винты сняты, дрон разоружён, передатчик выключен: проверяет владелец (подтверждение в 22_kamera_cena_A_C_A2.cmd).
# Аргументы: метка ГГГГММДД_ЧЧММСС и фаза A | C | A2. Итог: «ФАЗА <фаза> ГОТОВО: <папка>» или «ФАЗА <фаза> НЕ ГОТОВО: причина», последняя строка BB_R6COST_DONE.
# Только для тестов на ПК: BB_TEST_PROC, BB_TEST_LOG, BB_TEST_NOROS.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6COST_MARK
export LC_ALL=C.UTF-8
PROC="${BB_TEST_PROC:-/proc}"; LOGF="${BB_TEST_LOG:-/tmp/bumblebee.log}"
STAMP="${1:-}"; PHASE="${2:-}"
case "$STAMP" in [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]) ;; *) echo "ФАЗА $PHASE НЕ ГОТОВО: метка '$STAMP' не ГГГГММДД_ЧЧММСС"; echo "BB_R6COST_DONE"; exit 2;; esac
stop() { echo "ФАЗА $PHASE НЕ ГОТОВО: $*"; echo "BB_R6COST_DONE"; exit 1; }
case "$PHASE" in
  A|A2) IMG=/main_camera/image_raw; INFO=/main_camera/camera_info ;;
  C) IMG=/main_camera/image_raw_full; INFO=/main_camera/camera_info_full ;;
  *) stop "фаза '$PHASE', а нужно A, C или A2" ;;
esac
ros_env() {
  [ -n "${BB_TEST_NOROS:-}" ] && return 0
  source /etc/profile.d/bumblebee-ros.sh < /dev/null > /dev/null 2>&1
  source /opt/ros/jazzy/setup.bash < /dev/null > /dev/null 2>&1
  if [ -f "$HOME/start_bumblebee.sh" ]; then
    while IFS= read -r l; do
      case "$l" in
        "source /home/lb/ros2_ws/install/setup.bash"|"source /home/lb/bench_ws/mavros/install/local_setup.bash"|"source /home/lb/bench_ws/r2j/install/local_setup.bash"|"source /home/lb/bench_ws/port/install/local_setup.bash")
          f="$HOME/${l#source /home/lb/}"; [ -f "$f" ] && source "$f" < /dev/null > /dev/null 2>&1 ;;
      esac
    done < "$HOME/start_bumblebee.sh"
  fi
  if [ -r /etc/bumblebee/ros.env ]; then set -a; . /etc/bumblebee/ros.env; set +a; fi
  export FASTDDS_BUILTIN_TRANSPORTS=UDPv4
}
scan_meas() {
  for d in "$PROC"/[0-9]*; do
    c=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null) || continue
    case "$c" in *BB_R6*) continue;; esac
    case "$c" in *aruco_detect_bench*|*main_camera_fix_full*|*bench_recorder.py*|*raw_layout_check.py*) echo "${d##*/} $(printf '%s' "$c" | cut -c1-160)";; esac
  done
}
count_cmd() {   # сколько процессов, в командной строке которых есть подстрока $1 (свой скрипт не считается)
  local n=0 d c
  for d in "$PROC"/[0-9]*; do
    c=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null) || continue
    case "$c" in *BB_R6*) continue;; esac
    case "$c" in *"$1"*) n=$((n+1));; esac
  done
  echo "$n"
}
I="$HOME/bench_ws/incoming/camera_fullrow_r6"
BD="$HOME/bench_ws/camera_fullrow_r6/$STAMP"
O="$BD/cost/$PHASE"
VENV="$HOME/opencv47_venv/bin/python3"
echo "COST_PHASE $PHASE $(date '+%F %T %z') dir=$O"
for f in "$O" "$O.recorder.log" "$O.aruco_bench.log" "$O.camfix_full.log" "$O.camfix_full_stats.txt" "$O.end.txt"; do
  [ ! -e "$f" ] || stop "уже есть $f, ничего не перезаписываю"
done
[ -d "$I" ] || stop "нет $I (сначала 21_kamera_K1_raskladka.cmd)"
( cd "$I" && sha256sum -c --quiet SHA256SUMS_camera_fullrow.txt ) > /dev/null 2>&1 || stop "sha256 файлов в $I не сходятся"
[ -x "$VENV" ] || stop "нет $VENV (детектор на Pi нужен с OpenCV из venv: системный 4.6 без ArucoDetector)"
m=$(scan_meas)
[ -z "$m" ] || stop "остался процесс замера (подождите минуту): $m"
for p in '__node:=main_camera_fix ' '__node:=aruco_detect ' 'mavros_node'; do
  n=$(count_cmd "$p"); echo "COST_STACK_BEFORE '$p' $n"
  [ "$n" = 1 ] || stop "в стеке не ровно один процесс ($p: $n); стек не работает как обычно"
done
ros_env
export RCUTILS_LOGGING_BUFFERED_STREAM=0 PYTHONUNBUFFERED=1   # строки журнала временных процессов сразу в файл (как у стека: start_bumblebee.sh)
PFX=$(timeout 30 ros2 pkg prefix bumblebee < /dev/null 2>/dev/null | head -1)
APFX=$(timeout 30 ros2 pkg prefix aruco_pose < /dev/null 2>/dev/null | head -1)
AD="$PFX/lib/bumblebee/aruco_detect.py"
MAP="$APFX/share/aruco_pose/map/map.txt"
[ -n "$PFX" ] && [ -f "$AD" ] || stop "нет aruco_detect.py стека ($AD)"
[ -n "$APFX" ] && [ -f "$MAP" ] || stop "нет карты меток ($MAP)"
echo "COST_AD $AD sha256=$(sha256sum "$AD" | cut -c1-64)"
echo "COST_ARUCO_LAUNCH $(sha256sum "$PFX/share/bumblebee/launch/aruco.launch.py" 2>/dev/null | cut -c1-64)"
echo "COST_MAP $MAP sha256=$(sha256sum "$MAP" | cut -c1-64)"
mkdir -p "$BD/cost" || stop "не создать $BD/cost"
th0=$(vcgencmd get_throttled 2>&1); t0=$(vcgencmd measure_temp 2>&1)
d0=$(grep -c 'process has died' "$LOGF" 2>/dev/null)
echo "COST_START $th0 $t0 died=${d0:-unknown}"
CF=""; DT=""
if [ "$PHASE" = C ]; then
  timeout -s INT 240 python3 -B "$I/camera_fix.py" --ros-args -r __ns:=/main_camera -r __node:=main_camera_fix_full \
    -p output_topic:=image_raw_full -r camera_info:=camera_info_full < /dev/null > "$O.camfix_full.log" 2>&1 &
  CF=$!
  sleep 5
fi
timeout -s INT 230 "$VENV" -B "$AD" --ros-args -r __node:=aruco_detect_bench \
  -p dictionary:=1 -p estimate_poses:=true -p send_tf:=true -p use_map_markers:=true -p length:=0.15 \
  -p corner_refinement_method:=3 -p min_marker_perimeter_rate:=0.03 -p map_file:="$MAP" \
  -p adaptive_thresh_win_size_max:=51 -p use_unsharp:=true -p unsharp_sigma:=1.0 -p unsharp_amount:=0.6 \
  -p aruco3_downscale_every_n:=4 -p track_roi_expand:=1.5 -p track_roi_min_px:=60 -p track_sweep_min:=3 \
  -p track_sweep_max:=21 -p track_sweep_step:=6 -p track_keepalive_frames:=3 -p gate_by_flight_state:=false \
  -r image_raw:=$IMG -r camera_info:=$INFO -r map_markers:=/aruco_map/map \
  -r markers:=/bench/aruco_detect/markers -r debug:=/bench/aruco_detect/debug -r map_pose:=/bench/aruco_map/pose \
  -r map_image:=/bench/aruco_map/image -r /aruco_detect/markers_used:=/bench/aruco_detect/markers_used \
  -r /aruco_detect/yaw_locked:=/bench/aruco_detect/yaw_locked -r /tf:=/bench/tf < /dev/null > "$O.aruco_bench.log" 2>&1 &
DT=$!
sleep 30
timeout -s INT 170 python3 -B "$I/bench_recorder.py" --out "$O" --duration 120 --pose-topic /bench/aruco_map/pose \
  --markers-topic /bench/aruco_detect/markers --image-topic $IMG \
  --procs "v4l2_main=__node:=main_camera " "v4l2_second=__node:=second_camera " \
          "camfix=__node:=main_camera_fix " "camfix_second=__node:=second_camera_fix " \
          "camfix_full=__node:=main_camera_fix_full " "aruco_bench=__node:=aruco_detect_bench " \
          "aruco=__node:=aruco_detect " mavros=mavros_node vpe_fix=vpe_fix.py simple_offboard=lib/bumblebee/simple_offboard \
          setpoint_freshness=setpoint_freshness.py qos_relay=qos_relay.py mjpeg=ros_mjpeg_server.py \
          rosbridge=rosbridge tf2_web=tf2_web_republisher controller=bumblebee_controller \
          camera_markers=camera_markers servo_rc=servo_rc.py wheel_rc=wheel_rc.py < /dev/null > "$O.recorder.log" 2>&1
echo "COST_RECORDER_RC $?"
# запись кончилась: временные процессы останавливаются сигналом INT по своему PID (timeout передаёт его процессу)
[ -n "$DT" ] && kill -INT "$DT" 2>/dev/null
[ -n "$CF" ] && kill -INT "$CF" 2>/dev/null
wait 2>/dev/null
th1=$(vcgencmd get_throttled 2>&1); t1=$(vcgencmd measure_temp 2>&1)
d1=$(grep -c 'process has died' "$LOGF" 2>/dev/null)
printf 'throttled=%s\ntemp=%s\ndied=%s\n' "$th1" "$t1" "${d1:-unknown}" > "$O.end.txt"
echo "COST_END $th1 $t1 died=${d1:-unknown}"
while IFS= read -r l; do echo "COST_REC $l"; done < "$O.recorder.log"
if [ "$PHASE" = C ]; then
  grep -a 'camera_fix' "$O.camfix_full.log" | grep -a -E 'stats|full_rows=|full-row read' > "$O.camfix_full_stats.txt"
  while IFS= read -r l; do echo "COST_CAMFIX_FULL $l"; done < "$O.camfix_full_stats.txt"
  grep -q 'full-row frames' "$O.camfix_full_stats.txt" || stop "в журнале main_camera_fix_full нет строк stats с full-row frames"
fi
[ -f "$O/summary.json" ] || stop "нет $O/summary.json"
echo "COST_SUMMARY_JSON $(tr -d '\n' < "$O/summary.json" | cut -c1-12000)"
grep -q '^RECORDER ГОТОВО' "$O.recorder.log" || stop "нет строки RECORDER ГОТОВО"
m=$(scan_meas)
[ -z "$m" ] || echo "COST_LEFT процессы замера ещё работают (закончатся по timeout): $m"
echo "ФАЗА $PHASE ГОТОВО: $O"
echo "BB_R6COST_DONE"
