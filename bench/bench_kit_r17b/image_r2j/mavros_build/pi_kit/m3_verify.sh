#!/bin/bash
# rc3 MAVROS overlay, step M3 (Pi): check the built ~/bench_ws/mavros/install and take its prints (sha256 of every file).
# Claude, 30.10.2026 (README_RU.md). Read-only except three new files: ~/bench_ws/MAVROS_ARM64_SHA256SUMS.txt (all files),
# ~/bench_ws/MAVROS_ARM64_SO_SHA256.txt (the .so files and mavros_node) and ~/bench_ws/mavros_install_diff.txt (file-name
# differences from the PC dry run outside the main files). Never overwrites. No sudo.
# v2 02.11.2026: the source check accepts the no-git path of M1 v2 (~/bench_ws/mavros_src_mode.txt: MODE=git or tar).
# r3 02.11.2026 (old text: m3_verify.sh.r2): build type RELEASE (owner 02.11). rc3m_flags_check compares the build with the
#    PC reference Release build /work/ws_mavros214_bp02_rel (02.11.2026): CMakeCache CMAKE_BUILD_TYPE=Release,
#    CMAKE_CXX_FLAGS / CMAKE_C_FLAGS empty, CMAKE_CXX_FLAGS_RELEASE / CMAKE_C_FLAGS_RELEASE '-O3 -DNDEBUG', BUILD_TESTING
#    OFF, and CXX_FLAGS of mavros, mavros_plugins, mavros_node exactly as in that build's flags.make; anything else = stop.
#    No stderr is accepted in advance (unchanged): the expected GCC warning in setpoint_accel.cpp also stops M2 and M3
#    until Claude's written answer, then 'claude_ok'. Everything else as in r2.
# r2 02.11.2026 (review of 02.11; old text: m3_verify.sh.r1):
#  - refuses while the build still runs under ~/bench_ws/mavros (m2_stop.sh first);
#  - (replaced by r3) build type «как SITL» (empty CMAKE_BUILD_TYPE, no -O, no -DNDEBUG);
#  - no stderr accepted in advance: any stderr / WARNING in any build log = stop, unless 'claude_ok' (Claude's written answer);
#  - file list: the MAIN files (libraries in mavros/lib, mavros_node, mavros_plugins.xml, ament index entries) must be
#    exactly as in the PC dry run (EXPECTED_ESSENTIAL_FILES.txt), else stop. Other differences (colcon/ament service files:
#    the Pi has colcon-core 0.20.1 and ament_cmake 2.5.5, the PC 0.21.3 and 2.5.6) are printed and saved for Claude, not a stop;
#  - prints 'MSF_SHA256=<sha256 of MAVROS_ARM64_SHA256SUMS.txt>': the session kit passes it to m5 (RC3M_MSF_SHA256).
# Usage: bash m3_verify.sh            normal
#        bash m3_verify.sh claude_ok  only after Claude answered «принято» in writing on the stderr/WARNING lines of the
#                                     build logs (M2 stopped on them); then those log lines are not checked again.
# Env (dry run on the PC only): RC3M_HOST, RC3M_INC, RC3M_APT_ROOT (where libmavconn/mavros_msgs/mavros_extras must come
# from; Pi: /opt/ros/jazzy), RC3M_ARCH (ELF machine; Pi: AArch64), RC3M_DRYRUN_UNDERLAY (stand-in setup files),
# RC3M_DRYRUN_APTONLY (stand-in for apt mavros 2.14 in the «as today» comparison). On the Pi none is set.
# Tests on the PC: RC3M_SOURCE_ONLY=1 source this file, then call rc3m_install_cmp or rc3m_flags_check (tests/test_m3.sh).

