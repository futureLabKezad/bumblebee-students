#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 12.11.2026, набор r6). Проверка на Pi до и после установки (и отката) варианта образа «r2j + камера полных строк» (image_r2j_cam).
# Ничего не пишет, не копирует, службы не трогает.
# Режим (аргумент 1):
#   install    : перед установкой. Служба bumblebee НЕ active (останавливает владелец сам); в ~/start_bumblebee.sh есть строка оверлея r2j;
#                ros2 pkg prefix bumblebee (с теми же строками source, что у запуска) = /home/lb/bench_ws/r2j/install/bumblebee (то, что реально исполняется);
#                4 файла на местах = r2j (camera_fix.py 4a15d699 и bumblebee.launch.py 62be01db в src и в install оверлея). Иначе СТОП: ставить нельзя
#                (иначе правка легла бы не туда, где исполняется, и молча ничего не изменила бы: урок Wi-Fi).
#   installed  : сразу после установки. Те же 4 файла = вариант (dabd5076 и 5f0954d8). Это «файлы легли»; что стек их исполняет, проверяет 24a после запуска службы.
#   rollback   : перед откатом. Служба НЕ active; оверлей подключён; 4 файла = вариант; и список резервных копий в папке резерва ВАРИАНТА с sha256 их installed_manifest.tsv
#                (папку BROOT = <BACKUP_ROOT>/r2j_cam и sha256 очищенного манифеста варианта ПК подставляет вместо строки #@@CPARGS@@) — ПК выберет самую новую полную
#                копию ИМЕННО этой установки. Резерв варианта лежит отдельно от резервов образа r2j (правка 2 проверки RV, 12.11): 06 r5 без метки его не видит.
#   rolledback : сразу после отката. 4 файла = r2j.
# Список файлов (путь от HOME, sha r2j, sha варианта) подставляет ПК вместо строки #@@CAMVAR@@.
# stdout: CP_* строки, CP_RESULT OK | STOP <причины>, последняя строка BB_R6CP_DONE.
# Только для тестов на ПК: BB_TEST_NOROS (тогда префикс берётся из BB_TEST_PREFIX).
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6CP_MARK
export LC_ALL=C
MODE="${1:-}"
case "$MODE" in install|installed|rollback|rolledback) ;; *) echo "CP_RESULT STOP режим '$MODE'"; echo "BB_R6CP_DONE"; exit 0;; esac
VAR='
#@@CAMVAR@@
'
# папку резерва варианта (<BACKUP_ROOT>/r2j_cam) и sha256 манифеста подставляет ПК (в аргументах ssh набора разрешены только короткие простые слова)
ARGS='
#@@CPARGS@@
'
BROOT=$(printf '%s\n' "$ARGS" | sed -n 's/^BROOT=//p' | head -1)
MSHA=$(printf '%s\n' "$ARGS" | sed -n 's/^MSHA=//p' | head -1)
OVL_LINE="source /home/lb/bench_ws/r2j/install/local_setup.bash"
WANT_PFX="$HOME/bench_ws/r2j/install/bumblebee"
why=""
svc=$(systemctl is-active bumblebee 2>/dev/null | head -1)
echo "CP_SERVICE bumblebee ${svc:-unknown}"
case "$MODE" in install|rollback) [ "$svc" = active ] && why="$why служба_bumblebee_active(остановите_сами:sudo_systemctl_stop_bumblebee)";; esac
if [ -f "$HOME/start_bumblebee.sh" ] && grep -qxF "$OVL_LINE" "$HOME/start_bumblebee.sh"; then echo "CP_OVERLAY_LINE yes"; else echo "CP_OVERLAY_LINE no"; why="$why в_start_bumblebee.sh_нет_строки_оверлея_r2j(сначала_13,15,16)"; fi
if [ -n "${BB_TEST_NOROS:-}" ]; then PFX="${BB_TEST_PREFIX:-}"; else
  PFX=$( source /etc/profile.d/bumblebee-ros.sh < /dev/null > /dev/null 2>&1
         source /opt/ros/jazzy/setup.bash < /dev/null > /dev/null 2>&1
         while IFS= read -r l; do
           case "$l" in
             "source /home/lb/ros2_ws/install/setup.bash"|"source /home/lb/bench_ws/mavros/install/local_setup.bash"|"source /home/lb/bench_ws/r2j/install/local_setup.bash"|"source /home/lb/bench_ws/port/install/local_setup.bash")
               f="$HOME/${l#source /home/lb/}"; [ -f "$f" ] && source "$f" < /dev/null > /dev/null 2>&1 ;;
           esac
         done < "$HOME/start_bumblebee.sh"
         timeout 30 ros2 pkg prefix bumblebee < /dev/null 2>/dev/null | head -1 )
