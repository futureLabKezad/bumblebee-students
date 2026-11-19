#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2, по решению чата 1 в 19:19). Какой MAVROS стоит и активен на Pi, из какого коммита собран, совпадают ли пять исходных файлов bp02.
# Ничего не пишет на дрон, файлов на Pi не создаёт (git только читает). Список «sha256  путь» подставляет ПК (run_mavros_check.ps1) вместо строки #@@LIST@@ в памяти.
# Где искать: исходники ~/bench_ws/mavros/src/mavros-source (так в наборе MAVROS rc3: m1_unpack.sh, m2_build.sh), файл ~/bench_ws/mavros_src_mode.txt (там строка commit=...).
# stdout: MAVROS_APT, MAVROS_ACTIVE_PREFIX, MAVROS_PKG_VERSION, MAVROS_SRC_MODE <строка>, MAVROS_GIT_HEAD, MAVROS_SRC <путь> OK|DIFF|MISSING, MAVROS_BIN <sha256> <путь>, BB_MAVROS_CHECK ..., BB_MAVROS_CHECK_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
# Оверлеи, которые подключает запуск службы (start_bumblebee.sh): подключаются ТОЛЬКО строки source ровно из четырёх известных (ros2_ws, mavros, r2j, port), как их подключил бы запуск; так видно, что исполняется на самом деле.
if [ -f "$HOME/start_bumblebee.sh" ]; then
  while IFS= read -r l; do
    case "$l" in
      "source /home/lb/ros2_ws/install/setup.bash"|"source /home/lb/bench_ws/mavros/install/local_setup.bash"|"source /home/lb/bench_ws/r2j/install/local_setup.bash"|"source /home/lb/bench_ws/port/install/local_setup.bash")
        f="$HOME/${l#source /home/lb/}"; [ -f "$f" ] && source "$f" < /dev/null 2>/dev/null ;;
    esac
  done < "$HOME/start_bumblebee.sh"
fi
# BB_MAVROS_MARK
LIST='
#@@LIST@@
'
echo "MAVROS_APT $(dpkg-query -W -f='${Package}=${Version}' ros-jazzy-mavros 2>&1 | head -1)"
PFX=$(timeout 30 ros2 pkg prefix mavros < /dev/null 2>/dev/null | head -1)
echo "MAVROS_ACTIVE_PREFIX ${PFX:-none}"
if [ -n "$PFX" ] && [ -f "$PFX/share/mavros/package.xml" ]; then
  echo "MAVROS_PKG_VERSION $(grep -o '<version>[^<]*' "$PFX/share/mavros/package.xml" | head -1 | sed 's/<version>//')"
fi
SRC="$HOME/bench_ws/mavros/src/mavros-source"
MODE="$HOME/bench_ws/mavros_src_mode.txt"
if [ -f "$MODE" ]; then head -5 "$MODE" | while IFS= read -r l; do echo "MAVROS_SRC_MODE $l"; done; else echo "MAVROS_SRC_MODE none (нет $MODE)"; fi
if [ -d "$SRC/.git" ] && command -v git >/dev/null 2>&1; then
  echo "MAVROS_GIT_HEAD $(git -C "$SRC" rev-parse HEAD 2>&1 | head -1)"
  echo "MAVROS_GIT_TAG $(git -C "$SRC" describe --tags 2>&1 | head -1)"
else
  echo "MAVROS_GIT_HEAD none"
fi
ok=0; diff=0; miss=0
while read -r want path; do
  case "$want" in ''|\#*) continue;; esac
  if [ ! -f "$SRC/$path" ]; then echo "MAVROS_SRC $path MISSING"; miss=$((miss+1)); continue; fi
  got=$(sha256sum "$SRC/$path" 2>/dev/null | cut -c1-64)
  if [ "$got" = "$want" ]; then ok=$((ok+1)); echo "MAVROS_SRC $path OK"; else diff=$((diff+1)); echo "MAVROS_SRC $path DIFF got=$got want=$want"; fi
done <<< "$LIST"
for f in libmavros.so libmavros_plugins.so mavros_node; do
  find "${PFX:-/nonexistent}" "$HOME/bench_ws/mavros/install" /opt/ros/jazzy/lib -maxdepth 4 -name "$f" -type f 2>/dev/null | head -3 | while IFS= read -r p; do echo "MAVROS_BIN $(sha256sum "$p" 2>/dev/null | cut -c1-64) $p"; done
done
echo "BB_MAVROS_CHECK src_ok=$ok src_diff=$diff src_missing=$miss"
echo "BB_MAVROS_CHECK_DONE"
