#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 12.11.2026, набор r6). «Правка применилась?» для камеры после перезапуска стека (урок Wi-Fi: файл на месте ещё не значит, что он работает).
# Аргумент: cam (после 05c: ждём camera_fix dabd5076 и launch с full_rows) или r2j (после отката 06c: ждём прежние camera_fix 4a15d699 и launch r2j).
# Что читает (ничего не пишет, службы не трогает, sudo не нужен):
#  - служба bumblebee: active, MainPID, NRestarts;
#  - префикс, который реально исполняется (ros2 pkg prefix bumblebee с теми же строками source, что у запуска), sha256 launch-файла в нём;
#  - РАБОТАЮЩИЕ процессы camera_fix: путь из /proc/<pid>/cmdline, sha256 файла по этому пути, имя узла (__node:=), время запуска процесса и время
#    последнего изменения файла (ctime): если файл менялся ПОСЛЕ запуска процесса, процесс исполняет старый код (стек не перезапущен);
#  - /tmp/bumblebee.log (только чтение; его же читает portguard): блок ПОСЛЕДНЕГО запуска стека (после последней строки «[launch]: All log files can be found below»,
#    pid в имени папки журнала сверяется с MainPID): строки запуска camera_fix (full_rows=True у главной, False у второй), «full-row read: 384 ...»,
#    строки «camera_fix stats» (legacy frames), «process has died», число запусков camera_fix (перезапуски), строки ошибок camera_fix.
# Решение OK / NOT_OK принимает ПК (run_r6_camverify.ps1). Последняя строка BB_R6CV_DONE.
# Только для тестов на ПК: BB_TEST_PROC, BB_TEST_LOG, BB_TEST_NOROS (тогда префикс из BB_TEST_PREFIX), BB_TEST_HZ.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6CV_MARK
export LC_ALL=C
PROC="${BB_TEST_PROC:-/proc}"; LOGF="${BB_TEST_LOG:-/tmp/bumblebee.log}"
MODE="${1:-}"
case "$MODE" in cam|r2j) ;; *) echo "CV_STOP режим '$MODE'"; echo "BB_R6CV_DONE"; exit 0;; esac
echo "CV_MODE $MODE $(date '+%F %T %z')"
act=unknown; mpid=0; nr=unknown
while IFS='=' read -r k v; do case "$k" in ActiveState) act="$v";; MainPID) mpid="$v";; NRestarts) nr="$v";; esac; done < <(systemctl show bumblebee -p ActiveState -p MainPID -p NRestarts 2>/dev/null)
echo "CV_SERVICE active=$act mainpid=$mpid nrestarts=$nr"
if [ -n "${BB_TEST_NOROS:-}" ]; then PFX="${BB_TEST_PREFIX:-}"; else
  PFX=$( source /etc/profile.d/bumblebee-ros.sh < /dev/null > /dev/null 2>&1
         source /opt/ros/jazzy/setup.bash < /dev/null > /dev/null 2>&1
         if [ -f "$HOME/start_bumblebee.sh" ]; then
           while IFS= read -r l; do
             case "$l" in
               "source /home/lb/ros2_ws/install/setup.bash"|"source /home/lb/bench_ws/mavros/install/local_setup.bash"|"source /home/lb/bench_ws/r2j/install/local_setup.bash"|"source /home/lb/bench_ws/port/install/local_setup.bash")
                 f="$HOME/${l#source /home/lb/}"; [ -f "$f" ] && source "$f" < /dev/null > /dev/null 2>&1 ;;
             esac
           done < "$HOME/start_bumblebee.sh"
         fi
         timeout 30 ros2 pkg prefix bumblebee < /dev/null 2>/dev/null | head -1 )
fi
echo "CV_PREFIX ${PFX:-none}"
if [ -n "$PFX" ] && [ -f "$PFX/share/bumblebee/launch/bumblebee.launch.py" ]; then
  echo "CV_LAUNCH sha=$(sha256sum "$PFX/share/bumblebee/launch/bumblebee.launch.py" | cut -c1-64)"
else
  echo "CV_LAUNCH sha=missing"
