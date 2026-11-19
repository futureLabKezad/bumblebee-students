#!/bin/bash
# МЕНЯЕТ ДРОН (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58; ТОЛЬКО ПОСЛЕ «ДА» ВЛАДЕЛЬЦА). Подключает собранный оверлей одной строкой в ~/start_bumblebee.sh (как шаги У2 и УМ набора s0b / rc3: те же проверки, копия до замены, .bbnew, ничего не перезаписывается без копии).
# Аргумент 1: mavros или bumblebee. Строки (порядок как у УМ и У2: ros2_ws, затем MAVROS, затем bumblebee; оверлей, подключённый позже, главнее):
#   source /home/lb/ros2_ws/install/setup.bash
#   source /home/lb/bench_ws/mavros/install/local_setup.bash     <- target mavros (сразу после строки ros2_ws)
#   source /home/lb/bench_ws/r2j/install/local_setup.bash        <- target bumblebee (после строки MAVROS, если она есть, иначе после ros2_ws)
# Условия (иначе STOP, ничего не изменено): служба bumblebee не активна; оверлей собран и его файлы РОВНО такие, как в отпечатках, снятых шагом 15 (ПК подставляет вместо #@@FPCFG@@ две строки FPHASH=<сумма списка «sha256  путь»> и FPCOUNT=<число файлов>: сам список слишком длинный для командной строки ssh; лишних файлов нет);
# в start_bumblebee.sh ровно одна строка ros2_ws и ещё нет строки этого оверлея; нет .bbnew; папка копии ещё не существует. Копии: ~/bench_ws/_bk_start_bumblebee_<метка>/start_bumblebee.sh.before и .after.
# Служба и перезагрузка: после подключения владелец сам запускает службу (пароль). Откат: 17_otkljuchit_overlay.cmd (возвращает файл из .before, оверлей на диске остаётся). Последняя строка при успехе: BB_CONN_DONE <target> <папка копии>.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
T="${1:-}"
case "$T" in mavros|bumblebee) ;; *) echo "STOP: bad target '$T' (mavros|bumblebee)" >&2; exit 1;; esac
# BB_CONN_MARK
FPCFG='
#@@FPCFG@@
'
FPHASH=$(printf '%s\n' "$FPCFG" | sed -n 's/^FPHASH=//p' | head -1)
FPCOUNT=$(printf '%s\n' "$FPCFG" | sed -n 's/^FPCOUNT=//p' | head -1)
stop() { echo "BB_CONN_STOP $*"; exit 1; }
S="$HOME/start_bumblebee.sh"
LWS='source /home/lb/ros2_ws/install/setup.bash'
LM='source /home/lb/bench_ws/mavros/install/local_setup.bash'
LB='source /home/lb/bench_ws/r2j/install/local_setup.bash'
if [ "$T" = mavros ]; then ROOT="$HOME/bench_ws/mavros"; NEW="$LM"; ANCHOR="$LWS"; KEY='bench_ws/mavros'; else ROOT="$HOME/bench_ws/r2j"; NEW="$LB"; KEY='bench_ws/r2j'; fi
INST="$ROOT/install"
if systemctl is-active --quiet bumblebee; then stop "служба bumblebee запущена: остановите сами (sudo systemctl stop bumblebee)"; fi
[ -f "$S" ] || stop "нет $S"
[ -d "$INST" ] || stop "нет $INST (оверлей не собран)"
[ "$(grep -c -x "$LWS" "$S")" = 1 ] || stop "в start_bumblebee.sh не ровно одна строка ros2_ws"
[ "$(grep -c "$KEY" "$S")" = 0 ] || stop "в start_bumblebee.sh уже есть строка $KEY"
if [ "$T" = bumblebee ]; then if [ "$(grep -c -x "$LM" "$S")" = 1 ]; then ANCHOR="$LM"; else ANCHOR="$LWS"; fi; fi
[ ! -e "$S.bbnew" ] || stop "остался $S.bbnew"
case "$FPHASH" in *[!0-9a-f]*|'') stop "в скрипте нет суммы списка отпечатков (FPHASH)";; esac
[ "${#FPHASH}" = 64 ] || stop "сумма списка отпечатков не 64 знака"
case "$FPCOUNT" in *[!0-9]*|'') stop "в скрипте нет числа файлов отпечатков (FPCOUNT)";; esac
[ "$FPCOUNT" -gt 0 ] || stop "пустой список отпечатков"
nfiles=$(find "$INST" -type f ! -path '*/__pycache__/*' | wc -l)
[ "$nfiles" = "$FPCOUNT" ] || stop "в оверлее $nfiles файлов, в отпечатках $FPCOUNT (лишние или пропавшие файлы)"
# Вместо списка в 500 строк (он не помещался в командную строку ssh) ПК шлёт сумму списка «sha256  путь» (пути от install, сортировка LC_ALL=C, каждая строка с \n).
# Здесь считается то же по файлам на Pi; при несовпадении выводятся строки FPGOT (то, что на Pi), ПК сам называет отличающиеся файлы.
FPGOT=$(cd "$INST" && find . -type f ! -path '*/__pycache__/*' | sed 's|^\./||' | LC_ALL=C sort | while IFS= read -r f; do echo "$(sha256sum -- "$f" | cut -c1-64)  $f"; done)
GOTHASH=$(printf '%s\n' "$FPGOT" | sha256sum | cut -c1-64)
if [ "$GOTHASH" != "$FPHASH" ]; then printf '%s\n' "$FPGOT" | sed 's/^/FPGOT /'; stop "файлы оверлея не равны отпечаткам (сумма списка $GOTHASH, ждали $FPHASH): отличия назовёт ПК"; fi
STAMP=$(date +%Y%m%d_%H%M%S)
BK="$HOME/bench_ws/_bk_start_bumblebee_$STAMP"
[ ! -e "$BK" ] || stop "$BK уже есть"
mkdir -p "$BK" || stop "не создать $BK"
cp -p "$S" "$BK/start_bumblebee.sh.before" || stop "не сохранить копию до замены"
awk -v a="$ANCHOR" -v n="$NEW" '{ print } $0 == a { print n }' "$S" > "$S.bbnew" || stop "не собрать новый файл"
diff "$S" "$S.bbnew" > "$BK/diff.txt"
[ "$(grep -c '^[<>]' "$BK/diff.txt")" = 1 ] || { mv "$S.bbnew" "$BK/rejected.bbnew"; stop "разница не из одной строки (файл не заменён)"; }
grep -qx "> $NEW" "$BK/diff.txt" || { mv "$S.bbnew" "$BK/rejected.bbnew"; stop "добавлена не та строка (файл не заменён)"; }
chmod 0755 "$S.bbnew"
cp -p "$S.bbnew" "$BK/start_bumblebee.sh.after" || stop "не сохранить копию после замены"
mv -f "$S.bbnew" "$S" || stop "не заменить файл"
cmp -s "$S" "$BK/start_bumblebee.sh.after" || stop "файл после замены не равен копии"
echo "BB_CONN_DONE $T $BK"
