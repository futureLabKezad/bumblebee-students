#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2; решение чата 1 в 20:10). Гейт перед взлётом: скрипт полёта берёт drone.py оттуда, куда указывает его sys.path.insert, или из своей папки. Все эти drone.py должны быть РОВНО r2j (sha256), иначе СТОП:
# тогда исправления сторожа r2j на дроне не сработали бы (скрипт импортировал бы старый drone.py).
# Ничего не пишет на дрон, файлов на Pi не создаёт. Две строки конфигурации (SCRIPT=путь, WANT=sha256 drone.py r2j) подставляет ПК вместо #@@FGCFG@@ в памяти.
# Что проверяется: (1) каждый каталог из строк «sys.path.insert(0, '<каталог>')» в тексте скрипта: <каталог>/drone.py есть и равен WANT; (2) drone.py рядом со скриптом (папка скрипта и папка на уровень выше) равен WANT, если он там есть;
# (3) если ни одного каталога из sys.path.insert нет, drone.py в папке скрипта ОБЯЗАН быть и равен WANT (так Python найдёт его сам). Скрипт полёта и его sha256 проверяет сам 07 отдельно.
# stdout: FG_DIR <каталог> drone.py OK|DIFF|MISSING, FG_NEAR <файл> OK|DIFF, BB_FG_RESULT OK или STOP <причины>, BB_FG_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_FG_MARK
CFG='
#@@FGCFG@@
'
SCRIPT=$(printf '%s\n' "$CFG" | sed -n 's/^SCRIPT=//p' | head -1)
WANT=$(printf '%s\n' "$CFG" | sed -n 's/^WANT=//p' | head -1)
case "$SCRIPT" in /home/lb/*.py) ;; *) echo "STOP: bad SCRIPT '$SCRIPT'" >&2; exit 1;; esac
case "$WANT" in *[!0-9a-f]*|'') echo "STOP: bad WANT" >&2; exit 1;; esac
[ "${#WANT}" = 64 ] || { echo "STOP: bad WANT length" >&2; exit 1; }
fs() { case "$1" in /home/lb/*) echo "$HOME/${1#/home/lb/}";; *) echo "$1";; esac; }   # на дроне HOME=/home/lb; путь в тексте скрипта абсолютный, сопоставляем с HOME (так же проверяется в тестах)
why=""
SCRIPT_FS=$(fs "$SCRIPT")
[ -f "$SCRIPT_FS" ] || { echo "BB_FG_RESULT STOP скрипта_нет"; echo "BB_FG_DONE"; exit 0; }
ndirs=0
while IFS= read -r d; do
  [ -n "$d" ] || continue
  ndirs=$((ndirs+1))
  df=$(fs "$d")
  if [ ! -f "$df/drone.py" ]; then echo "FG_DIR $d drone.py MISSING"; why="$why нет_drone.py_в_$d"; continue; fi
  got=$(sha256sum "$df/drone.py" | cut -c1-64)
  if [ "$got" = "$WANT" ]; then echo "FG_DIR $d drone.py OK"; else echo "FG_DIR $d drone.py DIFF got=$got want=$WANT"; why="$why drone.py_в_${d}_не_r2j"; fi
done < <(grep -o "sys\.path\.insert([0-9]*, *['\"][^'\"]*['\"])" "$SCRIPT_FS" | sed "s/^sys\.path\.insert([0-9]*, *['\"]\([^'\"]*\)['\"])$/\1/")
SD=$(dirname "$SCRIPT_FS")
nnear=0
for f in "$SD/drone.py" "$SD/../drone.py"; do
  [ -f "$f" ] || continue
  nnear=$((nnear+1))
  got=$(sha256sum "$f" | cut -c1-64)
  if [ "$got" = "$WANT" ]; then echo "FG_NEAR $f OK"; else echo "FG_NEAR $f DIFF got=$got want=$WANT"; why="$why drone.py_рядом_не_r2j"; fi
done
if [ "$ndirs" = 0 ] && [ ! -f "$SD/drone.py" ]; then why="$why нет_sys.path.insert_и_нет_drone.py_в_папке_скрипта"; fi
if [ -z "$why" ]; then echo "BB_FG_RESULT OK"; else echo "BB_FG_RESULT STOP$why"; fi
echo "BB_FG_DONE"
