#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 12.11.2026, набор r6; шаг 0 разбора P1 /work/pi_load_20261112/P1, поправки скептика V1). Что грузит Pi 20EC.
# Читает: службы и их главные процессы (systemctl show -p MainPID), процессы стека (потомки MainPID службы bumblebee), регулятор частоты ядер,
# температуру и троттлинг, энергосбережение Wi-Fi (без sudo: journalctl -b -k, строки set_power_mgmt; файлы conf.d NetworkManager только читаются),
# snap refresh --time, systemctl list-timers --all, apt-config dump | grep -i periodic, подписчиков тем *_reliable (ros2 topic info -v --no-daemon),
# список узлов (ros2 node list --no-daemon), затем pidstat -u -r -h -l 5 24 (2 минуты).
# Ничего не пишет на Pi (файлов не создаёт), sudo не использует, службы, стек и PX4 не трогает.
# По V1: ros2 только с --no-daemon (демон не остаётся); ros2 topic hz по кадрам НЕ используется (он сам грузит Pi);
#        notify_manager --selftest НЕ запускается (это не только чтение); /tmp/bumblebee.log не читается и не трогается (его читает portguard).
# Строки с командными строками процессов проходят через маску слов pass/psk/secret/token/key (на всякий случай: паролей в выводе быть не должно).
# Около 3 минут. stdout: строки LOAD_* и PS5 (pidstat), последняя строка BB_R6LOAD_DONE.
# Только для тестов на ПК: BB_TEST_PROC, BB_TEST_SYS, BB_TEST_ETC, BB_TEST_NOROS (на дроне они не заданы: /proc, /sys, /etc и окружение ROS как у стека).
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6LOAD_MARK
export LC_ALL=C
PROC="${BB_TEST_PROC:-/proc}"; SYSR="${BB_TEST_SYS:-/sys}"; ETC="${BB_TEST_ETC:-/etc}"
red() { sed -E 's/((pass(word)?|psk|secret|token|key)[=: ]+)[^ ]+/\1***/Ig'; }
ros_env() {
  [ -n "${BB_TEST_NOROS:-}" ] && return 0
  source /etc/profile.d/bumblebee-ros.sh < /dev/null > /dev/null 2>&1
  source /opt/ros/jazzy/setup.bash < /dev/null > /dev/null 2>&1
  # те же четыре известные строки source, что подключает запуск службы (start_bumblebee.sh); посторонние строки не выполняются
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
echo "LOAD_DATE $(date '+%F %T %z')"
echo "LOAD_UPTIME_S $(cut -d' ' -f1 "$PROC/uptime" 2>/dev/null)"
echo "LOAD_BOOT_ID $(cat "$PROC/sys/kernel/random/boot_id" 2>/dev/null)"
echo "LOAD_LOADAVG $(cut -d' ' -f1-3 "$PROC/loadavg" 2>/dev/null)"
echo "LOAD_CPUS $(nproc 2>/dev/null)"
for c in "$SYSR"/devices/system/cpu/cpu[0-9]*; do
  [ -d "$c" ] || continue
  n="${c##*/}"
  g=$(cat "$c/cpufreq/scaling_governor" 2>/dev/null || echo n/a)
  cur=$(cat "$c/cpufreq/scaling_cur_freq" 2>/dev/null || echo n/a)
  mn=$(cat "$c/cpufreq/scaling_min_freq" 2>/dev/null || echo n/a)
  mx=$(cat "$c/cpufreq/scaling_max_freq" 2>/dev/null || echo n/a)
  echo "LOAD_GOVERNOR $n governor=$g cur_khz=$cur min_khz=$mn max_khz=$mx"
done
echo "LOAD_GOVERNORS_AVAILABLE $(cat "$SYSR/devices/system/cpu/cpu0/cpufreq/scaling_available_governors" 2>/dev/null || echo n/a)"
if command -v vcgencmd >/dev/null 2>&1; then
  echo "LOAD_TEMP $(vcgencmd measure_temp 2>&1)"
  echo "LOAD_THROTTLED $(vcgencmd get_throttled 2>&1)"
  echo "LOAD_ARM_CLOCK $(vcgencmd measure_clock arm 2>&1)"
else
  echo "LOAD_TEMP n/a (no vcgencmd) $(cat "$SYSR/class/thermal/thermal_zone0/temp" 2>/dev/null)"
fi
# Службы: состояние, главный процесс (MainPID) и его строка ps (pcpu у ps = среднее за всю жизнь процесса; за интервалы смотри pidstat ниже)
SVCS="bumblebee notify-manager wifi-manager wifi-watchdog sys_metrics bumblebee-portguard bumblebee-ros-watchdog avahi-daemon NetworkManager wpa_supplicant snapd unattended-upgrades lttng-sessiond udisks2 rsyslog cron polkit ssh systemd-journald systemd-resolved systemd-timesyncd systemd-logind systemd-udevd dbus led-default fwupd"
for s in $SVCS; do
  st=$(systemctl show -p ActiveState --value "$s" 2>/dev/null | head -1)
  pid=$(systemctl show -p MainPID --value "$s" 2>/dev/null | head -1)
  nr=$(systemctl show -p NRestarts --value "$s" 2>/dev/null | head -1)
  en=$(systemctl is-enabled "$s" 2>/dev/null | head -1)
  echo "LOAD_SERVICE $s active=${st:-unknown} enabled=${en:-unknown} mainpid=${pid:-0} nrestarts=${nr:-unknown}"
  case "$pid" in ''|0|*[!0-9]*) continue;; esac
  ps -o pid=,ppid=,pcpu=,pmem=,rss=,etimes=,nlwp=,comm=,args= -p "$pid" 2>/dev/null | cut -c1-300 | red | while IFS= read -r l; do echo "LOAD_PS $s $l"; done
