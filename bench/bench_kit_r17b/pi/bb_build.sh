#!/bin/bash
# МЕНЯЕТ ДРОН (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58). Пересборка ТОЛЬКО пакета bumblebee из исходников r2j в ОТДЕЛЬНОМ рабочем каталоге ~/bench_ws/r2j (оверлей), как это уже делалось на этом дроне 29.10 (набор s0b, step8b_build.sh: 2 мин 26 с).
# Что делает: копирует ~/ros2_ws/src/bumblebee (исходники образа r2j, установленные шагом 05) в ~/bench_ws/r2j/src/bumblebee без __pycache__, проверяет sha256 C++ исходников по списку r2j, собирает в чистом окружении
# (только /opt/ros/jazzy) командой MAKEFLAGS=-j2 colcon build --packages-select bumblebee --cmake-args -DBUILD_TESTING=OFF, пишет журнал ~/bench_ws/build_r2j_1.log.
# НЕ трогает: ~/ros2_ws (ни src, ни install: прежняя сборка остаётся как есть, это и есть резерв), /opt/ros, start_bumblebee.sh (подключение оверлея отдельным шагом 16), параметры PX4, службу. Ничего не удаляет и не перезаписывает.
# Любой stderr сборки = СТОП и показ строк (как в плане 6.3: известное предупреждение «led_msgs not found — skipping led node» решает чат 1, заранее не принимается). Список C++ подставляет ПК вместо #@@CPP@@ в памяти; sha256 hover r6 вместо #@@HOVER@@ (r3: в исходниках и в копии оверлея должен быть скрипт висения hover r6).
# Последняя строка при успехе: BB_BBBUILD_OK <секунды>; при остановке из-за stderr: BB_BBBUILD_STDERR (сборка прошла, смотреть строки); иначе BB_BBBUILD_STOP.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_BBBUILD_MARK
CPP='
#@@CPP@@
'
HOVERTXT='
#@@HOVER@@
'
HOVER=$(printf '%s\n' "$HOVERTXT" | grep -E '^[0-9a-f]{64}$' | head -1)
stop() { echo "BB_BBBUILD_STOP $*"; exit 1; }
W="$HOME/bench_ws/r2j"
L="$HOME/bench_ws/build_r2j_1.log"
[ ! -e "$W" ] || stop "уже есть $W, ничего не перезаписываю"
[ ! -e "$L" ] || stop "уже есть $L, ничего не перезаписываю"
[ -f "$HOME/ros2_ws/src/bumblebee/package.xml" ] || stop "нет исходников ~/ros2_ws/src/bumblebee (сначала 05_install_r2j.cmd)"
if systemctl is-active --quiet bumblebee; then stop "служба bumblebee запущена: остановите сами (sudo systemctl stop bumblebee, пароль вводите вы)"; fi
[ ! -e "$HOME/.colcon/defaults.yaml" ] || stop "есть ~/.colcon/defaults.yaml: он может тихо поменять сборку"
busy=$(ps -eo comm= 2>/dev/null | grep -c -E '^(colcon|cmake|make|cc1plus)$')
[ "${busy:-0}" -eq 0 ] || stop "идёт другая сборка ($busy процессов)"
while read -r want path flag; do
  case "$want" in ''|\#*) continue;; esac
  [ "$(sha256sum "$HOME/$path" 2>/dev/null | cut -c1-64)" = "$want" ] || stop "исходник не равен r2j: $path"
done <<< "$CPP"
# r3 (замечание проверки 11.11): hover r6 (по sha256) есть в исходниках образа и потом в копии оверлея, иначе стоп до сборки
[ -n "$HOVER" ] || stop "в скрипте нет суммы hover r6"
[ "$(find "$HOME/ros2_ws/src/bumblebee/examples" -type f -name '*.py' -exec sha256sum {} + 2>/dev/null | grep -c "^$HOVER ")" -ge 1 ] || stop "в ~/ros2_ws/src/bumblebee/examples нет скрипта висения hover r6 (sha256 $HOVER)"
mkdir -p "$W/src" || stop "не создать $W/src"
( cd "$HOME/ros2_ws/src" && tar --exclude=__pycache__ -cf - bumblebee ) | ( cd "$W/src" && tar -xf - ) || stop "копирование исходников не удалось"
[ -f "$W/src/bumblebee/package.xml" ] || stop "после копирования нет package.xml"
[ -z "$(find "$W/src" -name __pycache__)" ] || stop "в копии есть __pycache__"
while read -r want path flag; do
  case "$want" in ''|\#*) continue;; esac
  rel="${path#ros2_ws/src/}"
  [ "$(sha256sum "$W/src/$rel" 2>/dev/null | cut -c1-64)" = "$want" ] || stop "копия исходника не равна r2j: $rel"
done <<< "$CPP"
[ "$(find "$W/src/bumblebee/examples" -type f -name '*.py' -exec sha256sum {} + 2>/dev/null | grep -c "^$HOVER ")" -ge 1 ] || stop "в копии оверлея нет скрипта висения hover r6 (sha256 $HOVER)"
echo "ИСХОДНИКИ r2j В $W ГОТОВО"
date; free -h; uptime
T0=$(date +%s)
env -i HOME="$HOME" USER="$USER" LANG=C.UTF-8 PATH=/usr/sbin:/usr/bin:/sbin:/bin bash --noprofile --norc -c 'source /opt/ros/jazzy/setup.bash
  case ":$AMENT_PREFIX_PATH:$CMAKE_PREFIX_PATH:$COLCON_PREFIX_PATH:" in *ros2_ws*|*bench_ws*) echo "СТОП: в окружении сборки есть ros2_ws или bench_ws"; exit 1 ;; esac
  cd ~/bench_ws/r2j || exit 1
  MAKEFLAGS=-j2 colcon build --packages-select bumblebee --cmake-args -DBUILD_TESTING=OFF' 2>&1 | tee "$L"
T1=$(date +%s)
date; free -h
grep -a '^Summary: 1 package finished' "$L" || stop "сборка не завершилась строкой Summary (смотреть $L)"
if grep -a -E '^ +[0-9]+ packages? (failed|aborted)|not processed' "$L"; then stop "сборка не прошла"; fi
if grep -a -E 'packages? had stderr output' "$L" || grep -a '^--- stderr:' "$L" || { grep -a '^WARNING:' "$L" | grep -a -v 'underlay workspaces'; }; then
  echo "BB_BBBUILD_STDERR $((T1-T0)) с: у сборки есть stderr (строки выше). Шаги дальше не делать, прислать журнал $L Claude и чату 1"
  exit 2
fi
echo "BB_BBBUILD_OK $((T1-T0))"
