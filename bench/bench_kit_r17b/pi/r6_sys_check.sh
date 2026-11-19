#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 12.11.2026, набор r6; проверка «ничего не отвалилось» Ч1–Ч6 из разбора P1 /work/pi_load_20261112/P1, поправки скептика V1).
# Делать ДО каждой системной правки (снимок «до») и ПОСЛЕ неё, и ещё раз после перезагрузки. Сравнение с «до» делает ПК (run_r6_syscheck.ps1).
# Ч1: systemctl --failed (должно быть пусто).
# Ч2: bumblebee, wifi-manager, wifi-watchdog, notify-manager, avahi-daemon, NetworkManager, sys_metrics: ActiveState, NRestarts, MainPID, время входа в active
#     (по нему ПК видит перезапуск после снимка «до» в ту же загрузку); журнал каждой службы за 10 минут: Traceback, ImportError, «Failed with result» и т.п. (как шаг 18).
#     led-default только справкой: на исправном дроне 12.11 он не работает (unit есть, не включён; V1), поэтому шаг 18 r5 там даёт NOT_OK.
# Ч3: энергосбережение Wi-Fi выключено: последняя строка ядра set_power_mgmt этой загрузки (journalctl -b -k, без sudo) и iw, если он есть.
# Ч4: ros2 node list --no-daemon (демон не остаётся, V1); ПК сравнивает со снимком «до».
# Ч5: pidstat -u -h -l 5 6 (30 секунд) для сравнения, это не критерий.
# Ч6: что владелец смотрит в приложении сам (печатает ПК).
# Плюс справка для ПК: состояние таймеров и snap hold из ступени 1 (ПК проверяет, что применённая правка держится и после перезагрузки).
# Ничего не пишет на Pi, sudo не использует, службы не трогает. Около 1 минуты. stdout: строки SC_*, последняя BB_R6SC_DONE.
# Только для тестов на ПК: BB_TEST_PROC, BB_TEST_NOROS.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6SC_MARK
export LC_ALL=C
PROC="${BB_TEST_PROC:-/proc}"
red() { sed -E 's/((pass(word)?|psk|secret|token|key)[=: ]+)[^ ]+/\1***/Ig'; }
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
echo "SC_DATE $(date '+%F %T %z')"
echo "SC_BOOT_ID $(cat "$PROC/sys/kernel/random/boot_id" 2>/dev/null)"
echo "SC_UPTIME_S $(cut -d' ' -f1 "$PROC/uptime" 2>/dev/null)"
# Ч1
f=$(systemctl --failed --no-legend --plain --no-pager 2>&1)
n=$(printf '%s\n' "$f" | grep -c .)
echo "SC_FAILED_COUNT $n"
printf '%s\n' "$f" | grep . | cut -c1-200 | while IFS= read -r l; do echo "SC_FAILED $l"; done
# Ч2
ERRPAT='Traceback|ImportError|ModuleNotFoundError|AttributeError|Failed with result|code=exited, status=[1-9]|code=dumped'
for s in bumblebee wifi-manager wifi-watchdog notify-manager avahi-daemon NetworkManager sys_metrics; do
  load=unknown; act=unknown; sub=unknown; nr=unknown; pid=0; em=0
  while IFS='=' read -r k v; do
    case "$k" in LoadState) load="$v";; ActiveState) act="$v";; SubState) sub="$v";; NRestarts) nr="$v";; MainPID) pid="$v";; ActiveEnterTimestampMonotonic) em="$v";; esac
  done < <(systemctl show "$s" -p LoadState -p ActiveState -p SubState -p NRestarts -p MainPID -p ActiveEnterTimestampMonotonic 2>/dev/null)
  case "$nr" in ''|*[!0-9]*) nr=unknown;; esac
  echo "SC_SVC $s load=${load:-unknown} active=${act:-unknown} sub=${sub:-unknown} nrestarts=$nr mainpid=${pid:-0} enter_mono=${em:-0}"
  j=$(journalctl -u "$s" --since "-10 min" --no-pager 2>&1)
  access=ok
  case "$j" in *"insufficient permissions"*|*"not seeing messages from other users"*) access=denied;; esac
  e=$(printf '%s\n' "$j" | grep -c -E "$ERRPAT")
  echo "SC_JERR $s errors=$e access=$access"
  printf '%s\n' "$j" | grep -E "$ERRPAT" | tail -n 5 | cut -c1-240 | red | while IFS= read -r l; do echo "SC_JERR_LINE $s | $l"; done
done
for s in led-default bumblebee-portguard bumblebee-ros-watchdog; do
  echo "SC_INFO $s enabled=$(systemctl is-enabled "$s" 2>&1 | head -1) active=$(systemctl is-active "$s" 2>&1 | head -1) nrestarts=$(systemctl show -p NRestarts --value "$s" 2>/dev/null | head -1)"
done
# Ч3
j=$(journalctl -b -k --no-pager 2>&1 | grep -E 'set_power_mgmt|insufficient permissions|not seeing messages' | tail -n 3)
case "$j" in
  *"insufficient permissions"*|*"not seeing messages"*) echo "SC_WIFI journal=denied" ;;
  "") echo "SC_WIFI journal=none" ;;
  *) last=$(printf '%s\n' "$j" | grep set_power_mgmt | tail -1); v=unknown
     case "$last" in *"power save disabled"*) v=disabled;; *"power save enabled"*) v=enabled;; esac
     echo "SC_WIFI journal=$v"
     echo "SC_WIFI_LINE $(printf '%s' "$last" | cut -c1-200)" ;;
esac
if command -v iw >/dev/null 2>&1; then
  w=$(iw dev wlan0 get power_save 2>&1 | head -1)
  case "$w" in *"Power save: off"*) echo "SC_WIFI_IW off";; *"Power save: on"*) echo "SC_WIFI_IW on";; *) echo "SC_WIFI_IW n/a $(printf '%s' "$w" | cut -c1-80)";; esac
else
  echo "SC_WIFI_IW n/a (нет iw)"
fi
# Справка: правки ступени 1 (их применённость проверяет ПК по журналам шагов 23)
for u in fwupd-refresh.timer man-db.timer motd-news.timer update-notifier-download.timer update-notifier-motd.timer; do
  echo "SC_STEP1 $u enabled=$(systemctl is-enabled "$u" 2>&1 | head -1) active=$(systemctl is-active "$u" 2>&1 | head -1)"
done
h=$(snap refresh --time 2>&1 | grep -E '^hold:' | head -1 | sed -E 's/^hold:[[:space:]]*//')
echo "SC_STEP1 snap hold=${h:-none}"
# Ч4
ros_env
nodes=$(timeout 40 ros2 node list --no-daemon --spin-time 5 < /dev/null 2>/dev/null); rc=$?
echo "SC_NODES_RC $rc"
printf '%s\n' "$nodes" | grep . | sed -E 's/transform_listener_impl_[0-9a-f]+/transform_listener_impl_X/' | LC_ALL=C sort | while IFS= read -r l; do echo "SC_NODE $l"; done
# Ч5 (после ros2: пауза 5 с, чтобы его запуск не попал в замер)
sleep 5
if command -v pidstat >/dev/null 2>&1; then
  LC_ALL=C timeout 60 pidstat -u -h -l 5 6 2>&1 | red | cut -c1-300 | while IFS= read -r l; do echo "SC_PS $l"; done
else
  echo "SC_PS absent (нет pidstat)"
fi
echo "BB_R6SC_DONE"
