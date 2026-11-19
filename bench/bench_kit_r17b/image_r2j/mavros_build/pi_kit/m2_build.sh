#!/bin/bash
# rc3 MAVROS overlay, step M2 (Pi): colcon build of the package 'mavros' only, no tests, in ~/bench_ws/mavros, with a
# memory / temperature / Pi-power watch and logs. Claude, 30.10.2026 (README_RU.md, PLAN_DELTA_rc3_mavros_proposal.md).
# v2 02.11.2026: the source check accepts the no-git path of M1 v2 (~/bench_ws/mavros_src_mode.txt: MODE=git or tar).
# r3 02.11.2026 (old text: m2_build.sh.r2): build type RELEASE — the owner's choice of 02.11 (s1b/ОТВЕТ_ВЛАДЕЛЬЦА_
#    PLAN_DELTA_s1b_20261102.md, дополнение; plan Appendix Б.1 lets the owner choose the type). cmake arguments
#    '-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF', exactly as the PC reference build /work/ws_mavros214_bp02_rel
#    (same colcon command; there: SITL-side evidence of the Release build). M3 compares CMakeCache and the compiler flags
#    of the 3 targets with that build. The known GCC warning in setpoint_accel.cpp (-Wmaybe-uninitialized, only with
#    optimisation) is NOT accepted in advance: any stderr = stop, Claude answers in writing, then M3 claude_ok.
#    Everything else is as in r2.
# r2 02.11.2026 (review of 02.11; old text: m2_build.sh.r1):
#  - (replaced by r3) build type «как SITL»: the cmake arguments of the bp02 SITL build ('-DBUILD_TESTING=OFF',
#    CMAKE_BUILD_TYPE empty = no -O, no NDEBUG, assert on).
#  - clean environment for colcon (env -i, only /opt/ros/jazzy and the angles headers), as plan 6.3; no ~/.colcon/defaults.yaml.
#  - the build is stopped TOGETHER with M2: Ctrl+C, a closed window, a lost ssh (HUP, or PIPE on the next line) and TERM go
#    to a trap that stops the build's process group (INT, 20 s, TERM, 20 s, KILL) and waits for it. PID file for m2_stop.sh.
#  - M2 refuses to start while colcon/make/cmake/the compiler run under ~/bench_ws/mavros (an earlier attempt still alive).
#  - no stderr is accepted in advance: any '--- stderr:' / 'had stderr output' / 'WARNING:' in any build_mavros_*.log = stop,
#    Claude answers in writing, then M3 with 'claude_ok' (plan 6.3, «Отпечатки после ответа Claude»).
#  - the watch also records vcgencmd get_throttled (or the Pi 5 hwmon under-voltage alarm) and stops the build after
#    30 s of Pi under-voltage in a row (Claude's choice: protects the SD card; stricter, not a plan criterion).
# Before M2 (the owner, plan 6 «Питание»): battery measured with the multimeter or the cell checker, value and time into the
# protocol; 21.0 V or any cell 3.5 V: do not start. During the build every 30 min; at 21.0 V / 3.5 V: m2_stop.sh (any window).
# Usage: bash m2_build.sh N      N = attempt 1, 2, ... (after a stop: same sources, colcon continues where it stopped).
# Writes only: ~/bench_ws/mavros/{build,install,log}, ~/bench_ws/build_mavros_N.log, mavros_watch_N.txt, mavros_time_N.txt,
# mavros_build_pid_N.txt; after a stop also mavros_watch_stop_N.txt (the watch) or mavros_build_stop_N.txt (from outside).
# Never overwrites, never deletes. No sudo, no network, no apt. The service 'bumblebee' must be stopped before (the owner,
# sudo), as for the port build in part 0b (plan 6.1). Only libmavconn, mavros_msgs and mavros_extras stay from apt.
# Env (dry run on the PC only): RC3M_HOST, RC3M_INC, RC3M_DRYRUN_UNDERLAY (setup files sourced after /opt: stand-in for
# apt 2.14 libmavconn/mavros_msgs, because the PC has apt 2.16), RC3M_JOBS (force make -j). On the Pi none is set.
N="${1:-}"
HOST_EXPECTED="${RC3M_HOST:-bumblebee-20ec}"
INC="${RC3M_INC:-$HOME/bench_ws/incoming/rc3_mavros}"
W="$HOME/bench_ws/mavros"
DEPS="$HOME/bench_ws/mavros_deps"
L="$HOME/bench_ws/build_mavros_$N.log"
WL="$HOME/bench_ws/mavros_watch_$N.txt"
TL="$HOME/bench_ws/mavros_time_$N.txt"
STOPF="$HOME/bench_ws/mavros_watch_stop_$N.txt"     # the watch stopped the build
INTF="$HOME/bench_ws/mavros_build_stop_$N.txt"      # stopped from outside: Ctrl+C, window, ssh, TERM, m2_stop.sh
PIDF="$HOME/bench_ws/mavros_build_pid_$N.txt"       # process group of the build (m2_stop.sh)
MEM_MIN_MB=700        # MemAvailable below this: the watch stops the build (the flight stack is stopped, but ssh must live)
TEMP_STOP_C=85        # SoC temperature at or above this for 2 minutes in a row: the watch stops the build (let it cool, then N+1)
TEMP_WARN_C=80
UV_STOP_N=3           # Pi under-voltage in 3 samples in a row (30 s): the watch stops the build
REL_CMAKE_ARGS='-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF'   # r3: Release, as /work/ws_mavros214_bp02_rel (owner 02.11)
export HOST_EXPECTED INC W DEPS L WL TL STOPF INTF PIDF N
r3_stop() { echo "=== СТОП: $*"; echo "=== Дальше ничего не делать. Прислать Claude этот вывод и $L"; exit 1; }
r3_temp() { local t; t=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null) || { echo NA; return; }; echo "$((t/1000)).$(( (t%1000)/100 ))"; }
r3_thr() { local t=; if command -v vcgencmd >/dev/null 2>&1; then t=$(vcgencmd get_throttled 2>/dev/null) || t=; fi
  case "$t" in throttled=0x[0-9a-fA-F]*) echo "${t#throttled=}" ;; *) echo NA ;; esac; }
