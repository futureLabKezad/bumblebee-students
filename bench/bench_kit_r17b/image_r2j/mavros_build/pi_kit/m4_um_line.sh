#!/bin/bash
# rc3 MAVROS overlay, step УМ (Pi): one extra line in ~/start_bumblebee.sh that sources the MAVROS overlay BEFORE the
# port overlay. Claude, 30.10.2026. Written like У2 (plan 7.6): same checks, copies before mv, '.bbnew', never overwrites.
# Order in session 1b: У2 (plan block, unchanged) -> УМ (this) -> one 'sudo reboot' (the owner) -> 7.4 rc3 with STEP=UM.
# Result (lines 17-19 of start_bumblebee.sh):
#   source /home/lb/ros2_ws/install/setup.bash
#   source /home/lb/bench_ws/mavros/install/local_setup.bash      <- УМ
#   source /home/lb/bench_ws/port/install/local_setup.bash        <- У2
# Why after ros2_ws: ros2_ws/install/setup.bash re-sources its underlay /opt/ros/jazzy, which would move /opt in front of
# an overlay sourced earlier. local_setup.bash does not re-source underlays, so the overlay sourced later wins.
# Rollback: plan 9.2 unchanged (it installs ~/bench_baseline/start_bumblebee.sh.0 = the baseline, both lines go).
# Needs BD (session folder). Prints 'УМ ГОТОВО' and RC3M_M4_OK; then the launcher asks for 'sudo reboot' (owner).
# Env (test on the PC only): RC3M_HOST, RC3M_S (path of start_bumblebee.sh), RC3M_LB (/home/lb), RC3M_BBLOG (/tmp/bumblebee.log).
HOST_EXPECTED="${RC3M_HOST:-bumblebee-20ec}"
LB="${RC3M_LB:-/home/lb}"
S="${RC3M_S:-$LB/start_bumblebee.sh}"
BBLOG="${RC3M_BBLOG:-/tmp/bumblebee.log}"
OUT=$(mktemp)
export HOST_EXPECTED LB S BBLOG
echo "=== $(date '+%F %T') УМ: строка MAVROS-оверлея в start_bumblebee.sh"
{
( set -eo pipefail
  [ -n "$BD" ]
  [ -d "$BD" ]
  [ "$(hostname)" = "$HOST_EXPECTED" ]
  L_WS='source /home/lb/ros2_ws/install/setup.bash'
  L_M='source /home/lb/bench_ws/mavros/install/local_setup.bash'
  L_P='source /home/lb/bench_ws/port/install/local_setup.bash'
  [ -f "$BD/start_bumblebee.sh.2" ]                                                   # У2 в этой сессии был
  cmp -s "$S" "$BD/start_bumblebee.sh.2"                                              # файл ровно как после У2
  ( cd "$LB/bench_ws/mavros/install"
    sha256sum -c --quiet "$LB/bench_ws/MAVROS_ARM64_SHA256SUMS.txt" )               # оверлей = отпечатки M3
  [ -x "$LB/bench_ws/mavros/install/mavros/lib/mavros/mavros_node" ]
  [ "$(grep -c -x "$L_WS" "$S")" = 1 ]
  [ "$(grep -c -x "$L_P" "$S")" = 1 ]
  [ "$(grep -c 'bench_ws/mavros' "$S")" = 0 ]                                       # строки УМ ещё нет
  [ ! -e "$S.bbnew" ]                                                               # остался .bbnew — «Остался .bbnew» (п. 7)
  for f in start_bumblebee.sh.M diff_UM.txt bumblebee_before_UM.log watchdog_before_UM.txt clockjump_before_UM.txt; do
    [ ! -e "$BD/$f" ]                                                               # ничего не перезаписываем
  done
  sed '/^source \/home\/lb\/ros2_ws\/install\/setup.bash$/a source /home/lb/bench_ws/mavros/install/local_setup.bash' "$S" > "$S.bbnew"
  diff "$S" "$S.bbnew" > "$BD/diff_UM.txt" || true
  [ "$(grep -c '^[<>]' "$BD/diff_UM.txt")" = 1 ]                                    # ровно одна строка добавлена
  grep -qx "> $L_M" "$BD/diff_UM.txt"                                                # и это нужная строка
  nws=$(grep -n -x "$L_WS" "$S.bbnew" | cut -d: -f1)
  nm=$(grep -n -x "$L_M" "$S.bbnew" | cut -d: -f1)
  np=$(grep -n -x "$L_P" "$S.bbnew" | cut -d: -f1)
  echo "строки: ros2_ws $nws, mavros $nm, port $np"
  [ "$nm" = $((nws+1)) ]                                                            # MAVROS сразу после ros2_ws
  [ "$np" = $((nm+1)) ]                                                             # и прямо перед портом
  chmod 0755 "$S.bbnew"
  cp -p "$S.bbnew" "$BD/start_bumblebee.sh.M"
  cp "$BBLOG" "$BD/bumblebee_before_UM.log"                                  # логи — до замены файла
  journalctl -u bumblebee-ros-watchdog -b --no-pager > "$BD/watchdog_before_UM.txt"
  journalctl -u bumblebee-clock-jump -b --no-pager > "$BD/clockjump_before_UM.txt"
  mv -f "$S.bbnew" "$S"
  echo 'ФАЙЛ ЗАМЕНЁН'
  cmp -s "$S" "$BD/start_bumblebee.sh.M"
  echo 'УМ ГОТОВО: можно перезагружать' )
} 2>&1 | tee "$OUT"
RC=${PIPESTATUS[0]}
if [ "$RC" != 0 ]; then
  if grep -q "ФАЙЛ ЗАМЕНЁН" "$OUT"; then echo "=== СТОП: ФАЙЛ ЗАМЕНЁН, а «УМ ГОТОВО» нет. НЕ перезагружать. Сразу откат 9.2."; exit 1; fi
  if [ -e "$S.bbnew" ]; then echo "=== СТОП: УМ остановился, остался .bbnew. По плану: перенести его и 9.2 («Остался .bbnew», п. 7). УМ не повторять."; exit 1; fi
  echo "=== СТОП: УМ остановился до замены файла (файл как после У2). Не перезагружать, прислать Claude. По плану — 9.2."
  exit 1
fi
echo RC3M_M4_OK
