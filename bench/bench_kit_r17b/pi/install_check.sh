#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2; по решениям чата 1 в 19:19 и 19:45). Что реально исполняется на Pi (install пакета bumblebee) и совпадает ли оно с образом r2j.
# Какой install исполняется, говорит `ros2 pkg prefix bumblebee` (после source профиля, как в start_bumblebee.sh); узлы лежат в <префикс>/lib/bumblebee/.
# Разделение по решению чата 1 (19:45):
#  - Python-узлы (*.py) от архитектуры не зависят: их sha256 должны совпасть со списком r2j (INSTALL_FILE ... OK|DIFF|MISSING);
#  - C++: сверяются ИСХОДНИКИ и файлы сборки пакета в $HOME/ros2_ws/src/bumblebee (CPP_SRC ... OK|DIFF|MISSING, список CPP_SOURCES_r2j.tsv);
#    бинарники НЕ сверяются по sha256 (в install r2j они собраны для x86, у Pi свои): печатаются sha256 и время файла (INSTALL_BIN), а флаг STALE ставится, если бинарник СТАРШЕ самого нового
#    из исходников, которые r2j меняет против дрона (флаг R в списке): значит, пакет после установки не пересобран и исполняется старый C++.
# Ничего не пишет на дрон, файлов на Pi не создаёт. Четыре списка подставляет ПК (run_install_check.ps1) вместо строк #@@LIST@@, #@@CPP@@, #@@BINS@@, #@@RT@@ в памяти. #@@RT@@ (21:50, S2): launch-файлы из <префикс>/share/bumblebee/launch и fcu_detect.py (исправление порта) по sha256, вывод RT_FILE и BB_RTPY ok= diff= missing=.
# stdout: INSTALL_PREFIX, INSTALL_FILE, CPP_SRC, INSTALL_BIN, OTHER_COPY (справочно), BB_INSTALL_CHECK ok= diff= missing= noprefix= cpp_ok= cpp_diff= cpp_missing= bin_ok= bin_missing= stale=, BB_INSTALL_CHECK_DONE.
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
# BB_INSTALL_MARK
LIST='
#@@LIST@@
'
CPP='
#@@CPP@@
'
BINS='
#@@BINS@@
'
RT='
#@@RT@@
'
echo "INSTALL_ARCH $(uname -m)"
PFX=$(timeout 30 ros2 pkg prefix bumblebee < /dev/null 2>/dev/null | head -1)
echo "INSTALL_PREFIX ${PFX:-none}"
if [ -z "$PFX" ] || [ ! -d "$PFX/lib/bumblebee" ]; then
  echo "BB_INSTALL_CHECK ok=0 diff=0 missing=0 noprefix=1 cpp_ok=0 cpp_diff=0 cpp_missing=0 bin_ok=0 bin_missing=0 stale=0"
  echo "BB_INSTALL_CHECK_DONE"
  exit 0
fi
D="$PFX/lib/bumblebee"
# r11 (16.11): у двух примеров полёта want = «sha_r2j,sha_real» (image_r2j\EXAMPLES_REAL_20261116.tsv, карта real): совпадение с любым - OK, второе помечается REAL_MAP; у остальных строк want один, как в r9
# r13 (17.11): определение shamatch поднято сюда без изменений - оно нужно уже циклу python-узлов (LIST)
shamatch() { [ -n "$1" ] || return 1; case ",$2," in *",$1,"*) return 0;; esac; return 1; }
# r15 (18.11, перенесено в r16): метка по СОВПАВШЕМУ sha. shalab <got> <sha1,sha2,...> <метка1,метка2,...> печатает метку того места, где got (1-е место - r2j, его метка пустая); не совпало - код 1
shalab() { local i=1 s; for s in $(printf '%s' "$2" | tr ',' ' '); do if [ -n "$1" ] && [ "$s" = "$1" ]; then printf '%s' "$3" | cut -d, -f"$i"; return 0; fi; i=$((i+1)); done; return 1; }
ok=0; diff=0; miss=0
while read -r want name; do
  case "$want" in ''|\#*) continue;; esac
  if [ ! -e "$D/$name" ]; then echo "INSTALL_FILE $name MISSING want=$want"; miss=$((miss+1)); continue; fi
  got=$(sha256sum "$D/$name" 2>/dev/null | cut -c1-64)
  # r13 (17.11): у aruco_detect.py want = «sha_r2j,sha_jd2» (image_r2j\POSEFIX_JD2_20261117.tsv, детектор меток варианта jd2): совпадение с любым - OK, второе помечается POSEFIX_JD2
  # r14 (17.11): у camera_fix.py want = «sha_r2j,sha_r2m_cam» (image_r2j\R2M_CAM_20261117.tsv): второе помечается R2M_CAM. Метка - по ИМЕНИ узла; у всех других узлов принимается только первое sha (r2j)
  # r17 (19.11; в r16 был В1): у aruco_detect.py want = «r2j,jd2,v11», у vpe_fix.py «r2j,v1» (image_r2j\POSEFIX_V11_20261119.tsv; vpe В1.1 = vpe В1). Берётся не больше 3 sha у aruco, 2 у vpe_fix и camera_fix, 1 у остальных; метка - по СОВПАВШЕМУ sha:
  # r2j - без метки, jd2 - POSEFIX_JD2, В1.1 - POSEFIX_V11 (у обоих узлов), r2m_cam - R2M_CAM
  case "$name" in aruco_detect.py) w=$(printf '%s' "$want" | cut -d, -f1-3); labs=",POSEFIX_JD2,POSEFIX_V11";; vpe_fix.py) w=$(printf '%s' "$want" | cut -d, -f1-2); labs=",POSEFIX_V11";; camera_fix.py) w=$(printf '%s' "$want" | cut -d, -f1-2); labs=",R2M_CAM";; *) w="${want%%,*}"; labs="";; esac
  if lab=$(shalab "$got" "$w" "$labs"); then ok=$((ok+1)); vmark=""; [ -n "$lab" ] && vmark=" $lab"; echo "INSTALL_FILE $name OK$vmark"; else diff=$((diff+1)); echo "INSTALL_FILE $name DIFF got=$got want=$want"; fi