r3_uv() {   # 1 = Pi under-voltage now, 0 = no, NA = unknown (vcgencmd bit 0; else Pi 5 hwmon rpi_volt in0_lcrit_alarm)
  local t h; t=$(r3_thr)
  if [ "$t" != NA ]; then echo $(( t & 0x1 )); return; fi
  for h in /sys/class/hwmon/hwmon*; do
    if [ "$(cat "$h/name" 2>/dev/null)" = rpi_volt ] && [ -r "$h/in0_lcrit_alarm" ]; then cat "$h/in0_lcrit_alarm"; return; fi
  done
  echo NA; }
r3_thr_text() {   # bits of vcgencmd get_throttled in words
  local t="$1" s=""
  [ "$t" = NA ] && { echo "get_throttled: нет данных"; return; }
  [ $(( t & 0x1 )) != 0 ] && s="$s, пониженное напряжение СЕЙЧАС"
  [ $(( t & 0x2 )) != 0 ] && s="$s, частота ограничена сейчас"
  [ $(( t & 0x4 )) != 0 ] && s="$s, троттлинг сейчас"
  [ $(( t & 0x8 )) != 0 ] && s="$s, мягкий предел температуры сейчас"
  [ $(( t & 0x10000 )) != 0 ] && s="$s, пониженное напряжение БЫЛО после загрузки"
  [ $(( t & 0x20000 )) != 0 ] && s="$s, ограничение частоты было"
  [ $(( t & 0x40000 )) != 0 ] && s="$s, троттлинг был"
  [ $(( t & 0x80000 )) != 0 ] && s="$s, мягкий предел температуры был"
  echo "get_throttled $t${s:-, всё чисто}"; }