# r3: the PC reference Release build /work/ws_mavros214_bp02_rel (02.11.2026), flags.make of the three product targets
REL_FLAGS_LIB='-Wall -Wextra -Wpedantic -Wcomment -O3 -DNDEBUG -std=gnu++20 -fPIC'   # mavros, mavros_plugins
REL_FLAGS_EXE='-Wall -Wextra -Wpedantic -Wcomment -O3 -DNDEBUG -std=gnu++20'         # mavros_node
rc3m_flags_check() {  # BUILD_DIR (= ~/bench_ws/mavros/build/mavros): Release exactly as the PC reference; 1 = stop
  local B="$1" CC="$1/CMakeCache.txt" e t fl want FM
  for e in 'CMAKE_BUILD_TYPE:STRING=Release' 'CMAKE_CXX_FLAGS:STRING=' 'CMAKE_C_FLAGS:STRING=' \
           'CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -DNDEBUG' 'CMAKE_C_FLAGS_RELEASE:STRING=-O3 -DNDEBUG' 'BUILD_TESTING:BOOL=OFF'; do
    if grep -q -x -F -- "$e" "$CC" 2>/dev/null; then echo "  $e"
    else echo "СТОП: в $CC нет строки «$e» (есть: $(grep -E "^${e%%:*}:" "$CC" 2>/dev/null | head -1))"; return 1; fi
  done
  for t in mavros mavros_plugins mavros_node; do
    FM="$B/CMakeFiles/$t.dir/flags.make"
    if [ "$t" = mavros_node ]; then want="$REL_FLAGS_EXE"; else want="$REL_FLAGS_LIB"; fi
    if [ ! -f "$FM" ]; then echo "СТОП: нет $FM"; return 1; fi
    fl=$(sed -n 's/^CXX_FLAGS = *//p' "$FM")
    echo "  $t: CXX_FLAGS = $fl"
    if [ "$fl" != "$want" ]; then echo "СТОП: флаги $t не как в эталонной Release-сборке ПК ($want)"; return 1; fi
  done
  echo "тип сборки Release, флаги трёх целей = эталон ПК /work/ws_mavros214_bp02_rel"
  return 0; }

# main files of the overlay (the set must be exactly as in the PC dry run)
rc3m_essential() { { grep -E '^\./mavros/lib/[^/]+\.so[^/]*$|^\./mavros/lib/mavros/mavros_node$|^\./mavros/share/mavros/mavros_plugins\.xml$|^\./mavros/share/ament_index/resource_index/[^/]+/[^/]+$' || true; } | LC_ALL=C sort; }
rc3m_install_cmp() {  # ACTUAL EXPECTED_ALL EXPECTED_ESSENTIAL OUT_DIFF  (file lists './path', one per line)
  local A="$1" E="$2" ES="$3" O="$4" AE
  AE=$(rc3m_essential < "$A")
  if [ "$AE" != "$(LC_ALL=C sort "$ES")" ]; then
    diff <(printf '%s\n' "$AE") <(LC_ALL=C sort "$ES") | sed 's/^/  /' || true
    echo "СТОП: главные файлы install/ не те, что в сухом прогоне на ПК (< есть только здесь, > нет здесь)"; return 1
  fi
  echo "главные файлы install/: $(printf '%s\n' "$AE" | wc -l), ровно как на ПК"
  diff <(LC_ALL=C sort "$A") <(LC_ALL=C sort "$E") > "$O" || true
  if [ -s "$O" ]; then
    echo "ОТЛИЧИЯ списка install/ от ПК вне главных файлов (не стоп; прислать Claude $O): $(grep -c '^[<>]' "$O") строк"
    grep '^[<>]' "$O" | head -60 | sed 's/^/  /' || true
  else
    echo "весь список install/ ($(wc -l < "$A") файлов) — как на ПК"
  fi
  return 0; }
if [ -n "$RC3M_SOURCE_ONLY" ]; then return 0 2>/dev/null || exit 0; fi