done <<< "$LIST"
cok=0; cdiff=0; cmiss=0; newest=0
while read -r want path flag; do
  case "$want" in ''|\#*) continue;; esac
  f="$HOME/$path"
  if [ ! -f "$f" ]; then echo "CPP_SRC $path MISSING want=$want"; cmiss=$((cmiss+1)); continue; fi
  got=$(sha256sum "$f" 2>/dev/null | cut -c1-64)
  if shamatch "$got" "$want"; then cok=$((cok+1)); vmark=""; [ "$got" = "${want%%,*}" ] || vmark=" REAL_MAP"; echo "CPP_SRC $path OK $flag$vmark"; else cdiff=$((cdiff+1)); echo "CPP_SRC $path DIFF got=$got want=$want"; fi
  if [ "$flag" = "R" ]; then m=$(stat -c %Y "$f" 2>/dev/null || echo 0); [ "$m" -gt "$newest" ] && newest=$m; fi
done <<< "$CPP"
bok=0; bmiss=0; stale=0
while read -r name; do
  case "$name" in ''|\#*) continue;; esac
  if [ ! -f "$D/$name" ]; then echo "INSTALL_BIN $name MISSING"; bmiss=$((bmiss+1)); continue; fi
  bm=$(stat -c %Y "$D/$name" 2>/dev/null || echo 0)
  st=""
  if [ "$bm" -lt "$newest" ]; then st=" STALE (бинарник старше самого нового изменённого исходника: пакет не пересобран)"; stale=$((stale+1)); fi
  bok=$((bok+1)); echo "INSTALL_BIN $name sha=$(sha256sum "$D/$name" 2>/dev/null | cut -c1-64) mtime=$bm newest_changed_src=$newest$st"
done <<< "$BINS"
# Решение чата 1 21:50 (S2): launch-файлы, которые берёт «ros2 launch bumblebee bumblebee.launch.py» (<префикс>/share/bumblebee/launch/...), и fcu_detect.py, который start_bumblebee.sh запускает по полному пути в ros2_ws/src (исправление порта fcu_detect_fix_01): sha256 должны совпасть с r2j
rtok=0; rtbad=0; rtmiss=0
while read -r want kind path; do
  case "$want" in ''|\#*) continue;; esac
  case "$kind" in LAUNCH) f="$PFX/share/bumblebee/$path";; FCU) f="$HOME/$path";; *) continue;; esac
  if [ ! -f "$f" ]; then echo "RT_FILE $kind $path MISSING want=$want"; rtmiss=$((rtmiss+1)); continue; fi
  got=$(sha256sum "$f" 2>/dev/null | cut -c1-64)
  # r14 (17.11): у LAUNCH launch/bumblebee.launch.py want = «sha_r2j,sha_r2m_cam» (image_r2j\R2M_CAM_20261117.tsv): второе помечается R2M_CAM. Метка - по ПУТИ; у всех других строк RT - только первое sha (r2j), как в r13
  case "$kind $path" in "LAUNCH launch/bumblebee.launch.py") w="$want"; lab=" R2M_CAM";; *) w="${want%%,*}"; lab="";; esac
  if shamatch "$got" "$w"; then rtok=$((rtok+1)); vmark=""; [ "$got" = "${w%%,*}" ] || vmark="$lab"; echo "RT_FILE $kind $path OK$vmark"; else rtbad=$((rtbad+1)); echo "RT_FILE $kind $path DIFF got=$got want=$want"; fi
done <<< "$RT"
echo "BB_RTPY ok=$rtok diff=$rtbad missing=$rtmiss"
find "$HOME" -maxdepth 9 -path '*install*' \( -name camera_fix.py -o -name vpe_fix.py -o -name aruco_detect.py \) 2>/dev/null | head -12 | while IFS= read -r f; do
  case "$f" in "$D"/*) continue;; esac
  echo "OTHER_COPY $(sha256sum "$f" 2>/dev/null | cut -c1-64) $f"
done
echo "BB_INSTALL_CHECK ok=$ok diff=$diff missing=$miss noprefix=0 cpp_ok=$cok cpp_diff=$cdiff cpp_missing=$cmiss bin_ok=$bok bin_missing=$bmiss stale=$stale"
echo "BB_INSTALL_CHECK_DONE"
