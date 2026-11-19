#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58). Отпечатки собранного оверлея на Pi (аналог шага m3): sha256 всех файлов install, список исполняемых, и проверка «бинарники не старше исходников».
# Ничего не пишет на дрон, файлов на Pi не создаёт: отпечатки записывает ПК (run_fingerprint.ps1) в out\fingerprint_*.txt. Вызывается после КАЖДОЙ сборки: для оверлея bumblebee (~/bench_ws/r2j) и для оверлея MAVROS (~/bench_ws/mavros).
# Аргумент 1: bumblebee или mavros. Списки подставляет ПК вместо строк #@@LIST@@ (для bumblebee: python-узлы «sha256  имя» r2j), #@@CPP@@ (для bumblebee: C++ исходники r2j с флагом R; для mavros: 5 исходников bp02 «sha256  путь  R»), #@@RT@@ (для bumblebee: launch-файлы и fcu_detect.py r2j «sha256  вид  путь»; для mavros пусто).
# stdout: FP_TARGET, FP_ROOT, FP_FILE <sha256> <путь относительно install> (все файлы, кроме __pycache__), FP_EXEC <имя> (файлы lib/<пакет>), PY_NODE <имя> OK|DIFF|MISSING (bumblebee), SRC <путь> OK|DIFF|MISSING,
# RT_FILE <LAUNCH|FCU> <путь> OK|DIFF|MISSING, BB_FP_RT ok= diff= missing= (S2, 21:50), BIN <имя> sha=... mtime=... [STALE], BB_FP_RESULT files= py_ok= py_bad= src_ok= src_bad= bin= stale=, BB_FP_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
T="${1:-}"
case "$T" in bumblebee|mavros) ;; *) echo "STOP: bad target '$T' (bumblebee|mavros)" >&2; exit 1;; esac
# BB_FP_MARK
LIST='
#@@LIST@@
'
CPP='
#@@CPP@@
'
RT='
#@@RT@@
'
if [ "$T" = bumblebee ]; then
  ROOT="$HOME/bench_ws/r2j"; INST="$ROOT/install"; SRCBASE="$ROOT/src"; BIND="$INST/bumblebee/lib/bumblebee"
else
  ROOT="$HOME/bench_ws/mavros"; INST="$ROOT/install"; SRCBASE="$ROOT/src/mavros-source"; BIND="$INST/mavros/lib"
fi
echo "FP_TARGET $T"
echo "FP_ROOT $ROOT"
if [ ! -d "$INST" ]; then
  echo "BB_FP_RESULT files=0 py_ok=0 py_bad=0 src_ok=0 src_bad=0 bin=0 stale=0 noinstall=1"
  echo "BB_FP_DONE"
  exit 0
fi
nf=0
while IFS= read -r f; do
  echo "FP_FILE $(sha256sum "$f" 2>/dev/null | cut -c1-64) ${f#$INST/}"
  nf=$((nf+1))
done < <(find "$INST" -type f ! -path '*/__pycache__/*' 2>/dev/null | LC_ALL=C sort)
ls "$BIND" 2>/dev/null | while IFS= read -r n; do echo "FP_EXEC $n"; done
# r11 (16.11): у двух примеров полёта want = «sha_r2j,sha_real» (image_r2j\EXAMPLES_REAL_20261116.tsv, карта real): совпадение с любым - OK, второе помечается REAL_MAP; у остальных строк want один, как в r9
# r13 (17.11): определение shamatch поднято сюда без изменений - оно нужно уже циклу python-узлов (LIST)
shamatch() { [ -n "$1" ] || return 1; case ",$2," in *",$1,"*) return 0;; esac; return 1; }
# r15 (18.11, перенесено в r16): метка по СОВПАВШЕМУ sha. shalab <got> <sha1,sha2,...> <метка1,метка2,...> печатает метку того места, где got (1-е место - r2j, его метка пустая); не совпало - код 1
shalab() { local i=1 s; for s in $(printf '%s' "$2" | tr ',' ' '); do if [ -n "$1" ] && [ "$s" = "$1" ]; then printf '%s' "$3" | cut -d, -f"$i"; return 0; fi; i=$((i+1)); done; return 1; }
pok=0; pbad=0
if [ "$T" = bumblebee ]; then
  while read -r want name; do
    case "$want" in ''|\#*) continue;; esac
    if [ ! -f "$BIND/$name" ]; then echo "PY_NODE $name MISSING"; pbad=$((pbad+1)); continue; fi
    got=$(sha256sum "$BIND/$name" 2>/dev/null | cut -c1-64)
    # r13 (17.11): у aruco_detect.py want = «sha_r2j,sha_jd2» (image_r2j\POSEFIX_JD2_20261117.tsv, детектор меток варианта jd2): совпадение с любым - OK, второе помечается POSEFIX_JD2
    # r14 (17.11): у camera_fix.py want = «sha_r2j,sha_r2m_cam» (image_r2j\R2M_CAM_20261117.tsv): второе помечается R2M_CAM. Метка - по ИМЕНИ узла; у всех других узлов принимается только первое sha (r2j)
    # r17 (19.11; в r16 был В1): у aruco_detect.py want = «r2j,jd2,v11», у vpe_fix.py «r2j,v1» (image_r2j\POSEFIX_V11_20261119.tsv; vpe В1.1 = vpe В1). Берётся не больше 3 sha у aruco, 2 у vpe_fix и camera_fix, 1 у остальных; метка - по СОВПАВШЕМУ sha:
    # r2j - без метки, jd2 - POSEFIX_JD2, В1.1 - POSEFIX_V11 (у обоих узлов), r2m_cam - R2M_CAM
    case "$name" in aruco_detect.py) w=$(printf '%s' "$want" | cut -d, -f1-3); labs=",POSEFIX_JD2,POSEFIX_V11";; vpe_fix.py) w=$(printf '%s' "$want" | cut -d, -f1-2); labs=",POSEFIX_V11";; camera_fix.py) w=$(printf '%s' "$want" | cut -d, -f1-2); labs=",R2M_CAM";; *) w="${want%%,*}"; labs="";; esac
    if lab=$(shalab "$got" "$w" "$labs"); then pok=$((pok+1)); vmark=""; [ -n "$lab" ] && vmark=" $lab"; echo "PY_NODE $name OK$vmark"; else pbad=$((pbad+1)); echo "PY_NODE $name DIFF got=$got want=$want"; fi
  done <<< "$LIST"