ARG="${1:-}"
HOST_EXPECTED="${RC3M_HOST:-bumblebee-20ec}"
INC="${RC3M_INC:-$HOME/bench_ws/incoming/rc3_mavros}"
APT_ROOT="${RC3M_APT_ROOT:-/opt/ros/jazzy}"
ARCH="${RC3M_ARCH:-AArch64}"
W="$HOME/bench_ws/mavros"
I="$W/install"
DEPS="$HOME/bench_ws/mavros_deps"
F="$HOME/bench_ws/MAVROS_ARM64_SHA256SUMS.txt"
SO="$HOME/bench_ws/MAVROS_ARM64_SO_SHA256.txt"
DF="$HOME/bench_ws/mavros_install_diff.txt"
export ARG HOST_EXPECTED INC APT_ROOT ARCH W I DEPS F SO DF REL_FLAGS_LIB REL_FLAGS_EXE
r3_busy() {   # build processes that work under ~/bench_ws/mavros (working folder or command line); prints them; 0 = found
  local p cw cl hit=1 m
  for p in $(pgrep -x 'colcon|make|gmake|cmake|cc1plus|cc1|c\+\+|g\+\+|gcc|collect2|ld|as|time' 2>/dev/null); do
    m=; cw=$(readlink "/proc/$p/cwd" 2>/dev/null) || cw=; cl=$( { tr '\0' ' ' < "/proc/$p/cmdline"; } 2>/dev/null ) || cl=
    case "$cw/" in "$W"/*) m=1 ;; esac
    case " $cl " in *"$W"/*|*"$W "*) m=1 ;; esac
    if [ -n "$m" ]; then echo "  идёт: PID $p $(cat "/proc/$p/comm" 2>/dev/null), папка $cw: ${cl:0:150}"; hit=0; fi
  done
  return $hit; }
echo "=== $(date '+%F %T') M3: проверка сборки MAVROS и отпечатки"
( set -eo pipefail
  [ "$(hostname)" = "$HOST_EXPECTED" ]
  case "$ARG" in ''|claude_ok) ;; *) echo "СТОП: аргумент только claude_ok"; exit 1 ;; esac
  for f in "$F" "$SO" "$DF"; do
    if [ -e "$f" ]; then echo "СТОП: $f уже есть (M3 не повторяется)"; exit 1; fi
  done
  if r3_busy; then echo "СТОП: сборка MAVROS ещё идёт (процессы выше). Дождаться конца M2 или m2_stop.sh"; exit 1; fi
  LN=$(ls "$HOME"/bench_ws/build_mavros_*.log | sort -V | tail -1)
  echo "последняя попытка: $LN"
  grep -a '^Summary: 1 package finished' "$LN"
  if grep -a -E '^ +[0-9]+ packages? (failed|aborted)|not processed' "$LN"; then echo 'СТОП: сборка не прошла'; exit 1; fi
  if [ "$ARG" = claude_ok ]; then
    echo "stderr/WARNING в логах сборки приняты Claude письменно (claude_ok): записать время ответа в протокол"
  else
    for g in "$HOME"/bench_ws/build_mavros_*.log; do                    # любой stderr — стоп (п. 6.3), заранее ничего не принято
      if grep -a -n -E 'packages? had stderr output|^--- stderr:' "$g"; then echo "СТОП: в $g есть stderr. Прислать Claude; после письменного «принято» — bash m3_verify.sh claude_ok"; exit 1; fi
      if grep -a -n -E '(^|\] )WARNING:' "$g"; then echo "СТОП: в $g предупреждение colcon. Прислать Claude; после письменного «принято» — claude_ok"; exit 1; fi
    done
  fi
  # исходники — та же метка, без правок
  tag=$(sed -n 's/^tag=//p' "$INC/EXPECTED_SRC.txt")
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
  echo "исходники: $tag $C"
  # настройки сборки (r3): Release, ровно как эталонная сборка ПК /work/ws_mavros214_bp02_rel
  CC="$W/build/mavros/CMakeCache.txt"
  rc3m_flags_check "$W/build/mavros" || exit 1
  grep -x 'mavlink_DIR:PATH=/opt/ros/jazzy/share/mavlink/cmake' "$CC"          # заголовки MAVLink этого дрона (apt)
  grep -x "angles_DIR:PATH=$DEPS/opt/ros/jazzy/share/angles/cmake" "$CC"
  for p in libmavconn mavros_msgs; do                                             # собрано против apt 2.14 этого дрона
    d=$(sed -n "s/^${p}_DIR:PATH=//p" "$CC")
    echo "${p}_DIR=$d"
    case "$d" in "$APT_ROOT"/*) ;; *) echo "СТОП: $p взят не из $APT_ROOT"; exit 1 ;; esac
  done
  # старые заголовки MAVROS из apt (/opt/ros/jazzy/include/mavros/*.hpp, там mavros_router.hpp 2.14.0) не попали ни в
  # один объектный файл: в путях есть -isystem /opt/ros/jazzy/include (от зависимостей), но -I исходников идёт раньше.
  # Доказательство — файлы зависимостей компилятора (*.o.d): какие заголовки на самом деле прочитаны.
  ND=$(find "$W/build/mavros" -name '*.o.d' | wc -l)
  echo "файлов зависимостей *.o.d: $ND"
  [ "$ND" -ge 30 ]
  if find "$W/build/mavros" -name '*.o.d' -print0 | xargs -0 grep -l '/opt/ros/jazzy/include/mavros/'; then
    echo 'СТОП: объектный файл собран с заголовком MAVROS из /opt/ros/jazzy/include/mavros (старый apt)'; exit 1
  fi
  NR=$(find "$W/build/mavros" -name '*.o.d' -print0 | xargs -0 grep -h -o '[^ ]*/mavros_router\.hpp' | sort -u)
  echo "mavros_router.hpp взят из: $NR"
  [ "$NR" = "$W/src/mavros-source/mavros/include/mavros/mavros_router.hpp" ]
  # нужные файлы
  for f in mavros/lib/libmavros.so mavros/lib/libmavros_plugins.so mavros/lib/mavros/mavros_node \
           mavros/share/mavros/mavros_plugins.xml mavros/share/ament_index/resource_index/mavros__pluginlib__plugin/mavros \
           mavros/share/ament_index/resource_index/packages/mavros mavros/share/mavros/local_setup.bash local_setup.bash; do
    [ -f "$I/$f" ]
  done
  cmp "$W/src/mavros-source/mavros/mavros_plugins.xml" "$I/mavros/share/mavros/mavros_plugins.xml"
  [ "$(cat "$I/mavros/share/ament_index/resource_index/mavros__pluginlib__plugin/mavros")" = share/mavros/mavros_plugins.xml ]
  for p in libmavconn mavros_msgs mavros_extras test_mavros; do
    if [ -e "$I/$p" ]; then echo "СТОП: в оверлее есть $p (собирается только mavros)"; exit 1; fi
  done
  # список файлов: главные — ровно как в сухом прогоне на ПК (имена; суммы другие: другая архитектура); остальное — Claude
  AL=$(mktemp)
  ( cd "$I" && find . -type f ! -path '*/__pycache__/*' | LC_ALL=C sort ) > "$AL"
  rc3m_install_cmp "$AL" "$INC/EXPECTED_INSTALL_FILES.txt" "$INC/EXPECTED_ESSENTIAL_FILES.txt" "$DF"
  for f in package_run_dependencies parent_prefix_path rclcpp_components; do
    echo "ament index $f/mavros: $(tr '\n' ' ' < "$I/mavros/share/ament_index/resource_index/$f/mavros" | cut -c1-300)"
  done
  for b in mavros/lib/libmavros.so mavros/lib/libmavros_plugins.so mavros/lib/mavros/mavros_node; do
    readelf -h "$I/$b" | grep -E "Machine: +$ARCH"
  done
  if [ "$tag" = backport-02 ]; then                                               # правка 97a14ae1 внутри
    n=$(grep -a -c 'already processed' "$I/mavros/lib/libmavros_plugins.so" || true)
    echo "строка 'already processed' в libmavros_plugins.so: $n"
    [ "$n" -ge 1 ]
  fi
  readelf -d "$I/mavros/lib/mavros/mavros_node" | grep -E 'NEEDED.*(mavros|mavconn)|RPATH|RUNPATH' || true
  readelf -d "$I/mavros/lib/libmavros_plugins.so" | grep -E 'NEEDED.*(mavros|mavconn)|RPATH|RUNPATH' || true
  LK=$(mktemp)
  # как увидит запуск: /opt, ~/ros2_ws, потом оверлей MAVROS (как строка УМ в start_bumblebee.sh)
  bash -c '
    source /opt/ros/jazzy/setup.bash
    if [ -f "$HOME/ros2_ws/install/setup.bash" ]; then source "$HOME/ros2_ws/install/setup.bash"; fi
    for f in $RC3M_DRYRUN_UNDERLAY; do source "$f"; done
    source "$I/local_setup.bash"
    set -eo pipefail
    TN=$(mktemp); TR=$(mktemp)
    P=$(ros2 pkg prefix mavros); echo "ros2 pkg prefix mavros: $P"
    [ "$P" = "$I/mavros" ]
    for p in libmavconn mavros_msgs mavros_extras; do
      q=$(ros2 pkg prefix $p); echo "ros2 pkg prefix $p: $q"
      case "$q" in "$APT_ROOT"|"$APT_ROOT"/*) ;; *) echo "СТОП: $p не из $APT_ROOT"; exit 1 ;; esac
    done
    python3 -c "
import os, sys
from ament_index_python import get_resources
r = get_resources(\"mavros__pluginlib__plugin\")
print(\"плагины (ament index):\", dict(sorted(r.items())))
ok = r.get(\"mavros\") == os.environ[\"I\"] + \"/mavros\" and r.get(\"mavros_extras\", \"\").startswith(os.environ[\"APT_ROOT\"])
sys.exit(0 if ok else 1)"
    ldd "$I/mavros/lib/mavros/mavros_node" > "$TN"
    grep -E "libmavros|libmavconn|not found" "$TN"
    grep -q "libmavros.so => $I/mavros/lib/libmavros.so " "$TN"
    grep -q "libmavros_plugins.so => $I/mavros/lib/libmavros_plugins.so " "$TN" || echo "mavros_node не ссылается на libmavros_plugins.so (плагины грузит pluginlib)"
    if grep -q "not found" "$TN"; then echo "СТОП: у mavros_node не найдена библиотека"; exit 1; fi
    for lib in "$I/mavros/lib/libmavros_plugins.so" "$I/mavros/lib/libmavros.so" "$I/mavros/lib/mavros/mavros_node"; do
      ldd -r "$lib" > "$TR" 2>&1                                        # новые библиотеки: ни одного неразрешённого символа
      echo "ldd -r $lib: $(grep -c "undefined symbol" "$TR" || true) неразрешённых символов"
      if grep -E "undefined symbol|not found" "$TR"; then echo "СТОП: $lib не связывается"; exit 1; fi
    done
    EX="$(ros2 pkg prefix mavros_extras)/lib/libmavros_extras_plugins.so"
    ldd -r "$EX" > "$TR" 2>&1                                            # extras apt поверх нового libmavros.so
    grep -E "libmavros.so|libmavconn|not found" "$TR"
    grep -q "libmavros.so => $I/mavros/lib/libmavros.so " "$TR"
    if grep -q "not found" "$TR"; then echo "СТОП: у $EX не найдена библиотека"; exit 1; fi
    grep "undefined symbol" "$TR" | awk "{print \$3}" | LC_ALL=C sort -u > "$TN"
    echo "$EX с оверлеем: неразрешённых символов $(wc -l < "$TN")"
    echo "временные файлы (не удаляются): $TN $TR"
    echo "СВЯЗЫВАНИЕ ГОТОВО"
    echo "EXTRAS_UNDEF_FILE=$TN"' | tee "$LK"
  # тот же extras так, как он работает сегодня (только apt, без оверлея): оверлей не должен добавить ни одного
  # неразрешённого символа. В 2.14.0 уже есть один такой символ (tf2::fromMsg<Transform, Affine3d>, плагин fake_gps,
  # на дроне он не загружается): он «ленивый» и не мешает, пока его не вызывают — так же, как сегодня.
  TO=$(sed -n 's/^EXTRAS_UNDEF_FILE=//p' "$LK")
  [ -f "$TO" ]
  TA=$(mktemp)
  bash -c '
    source /opt/ros/jazzy/setup.bash
    if [ -f "$HOME/ros2_ws/install/setup.bash" ]; then source "$HOME/ros2_ws/install/setup.bash"; fi
    for f in $RC3M_DRYRUN_UNDERLAY $RC3M_DRYRUN_APTONLY; do source "$f"; done
    set -eo pipefail
    echo "без оверлея: ros2 pkg prefix mavros = $(ros2 pkg prefix mavros)"
    EX="$(ros2 pkg prefix mavros_extras)/lib/libmavros_extras_plugins.so"
    ldd -r "$EX" 2>&1 | grep -E "libmavros.so =>" || true
    ldd -r "$EX" 2>&1 | grep "undefined symbol" | awk "{print \$3}" | LC_ALL=C sort -u' > "$TA.log"
  grep -v '^без оверлея\|libmavros.so =>' "$TA.log" > "$TA" || true
  grep '^без оверлея\|libmavros.so =>' "$TA.log"
  echo "extras без оверлея (как сегодня): неразрешённых символов $(wc -l < "$TA"); с оверлеем: $(wc -l < "$TO")"
  c++filt < "$TA" | sed 's/^/  сегодня: /'
  NEWU=$(LC_ALL=C comm -13 "$TA" "$TO")
  if [ -n "$NEWU" ]; then printf '%s\n' "$NEWU" | c++filt; echo "СТОП: с оверлеем у extras появились новые неразрешённые символы"; exit 1; fi
  echo "НОВЫХ НЕРАЗРЕШЁННЫХ СИМВОЛОВ НЕТ"
  # отпечатки
  ( cd "$I" && find . -type f ! -path '*/__pycache__/*' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum ) > "$F"
  grep -E '\.so$|/mavros_node$' "$F" | tee "$SO"
  [ "$(wc -l < "$SO")" -ge 3 ]
  sha256sum "$F" "$SO"
  echo "MSF_SHA256=$(sha256sum < "$F" | cut -d' ' -f1)"                  # набор сессии: передать в m5 как RC3M_MSF_SHA256
  echo "ПРОВЕРКА СБОРКИ MAVROS ГОТОВО: $(wc -l < "$F") файлов в $F" )
RC=$?
if [ "$RC" != 0 ]; then echo "=== СТОП: M3 не прошёл (код $RC). Оверлей не подключать. Прислать Claude этот вывод."; exit 1; fi
echo RC3M_M3_OK
