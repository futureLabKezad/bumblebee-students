#!/bin/bash
# rc3 sessions only, step 7.1+ (Pi): CPU of the apt MAVROS (mavros_node from /opt) over 30 s, as the baseline for the
# bp02 criterion of plan redaction 9, U1 (Appendix Б): «ЦП mavros_node больше 50% одного ядра или больше чем в 2 раза
# выше apt — стоп». m5_check74_rc3.sh (STEP=UM) compares with this file. Claude, 02.11.2026 (PLAN_DELTA_rc3_mavros_proposal.md).
# Run in 7.1 of an rc3 session, BEFORE У2/УМ, while the drone still runs apt MAVROS (service bumblebee active).
# Writes only one new file: $BD/mavros_cpu_apt.txt (never overwritten). Read-only otherwise. No sudo.
# Usage on the drone: BD=~/bench_<session> bash m6_cpu_apt.sh      -> last line RC3M_M6_OK
# Env (test on the PC only): RC3M_HOST, RC3M_EXE_APT (expected mavros_node path), RC3M_CPU_S (seconds, default 30),
# RC3M_PNAME (process name, default mavros_node; the PC test uses a renamed copy of an ordinary program, never MAVROS).
HOST_EXPECTED="${RC3M_HOST:-bumblebee-20ec}"
EXE_APT="${RC3M_EXE_APT:-/opt/ros/jazzy/lib/mavros/mavros_node}"
CPU_S="${RC3M_CPU_S:-30}"
PNAME="${RC3M_PNAME:-mavros_node}"
export HOST_EXPECTED EXE_APT CPU_S PNAME
echo "=== $(date '+%F %T') ЦП MAVROS apt (база для порога bp02), $CPU_S с"
( set -eo pipefail
  [ -n "$BD" ]
  [ -d "$BD" ]
  [ "$(hostname)" = "$HOST_EXPECTED" ]
  O="$BD/mavros_cpu_apt.txt"
  [ ! -e "$O" ]                                                          # не перезаписываем
  P=$(pgrep -x "$PNAME" || true)
  if [ -z "$P" ]; then echo 'СТОП: mavros_node нет'; exit 1; fi
  [ "$(echo $P | wc -w)" = 1 ]                                           # ровно один
  EXE=$(readlink -f "/proc/$P/exe")
  echo "PID=$P readlink: $EXE"
  if [ "$EXE" != "$EXE_APT" ]; then echo "СТОП: mavros_node не из $EXE_APT (база берётся только с apt MAVROS)"; exit 1; fi
  HZ=$(getconf CLK_TCK)
  a=$(awk '{print $14+$15}' "/proc/$P/stat"); sleep "$CPU_S"
  b=$(awk '{print $14+$15}' "/proc/$P/stat")                              # процесс должен жить весь замер
  X10=$(( (b - a) * 1000 / (HZ * CPU_S) ))                               # десятые доли % одного ядра
  { echo "CPU_APT_X10=$X10"; echo "seconds=$CPU_S pid=$P exe=$EXE ticks=$((b - a)) hz=$HZ date=$(date '+%F %T')"; } > "$O"
  cat "$O"
  echo "ЦП MAVROS apt: $((X10 / 10)).$((X10 % 10))% одного ядра за $CPU_S с — записано в $O"
  echo 'ЦП APT ГОТОВО' )
RC=$?
if [ "$RC" != 0 ]; then echo "=== СТОП: замер ЦП apt не прошёл (код $RC). Без него проверка УМ не сойдётся. Ничего не менять, прислать Claude."; exit 1; fi
echo RC3M_M6_OK