fi
sok=0; sbad=0; newest=0
while read -r want path flag; do
  case "$want" in ''|\#*) continue;; esac
  if [ "$T" = bumblebee ]; then rel="${path#ros2_ws/src/}"; else rel="$path"; fi
  f="$SRCBASE/$rel"
  if [ ! -f "$f" ]; then echo "SRC $rel MISSING"; sbad=$((sbad+1)); continue; fi
  got=$(sha256sum "$f" 2>/dev/null | cut -c1-64)
  if shamatch "$got" "$want"; then sok=$((sok+1)); vmark=""; [ "$got" = "${want%%,*}" ] || vmark=" REAL_MAP"; echo "SRC $rel OK $flag$vmark"; else sbad=$((sbad+1)); echo "SRC $rel DIFF got=$got want=$want"; fi
  if [ "$flag" = "R" ]; then m=$(stat -c %Y "$f" 2>/dev/null || echo 0); [ "$m" -gt "$newest" ] && newest=$m; fi
done <<< "$CPP"
nb=0; stale=0
if [ "$T" = bumblebee ]; then BINS=$(for n in simple_offboard camera_markers optical_flow_node rc shell vpe_publisher; do [ -f "$BIND/$n" ] && echo "$BIND/$n"; done)
else BINS=$(find "$INST/mavros" \( -name libmavros.so -o -name libmavros_plugins.so -o -name mavros_node \) -type f 2>/dev/null | LC_ALL=C sort); fi
while IFS= read -r b; do
  [ -n "$b" ] || continue
  bm=$(stat -c %Y "$b" 2>/dev/null || echo 0); st=""
  if [ "$bm" -lt "$newest" ]; then st=" STALE"; stale=$((stale+1)); fi
  nb=$((nb+1)); echo "BIN ${b#$INST/} sha=$(sha256sum "$b" 2>/dev/null | cut -c1-64) mtime=$bm newest_source=$newest$st"
done <<< "$BINS"
# Решение чата 1 21:50 (S2), только для bumblebee (для MAVROS список пуст): launch-файлы оверлея (<install>/bumblebee/share/bumblebee/launch, их берёт «ros2 launch», когда оверлей подключён) и fcu_detect.py по полному пути ros2_ws/src (его запускает start_bumblebee.sh; исправление порта) равны r2j по sha256
rtok=0; rtbad=0; rtmiss=0
while read -r want kind path; do
  case "$want" in ''|\#*) continue;; esac
  case "$kind" in LAUNCH) f="$INST/bumblebee/share/bumblebee/$path";; FCU) f="$HOME/$path";; *) continue;; esac
  if [ ! -f "$f" ]; then echo "RT_FILE $kind $path MISSING want=$want"; rtmiss=$((rtmiss+1)); continue; fi
  got=$(sha256sum "$f" 2>/dev/null | cut -c1-64)
  # r14 (17.11): у LAUNCH launch/bumblebee.launch.py want = «sha_r2j,sha_r2m_cam» (image_r2j\R2M_CAM_20261117.tsv): второе помечается R2M_CAM. Метка - по ПУТИ; у всех других строк RT - только первое sha (r2j), как в r13
  case "$kind $path" in "LAUNCH launch/bumblebee.launch.py") w="$want"; lab=" R2M_CAM";; *) w="${want%%,*}"; lab="";; esac
  if shamatch "$got" "$w"; then rtok=$((rtok+1)); vmark=""; [ "$got" = "${w%%,*}" ] || vmark="$lab"; echo "RT_FILE $kind $path OK$vmark"; else rtbad=$((rtbad+1)); echo "RT_FILE $kind $path DIFF got=$got want=$want"; fi
done <<< "$RT"
echo "BB_FP_RT ok=$rtok diff=$rtbad missing=$rtmiss"
echo "BB_FP_RESULT files=$nf py_ok=$pok py_bad=$pbad src_ok=$sok src_bad=$sbad bin=$nb stale=$stale noinstall=0"
echo "BB_FP_DONE"