fi
PFXR=$(readlink -f "$PFX" 2>/dev/null); WANTR=$(readlink -f "$WANT_PFX" 2>/dev/null)
echo "CP_PREFIX ${PFX:-none}"
[ -n "$PFX" ] && [ "$PFXR" = "$WANTR" ] || why="$why исполняется_не_оверлей_r2j(prefix=${PFX:-none})"
n=0; okr=0; okc=0
while read -r path sr sc; do
  case "$path" in ''|\#*) continue;; esac
  n=$((n+1))
  f="$HOME/$path"
  if [ -L "$f" ]; then echo "CP_FILE $path SYMLINK"; why="$why символьная_ссылка:$path"; continue; fi
  if [ ! -f "$f" ]; then echo "CP_FILE $path MISSING"; why="$why нет_файла:$path"; continue; fi
  got=$(sha256sum "$f" 2>/dev/null | cut -c1-64)
  k=OTHER; [ "$got" = "$sr" ] && { k=R2J; okr=$((okr+1)); }; [ "$got" = "$sc" ] && { k=CAM; okc=$((okc+1)); }
  echo "CP_FILE $path $k sha=$got"
done <<< "$VAR"
echo "CP_COUNT files=$n r2j=$okr cam=$okc"
[ "$n" = 4 ] || why="$why в_списке_не_4_файла($n)"
case "$MODE" in
  install|rolledback) [ "$okr" = "$n" ] || why="$why файлы_не_равны_r2j(r2j=${okr}_из_${n})" ;;
  installed|rollback) [ "$okc" = "$n" ] || why="$why файлы_не_равны_варианту(cam=${okc}_из_${n})" ;;
esac
if [ "$MODE" = rollback ]; then
  case "$BROOT" in /*) ;; *) why="$why BACKUP_ROOT_не_абсолютный_путь";; esac
  case "$MSHA" in [0-9a-f]*) [ "${#MSHA}" = 64 ] || why="$why нет_sha_манифеста";; *) why="$why нет_sha_манифеста";; esac
  if [ -d "$BROOT" ]; then
    for b in $(ls -1 "$BROOT" 2>/dev/null | grep -E '^[0-9]{8}_[0-9]{6}$' | sort); do
      ms=$(sha256sum "$BROOT/$b/installed_manifest.tsv" 2>/dev/null | cut -c1-64)
      rb=0; [ -e "$BROOT/$b/ROLLED_BACK" ] && rb=1
      cpl=1; { [ -d "$BROOT/$b/files" ] && [ -f "$BROOT/$b/files.sha256" ] && [ ! -e "$BROOT/$b/BACKUP_FAILED" ]; } || cpl=0
      m=0; [ "$ms" = "$MSHA" ] && m=1
      echo "CP_BACKUP $b match=$m rolled_back=$rb complete=$cpl"
    done
  else
    why="$why нет_папки_BACKUP_ROOT"
  fi
fi
if [ -z "$why" ]; then echo "CP_RESULT OK"; else echo "CP_RESULT STOP$why"; fi
echo "BB_R6CP_DONE"
