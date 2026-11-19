#!/bin/bash
# rc3 MAVROS overlay, step M2-СТОП (Pi): stop the MAVROS build of M2 from any window, one click. Claude, 02.11.2026 (r2,
# review of 02.11; README_RU.md, PLAN_DELTA_rc3_mavros_proposal.md).
# When: battery at 21.0 V or a cell at 3.5 V (plan 6 «Питание»: the build is stopped, «Сохранить логи», then plan/v1 4.1),
# or Claude / the owner says stop, or the window of M2 is gone and the build may still run.
# The latest attempt N = the newest ~/bench_ws/build_mavros_N.log (M2 creates it first). Finds the build (1) by its PID file
# ~/bench_ws/mavros_build_pid_N.txt (only if the Pi did not reboot since: boot_id) and (2) by build processes (colcon,
# make, cmake, compiler, linker, time) that work under ~/bench_ws/mavros. Sends INT, then TERM, then KILL, 20 s apart, and
# checks that nothing is left. Safe if nothing runs (then it signals nothing and writes nothing).
# Writes only ~/bench_ws/mavros_build_stop_N.txt (if something was stopped and the file is not there yet; the window of M2
# then says «остановили снаружи»). Never deletes anything. No sudo, no network. Last line: RC3M_M2STOP_OK.
# Next attempt: M2 with N+1 (colcon continues). Env (test on the PC only): RC3M_HOST.
HOST_EXPECTED="${RC3M_HOST:-bumblebee-20ec}"
W="$HOME/bench_ws/mavros"
export HOST_EXPECTED W
r3_scan() {   # BUSY = PIDs of build processes under ~/bench_ws/mavros; prints them
  local p cw cl m; BUSY=
  for p in $(pgrep -x 'colcon|make|gmake|cmake|cc1plus|cc1|c\+\+|g\+\+|gcc|collect2|ld|as|time' 2>/dev/null); do
    m=; cw=$(readlink "/proc/$p/cwd" 2>/dev/null) || cw=; cl=$( { tr '\0' ' ' < "/proc/$p/cmdline"; } 2>/dev/null ) || cl=
    case "$cw/" in "$W"/*) m=1 ;; esac
    case " $cl " in *"$W"/*|*"$W "*) m=1 ;; esac
    if [ -n "$m" ]; then echo "  идёт: PID $p $(cat "/proc/$p/comm" 2>/dev/null), папка $cw: ${cl:0:150}"; BUSY="$BUSY $p"; fi
  done; }
r3_group_is_build() {   # the process group $1 has at least one process working under ~/bench_ws/mavros
  local p cw
  for p in $(pgrep -g "$1" 2>/dev/null); do
    cw=$(readlink "/proc/$p/cwd" 2>/dev/null) || cw=
    case "$cw/" in "$W"/*) return 0 ;; esac
  done
  return 1; }
echo "=== $(date '+%F %T') M2-СТОП: остановка сборки MAVROS"
( set -o pipefail
  if [ "$(hostname)" != "$HOST_EXPECTED" ]; then echo "СТОП: это не $HOST_EXPECTED"; exit 1; fi
  LN=$(ls "$HOME"/bench_ws/build_mavros_*.log 2>/dev/null | sort -V | tail -1)
  N=$(basename "${LN:-x}" | sed -n 's/^build_mavros_\([0-9][0-9]*\)\.log$/\1/p')
  PG=; SF=
  if [ -n "$N" ]; then
    SF="$HOME/bench_ws/mavros_build_stop_$N.txt"
    PF="$HOME/bench_ws/mavros_build_pid_$N.txt"
    echo "последняя попытка: N=$N ($LN)"
    if [ -f "$PF" ]; then
      PG=$(sed -n 's/^PGID=//p' "$PF"); B=$(sed -n 's/^boot_id=//p' "$PF")
      echo "файл PID: $PF (группа $PG)"
      if [ "$B" != "$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)" ]; then echo "Pi перезагружался после этой попытки: этой группы сборки нет"; PG=; fi
      case "$PG" in ''|*[!0-9]*) PG= ;; esac
    else
      echo "файла PID попытки N=$N нет (M2 его ещё не записал) — ищу процессы сборки"
    fi
  else
    echo "логов сборки нет (M2 ещё не запускался)"
  fi
  if [ -n "$PG" ] && r3_group_is_build "$PG"; then
    [ -e "$SF" ] || echo "m2_stop.sh $(date '+%F %T'): сборку N=$N остановили снаружи" > "$SF"
    for s in INT TERM KILL; do
      pgrep -g "$PG" >/dev/null 2>&1 || break
      echo "сигнал $s группе сборки $PG"
      kill -"$s" -- "-$PG" 2>/dev/null
      for i in $(seq 20); do pgrep -g "$PG" >/dev/null 2>&1 || break; sleep 1; done
    done
  else
    echo "группа сборки из файла PID не работает"
  fi
  for s in INT TERM KILL; do                                            # процессы сборки вне группы или без файла PID
    r3_scan > /dev/null
    [ -n "$BUSY" ] || break
    r3_scan
    if [ -n "$SF" ] && [ ! -e "$SF" ]; then echo "m2_stop.sh $(date '+%F %T'): процессы сборки N=$N остановлены снаружи" > "$SF"; fi
    echo "сигнал $s процессам сборки:$BUSY"
    kill -"$s" $BUSY 2>/dev/null
    for i in $(seq 20); do r3_scan > /dev/null; [ -n "$BUSY" ] || break; sleep 1; done
  done
  r3_scan > /dev/null
  if [ -n "$BUSY" ]; then r3_scan; echo "СТОП: процессы сборки остались (выше). Прислать Claude этот вывод"; exit 1; fi
  echo "процессов сборки MAVROS под $W нет"
  echo 'СБОРКА MAVROS ОСТАНОВЛЕНА ГОТОВО (или не шла). Окно M2 само напишет «СТОП … остановили снаружи». Дальше — M2 с N+1' )
RC=$?
if [ "$RC" != 0 ]; then echo "=== СТОП: M2-СТОП не закончил (код $RC). Прислать Claude этот вывод."; exit 1; fi
echo RC3M_M2STOP_OK