done
# Процессы стека: все потомки главного процесса службы bumblebee
BPID=$(systemctl show -p MainPID --value bumblebee 2>/dev/null | head -1)
case "$BPID" in
  ''|0|*[!0-9]*) echo "LOAD_STACK none (служба bumblebee не работает)" ;;
  *) ps -eo pid=,ppid= 2>/dev/null | awk -v root="$BPID" '{p[$1]=$2} END {for (k in p) {x=k; n=0; while ((x in p) && n<60) {if (p[x]==root) {print k; break}; x=p[x]; n++}}}' | sort -n | while read -r c; do
       ps -o pid=,ppid=,pcpu=,pmem=,rss=,etimes=,nlwp=,comm=,args= -p "$c" 2>/dev/null | cut -c1-300 | red | while IFS= read -r l; do echo "LOAD_STACK $l"; done
     done ;;
esac
# Энергосбережение Wi-Fi без sudo: последние строки ядра set_power_mgmt этой загрузки (урок Wi-Fi: проверять, что правка действительно применилась)
j=$(journalctl -b -k --no-pager -o short-monotonic 2>&1 | grep -E 'set_power_mgmt|insufficient permissions|not seeing messages' | tail -n 6)
case "$j" in
  *"insufficient permissions"*|*"not seeing messages"*) echo "LOAD_WIFI_PS_JOURNAL access=denied last=unknown" ;;
  "") echo "LOAD_WIFI_PS_JOURNAL access=ok last=none" ;;
  *) last=$(printf '%s\n' "$j" | grep set_power_mgmt | tail -1); v=unknown
     case "$last" in *"power save disabled"*) v=disabled;; *"power save enabled"*) v=enabled;; esac
     echo "LOAD_WIFI_PS_JOURNAL access=ok last=$v"
     printf '%s\n' "$j" | grep set_power_mgmt | cut -c1-200 | while IFS= read -r l; do echo "LOAD_WIFI_PS_LINE $l"; done ;;
esac
if command -v iw >/dev/null 2>&1; then echo "LOAD_WIFI_PS_IW $(iw dev wlan0 get power_save 2>&1 | head -1)"; else echo "LOAD_WIFI_PS_IW n/a (нет iw)"; fi
for d in /usr/lib/NetworkManager/conf.d /run/NetworkManager/conf.d "$ETC/NetworkManager/conf.d"; do
  for f in "$d"/*.conf; do
    [ -f "$f" ] || continue
    v=$(grep -h -E '^[[:space:]]*wifi\.powersave[[:space:]]*=' "$f" 2>/dev/null | tail -1 | tr -d ' ')
    echo "LOAD_NM_CONF $f ${v:-(нет wifi.powersave)}"
  done
done
# Обновления и таймеры
snap refresh --time 2>&1 | head -8 | while IFS= read -r l; do echo "LOAD_SNAP $l"; done
systemctl list-timers --all --no-pager 2>&1 | head -60 | while IFS= read -r l; do echo "LOAD_TIMER $l"; done
apt-config dump 2>/dev/null | grep -i periodic | while IFS= read -r l; do echo "LOAD_APT $l"; done
# Подписчики тем *_reliable (их публикует qos_relay; V1: читает ли их кто-то, например bumblebee_controller) и список узлов. Только --no-daemon.
ros_env
for t in /mavros/mavros/pose_reliable /mavros/mavros/velocity_local_reliable /mavros/mavros/data_reliable; do
  o=$(timeout 40 ros2 topic info -v --no-daemon --spin-time 5 "$t" < /dev/null 2>&1)
  pubs=$(printf '%s\n' "$o" | grep -m1 -E '^Publisher count:' | awk '{print $3}')
  subs=$(printf '%s\n' "$o" | grep -m1 -E '^Subscription count:' | awk '{print $3}')
  echo "LOAD_RELIABLE $t publishers=${pubs:-unknown} subscribers=${subs:-unknown}"
  printf '%s\n' "$o" | grep -E '^(Node name|Node namespace|Endpoint type):' | while IFS= read -r l; do echo "LOAD_RELIABLE_EP $t $l"; done
done
timeout 40 ros2 node list --no-daemon --spin-time 5 < /dev/null 2>/dev/null | while IFS= read -r l; do [ -n "$l" ] && echo "LOAD_NODE $l"; done
# Пауза, чтобы команды ros2 выше не попали в замер, потом pidstat: 24 интервала по 5 секунд
sleep 10
if command -v pidstat >/dev/null 2>&1; then
  LC_ALL=C timeout 150 pidstat -u -r -h -l 5 24 2>&1 | red | cut -c1-400 | while IFS= read -r l; do echo "PS5 $l"; done
  echo "LOAD_PIDSTAT done"
else
  echo "LOAD_PIDSTAT absent (нет pidstat)"
fi
echo "BB_R6LOAD_DONE"