r3_mem() { awk '/^MemAvailable:/{printf "%d", $2/1024}' /proc/meminfo; }
r3_busy() {   # build processes that work under ~/bench_ws/mavros (working folder or command line); prints them; 0 = found
  local p cw cl hit=1 m
  for p in $(pgrep -x 'colcon|make|gmake|cmake|cc1plus|cc1|c\+\+|g\+\+|gcc|collect2|ld|as|time' 2>/dev/null); do
    m=; cw=$(readlink "/proc/$p/cwd" 2>/dev/null) || cw=; cl=$( { tr '\0' ' ' < "/proc/$p/cmdline"; } 2>/dev/null ) || cl=
    case "$cw/" in "$W"/*) m=1 ;; esac
    case " $cl " in *"$W"/*|*"$W "*) m=1 ;; esac
    if [ -n "$m" ]; then echo "  идёт: PID $p $(cat "/proc/$p/comm" 2>/dev/null), папка $cw: ${cl:0:150}"; hit=0; fi
  done
  return $hit; }

echo "=== $(date '+%F %T') M2: сборка MAVROS (только пакет mavros, Release: -O3, как эталонная сборка на ПК), попытка N=$N"
echo "Батарея перед М2 измерена (мультиметр / банки), значение и время — в протокол? 21,0 В или банка 3,5 В — не начинать."
echo "Во время сборки — раз в 30 мин; на 21,0 В / 3,5 В — m2_stop.sh (любое окно), «Сохранить логи», дальше по плану (п. 6)."
( set -eo pipefail
  [ "$(hostname)" = "$HOST_EXPECTED" ]
  case "$N" in [1-9]|[1-9][0-9]) ;; *) echo 'СТОП: N — номер попытки 1, 2, …'; exit 1 ;; esac
  for f in "$L" "$WL" "$TL" "$STOPF" "$INTF" "$PIDF"; do
    if [ -e "$f" ]; then echo "СТОП: $f уже есть (новая попытка — следующий N)"; exit 1; fi
  done
  if [ "$N" != 1 ]; then [ -f "$HOME/bench_ws/build_mavros_$((N-1)).log" ]; fi
  if r3_busy; then echo "СТОП: сборка MAVROS ещё идёт (процессы выше). Сначала m2_stop.sh, потом M2 с этим N"; exit 1; fi
  [ ! -e "$HOME/bench_ws/MAVROS_ARM64_SHA256SUMS.txt" ]                 # отпечатки (M3) ещё не сняты
  if [ -e "$HOME/.colcon/defaults.yaml" ]; then echo 'СТОП: есть ~/.colcon/defaults.yaml: он может тихо поменять сборку (п. 6.3). Ничего не менять, прислать Claude этот файл'; exit 1; fi
  C=$(sed -n 's/^commit=//p' "$INC/EXPECTED_SRC.txt")
  [ "${#C}" = 40 ]
  MF="$HOME/bench_ws/mavros_src_mode.txt"                               # как M1 взял исходники: git или tar (git на Pi нет)
  MODE=$(sed -n 's/^MODE=//p' "$MF")
  [ "$(sed -n 's/^commit=//p' "$MF")" = "$C" ]
  if [ "$MODE" = git ]; then
    [ "$(git -C "$W/src/mavros-source" rev-parse HEAD)" = "$C" ]          # исходники = метка (M1)
    [ -z "$(git -C "$W/src/mavros-source" status --porcelain --untracked-files=all)" ]
  else
    [ "$MODE" = tar ]
    [ ! -e "$W/src/mavros-source/.git" ]
    ( cd "$W/src/mavros-source" && sha256sum -c --quiet "$INC/mavros_bp02_d63a236_files.sha256" )
    [ "$(find "$W/src/mavros-source" -type f | wc -l)" = "$(sed -n 's/^files=//p' "$INC/EXPECTED_SRC.txt")" ]
  fi
  [ -f "$DEPS/opt/ros/jazzy/share/angles/cmake/anglesConfig.cmake" ]
  if systemctl is-active --quiet bumblebee 2>/dev/null; then echo 'СТОП: служба bumblebee запущена (сначала «Сохранить логи», потом sudo systemctl stop bumblebee — делаете вы)'; exit 1; fi
  command -v colcon
  command -v g++
  command -v cmake
  [ -x /usr/bin/time ]
  [ -x /usr/bin/setsid ]
  [ -f /opt/ros/jazzy/setup.bash ]
  { cat /proc/device-tree/model 2>/dev/null || echo 'модель: нет /proc/device-tree/model'; } | tr -d '\0'; echo
  echo "nproc: $(nproc)"
  free -h
  df -h "$HOME" | tail -1
  echo "температура: $(r3_temp) C; $(r3_thr_text "$(r3_thr)"); пониженное напряжение сейчас: $(r3_uv)"
  echo 'УСЛОВИЯ СБОРКИ ГОТОВО' )
[ "$?" = 0 ] || r3_stop "условия сборки не выполнены, сборка не начиналась"

MT_KB=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
if [ -n "$RC3M_JOBS" ]; then J="$RC3M_JOBS"
elif [ "$MT_KB" -ge 7500000 ]; then J=3          # Pi 5 с 8/16 ГБ (на 20EC 16 ГБ, 7.1 части 0а): 3 задачи (одно ядро — системе и ssh; меньше нагрев)
else J=1; fi                                     # меньше 8 ГБ (например 4 ГБ): одна задача
case "$J" in [1-4]) ;; *) r3_stop "RC3M_JOBS=$J (можно 1–4)" ;; esac
echo "ОЗУ $((MT_KB/1024)) МБ -> MAKEFLAGS=-j$J, colcon --parallel-workers 1; cmake: $REL_CMAKE_ARGS (как эталон ПК /work/ws_mavros214_bp02_rel)"

BPID=; SPID=; STARTED=
r3_kill_group() {   # stop the build's process group: INT, 20 s, TERM, 20 s, KILL; then reap it
  local s i
  [ -n "$BPID" ] || return 0
  for s in INT TERM KILL; do
    pgrep -g "$BPID" >/dev/null 2>&1 || break
    kill -"$s" -- "-$BPID" 2>/dev/null
    for i in $(seq 20); do pgrep -g "$BPID" >/dev/null 2>&1 || break; sleep 1; done
  done
  wait "$BPID" 2>/dev/null; return 0; }
r3_watch_stop() { [ -e "$STOPF" ] || echo "$*" > "$STOPF"; r3_kill_group; }
r3_on_signal() {    # Ctrl+C, closed window, lost ssh, TERM: the build stops too
  trap '' INT TERM HUP PIPE
  [ -n "$SPID" ] && kill "$SPID" 2>/dev/null
  [ -n "$STARTED" ] && [ -z "$BPID" ] && BPID=$!
  { [ -e "$INTF" ] || echo "M2 получил $1 $(date '+%F %T'): сборка N=$N остановлена (Ctrl+C, окно закрыто, связь потеряна или TERM)" > "$INTF"; } 2>/dev/null
  r3_kill_group
  echo "=== СТОП: M2 получил $1. Сборка N=$N остановлена, процессы сборки сняты. Следующая попытка — M2 с N=$((N+1)) (colcon продолжит). Прислать Claude $L" 2>/dev/null
  exit 1; }
trap 'r3_on_signal INT' INT
trap 'r3_on_signal TERM' TERM
trap 'r3_on_signal HUP' HUP
trap 'r3_on_signal PIPE' PIPE
for s in INT HUP TERM PIPE; do                   # signal ignored when M2 started (nohup, '&'): bash cannot trap it
  case "$(trap -p "$s")" in *"''"*) echo "ВНИМАНИЕ: сигнал $s при запуске M2 игнорируется — он не остановит сборку. Остановка: m2_stop.sh" ;; esac
done

T0=$(date +%s)
STARTED=1
/usr/bin/env -i HOME="$HOME" USER="$USER" LOGNAME="${LOGNAME:-$USER}" LANG=C.UTF-8 PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  W="$W" DEPS="$DEPS" J="$J" TL="$TL" REL_CMAKE_ARGS="$REL_CMAKE_ARGS" RC3M_DRYRUN_UNDERLAY="$RC3M_DRYRUN_UNDERLAY" \
  /usr/bin/setsid /bin/bash --noprofile --norc -c '
  source /opt/ros/jazzy/setup.bash
  for f in $RC3M_DRYRUN_UNDERLAY; do source "$f"; done                  # только сухой прогон на ПК; на Pi переменная пустая
  export CMAKE_PREFIX_PATH="$DEPS/opt/ros/jazzy${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}:/opt/ros/jazzy"
  bad=; IFS=: read -r -a E <<< "$AMENT_PREFIX_PATH:$CMAKE_PREFIX_PATH:$COLCON_PREFIX_PATH"
  for e in "${E[@]}"; do [ "$e" = "$DEPS/opt/ros/jazzy" ] && continue; case "$e" in *ros2_ws*|*bench_ws*) bad="$bad $e" ;; esac; done
  if [ -n "$bad" ]; then echo "СТОП: в окружении сборки есть ros2_ws или bench_ws:$bad"; exit 1; fi
  for v in CMAKE_BUILD_TYPE CXXFLAGS CFLAGS CPPFLAGS LDFLAGS; do if [ -n "${!v}" ]; then echo "СТОП: в окружении сборки задан $v"; exit 1; fi; done
  cd "$W" || exit 1
  echo "CMAKE_PREFIX_PATH=$CMAKE_PREFIX_PATH"
  echo "AMENT_PREFIX_PATH=$AMENT_PREFIX_PATH"
  export MAKEFLAGS="-j$J"
  exec /usr/bin/time -v -o "$TL" nice -n 10 colcon build --base-paths src/mavros-source/mavros \
    --packages-select mavros --allow-overriding mavros --parallel-workers 1 --event-handlers console_direct- \
    --cmake-args $REL_CMAKE_ARGS' > "$L" 2>&1 < /dev/null &
BPID=$!
{ echo "N=$N"; echo "PGID=$BPID"; echo "M2_PID=$$"; echo "boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"; echo "start=$(date '+%F %T')"; } > "$PIDF"
sleep 1
PG=$(ps -o pgid= -p "$BPID" 2>/dev/null | tr -d ' ')
if kill -0 "$BPID" 2>/dev/null && [ "$PG" != "$BPID" ]; then
  kill -TERM "$BPID" 2>/dev/null
  r3_stop "сборка не в своей группе процессов (PID $BPID, группа $PG): остановлена. Прислать Claude"
fi
echo "сборка идёт (группа процессов $BPID, файл $PIDF), лог $L; строка состояния раз в минуту"
echo "Остановить сборку: Ctrl+C здесь или m2_stop.sh в любом окне (сборка останавливается вместе с этим окном)."
echo "time_s mem_avail_MB swap_free_MB temp_C load1 throttled uv note" > "$WL"
hot=0; uvn=0; k=0; minmem=999999; maxtemp=0
while kill -0 "$BPID" 2>/dev/null; do
  m=$(r3_mem); s=$(awk '/^SwapFree:/{printf "%d", $2/1024}' /proc/meminfo); t=$(r3_temp); l=$(cut -d' ' -f1 /proc/loadavg)
  thr=$(r3_thr); uv=$(r3_uv)
  note=""
  [ "$m" -lt "$minmem" ] && minmem=$m
  if [ "$t" != NA ]; then
    ti=${t%.*}
    [ "$ti" -gt "$maxtemp" ] && maxtemp=$ti
    if [ "$ti" -ge "$TEMP_STOP_C" ]; then hot=$((hot+1)); note="HOT$hot"; else hot=0; fi
    [ "$ti" -ge "$TEMP_WARN_C" ] && [ -z "$note" ] && note="warm"
  fi
  if [ "$uv" = 1 ]; then uvn=$((uvn+1)); note="${note:+$note,}UV$uvn"; else uvn=0; fi
  echo "$(( $(date +%s) - T0 )) $m $s $t $l $thr $uv $note" >> "$WL"
  if [ "$m" -lt "$MEM_MIN_MB" ]; then r3_watch_stop "память: MemAvailable $m МБ < $MEM_MIN_MB МБ"; fi
  if [ "$hot" -ge 12 ]; then r3_watch_stop "температура: $t C >= $TEMP_STOP_C C 2 минуты подряд"; fi
  if [ "$uvn" -ge "$UV_STOP_N" ]; then r3_watch_stop "питание Pi: пониженное напряжение $((uvn * 10)) с подряд ($(r3_thr_text "$thr")). Измерить батарею (21,0 В / 3,5 В — по плану п. 6)"; fi
  [ "$uv" = 1 ] && echo "  ВНИМАНИЕ $(date +%T): пониженное напряжение Pi ($(r3_thr_text "$thr")) — измерить батарею сейчас"
  k=$((k+1))
  [ $((k % 6)) = 0 ] && echo "  $(date +%T)  прошло $(( $(date +%s) - T0 )) с, свободно $m МБ, $t C, нагрузка $l, $thr $note"
  sleep 10 & SPID=$!; wait "$SPID"; SPID=
done
wait "$BPID" 2>/dev/null; RC=$?
if pgrep -g "$BPID" >/dev/null 2>&1; then r3_kill_group; fi                 # остатки группы (не должно быть)
T1=$(date +%s)
trap - INT TERM HUP PIPE
echo "=== $(date '+%F %T') сборка закончилась: код $RC, $(( T1 - T0 )) с; мин. MemAvailable $minmem МБ, макс. температура ${maxtemp} C; $(r3_thr_text "$(r3_thr)")"
grep -E 'Elapsed \(wall clock\)|Maximum resident set size|User time|System time|Percent of CPU' "$TL" 2>/dev/null || echo "нет $TL"
tail -5 "$L"
if r3_busy; then r3_stop "после сборки остались её процессы (выше): m2_stop.sh, потом прислать Claude"; fi
[ ! -e "$STOPF" ] || r3_stop "сторож остановил сборку: $(cat "$STOPF"). Дать остыть / разобраться, потом M2 с N=$((N+1)) (colcon продолжит)"
[ ! -e "$INTF" ] || r3_stop "сборку остановили снаружи: $(cat "$INTF"). Потом M2 с N=$((N+1)) (colcon продолжит)"
export RC
( set -eo pipefail
  [ "$RC" = 0 ]
  grep -a '^Summary: 1 package finished' "$L"
  if grep -a -E '^ +[0-9]+ packages? (failed|aborted)|not processed' "$L"; then echo 'СТОП: сборка не прошла'; exit 1; fi
  for g in "$HOME"/bench_ws/build_mavros_*.log; do                       # все попытки, не только эта (п. 6.3)
    if grep -a -n -E 'packages? had stderr output|^--- stderr:' "$g"; then
      awk '/^--- stderr: /{f=1} f{print} /^---$/{f=0}' "$g" | head -40
      echo "СТОП: в $g есть stderr. Любой stderr — стоп (п. 6.3 плана, заранее ничего не принято). Прислать Claude этот лог;"
      echo "      M3 — только после письменного ответа Claude «принято»: bash m3_verify.sh claude_ok (время ответа — в протокол)"
      exit 1
    fi
    if grep -a -n -E '(^|\] )WARNING:' "$g"; then echo "СТОП: в $g предупреждение colcon. Прислать Claude; M3 — только после письменного ответа Claude (claude_ok)"; exit 1; fi
  done
  echo 'СБОРКА MAVROS ГОТОВО' )
[ "$?" = 0 ] || r3_stop "сборка не прошла или есть stderr/WARNING (см. строки выше)"
echo RC3M_M2_OK