fi
HZ="${BB_TEST_HZ:-$(getconf CLK_TCK 2>/dev/null || echo 100)}"
BT=$(awk '/^btime /{print $2}' "$PROC/stat" 2>/dev/null)
PFXR=$(readlink -f "$PFX" 2>/dev/null)
for d in "$PROC"/[0-9]*; do
  [ -r "$d/cmdline" ] || continue
  mapfile -d '' -t argv < "$d/cmdline" 2>/dev/null || continue
  path=""; node=""
  for a in "${argv[@]}"; do
    case "$a" in *BB_R6*) path=""; node=""; break;; esac
    case "$a" in */lib/bumblebee/camera_fix.py) path="$a";; __node:=*) node="${a#__node:=}";; esac
  done
  [ -n "$path" ] || continue
  pid="${d##*/}"
  sha=$(sha256sum "$path" 2>/dev/null | cut -c1-64)
  st=$(sed -E 's/^.*\) //' "$d/stat" 2>/dev/null | awk '{print $20}')
  se=""; [ -n "$st" ] && [ -n "$BT" ] && se=$(( BT + st / HZ ))
  fc=$(stat -L -c %Z "$path" 2>/dev/null)
  pr=$(readlink -f "$path" 2>/dev/null); inp=no
  case "$pr" in "$PFXR"/lib/bumblebee/*) [ -n "$PFXR" ] && inp=yes;; esac
  echo "CV_PROC node=${node:-unknown} pid=$pid sha=${sha:-none} in_prefix=$inp start_epoch=${se:-unknown} file_ctime=${fc:-unknown} path=$path"
done
if [ ! -r "$LOGF" ]; then echo "CV_LOG access=denied"; echo "BB_R6CV_DONE"; exit 0; fi
N=$(grep -n -a '\[launch\]: All log files can be found below' "$LOGF" | tail -1 | cut -d: -f1)
if [ -z "$N" ]; then echo "CV_LOG access=ok run=none"; echo "BB_R6CV_DONE"; exit 0; fi
RL=$(sed -n "${N}p" "$LOGF")
LP=$(printf '%s' "$RL" | sed -E 's/.*-([0-9]+)[[:space:]]*$/\1/')
case "$LP" in ''|*[!0-9]*) LP=unknown;; esac
m=no; [ "$LP" = "$mpid" ] && m=yes
echo "CV_LOG access=ok run_line=$N launch_pid=$LP mainpid=$mpid match=$m"
B=$(tail -n +"$N" "$LOGF")
cnt() { printf '%s\n' "$B" | grep -a -c -F -- "$1"; }
MAINS='[main_camera.main_camera_fix]: camera_fix: image_raw_yuv -> image_raw'
SECS='[second_camera.second_camera_fix]: camera_fix: image_raw_yuv -> image_raw'
echo "CV_START main lines=$(cnt "$MAINS") full_rows_true=$(printf '%s\n' "$B" | grep -a -F -- "$MAINS" | grep -a -c -F 'full_rows=True') full_rows_false=$(printf '%s\n' "$B" | grep -a -F -- "$MAINS" | grep -a -c -F 'full_rows=False')"
echo "CV_START second lines=$(cnt "$SECS") full_rows_true=$(printf '%s\n' "$B" | grep -a -F -- "$SECS" | grep -a -c -F 'full_rows=True') full_rows_false=$(printf '%s\n' "$B" | grep -a -F -- "$SECS" | grep -a -c -F 'full_rows=False')"
echo "CV_FULLROW main read384=$(cnt '[main_camera.main_camera_fix]: camera_fix: full-row read: 384 sensor rows at pitch 1600 -> 640x480') any=$(cnt '[main_camera.main_camera_fix]: camera_fix: full-row read:') not_possible=$(printf '%s\n' "$B" | grep -a -F '[main_camera.main_camera_fix]' | grep -a -c -F 'full-row read not possible')"
echo "CV_FULLROW second any=$(cnt '[second_camera.second_camera_fix]: camera_fix: full-row read:')"
printf '%s\n' "$B" | grep -a -F '[main_camera.main_camera_fix]: camera_fix stats' | sed -E 's/.*full-row frames ([0-9]+), legacy frames ([0-9]+).*/CV_STATS main full=\1 legacy=\2/' | grep -a '^CV_STATS'
printf '%s\n' "$B" | grep -a -F '[second_camera.second_camera_fix]: camera_fix stats' | sed -E 's/.*full-row frames ([0-9]+), legacy frames ([0-9]+).*/CV_STATS second full=\1 legacy=\2/' | grep -a '^CV_STATS'
echo "CV_DIED $(cnt 'process has died')"
echo "CV_CAMFIX_STARTED $(printf '%s\n' "$B" | grep -a -c -E '\[INFO\] \[camera_fix\.py-[0-9]+\]: process started with pid')"
echo "CV_ERRORS $(printf '%s\n' "$B" | grep -a -c -E 'camera_fix (full-row )?error')"
printf '%s\n' "$B" | grep -a -E 'process has died|camera_fix (full-row )?error|full-row read not possible' | tail -n 8 | cut -c1-240 | while IFS= read -r l; do echo "CV_BAD_LINE $l"; done
echo "BB_R6CV_DONE"
