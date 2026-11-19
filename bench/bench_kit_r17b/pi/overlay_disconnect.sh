#!/bin/bash
# МЕНЯЕТ ДРОН (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58). Откат подключения оверлея (17_otkljuchit_overlay.cmd): возвращает ~/start_bumblebee.sh в состояние ДО последнего подключения (штатный MAVROS из apt и прежняя сборка ros2_ws снова главные).
# Берёт САМУЮ НОВУЮ папку ~/bench_ws/_bk_start_bumblebee_<метка>/ БЕЗ метки RESTORED (там start_bumblebee.sh.before и .after, их записал overlay_connect.sh) и возвращает файл из .before. Если подключали оба оверлея (сначала MAVROS, потом bumblebee), запускают дважды: первый раз снимает bumblebee, второй MAVROS (правка r2 по проверке 10.11).
# Условия (иначе STOP, ничего не изменено): служба bumblebee не активна; текущий файл РОВНО равен .after выбранной копии (после подключения его никто не менял); есть хотя бы одна копия без RESTORED. Оверлеи на диске не трогаются, копии не удаляются.
# Последняя строка при успехе: BB_DISC_DONE <папка копии>.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_DISC_MARK
stop() { echo "BB_DISC_STOP $*"; exit 1; }
S="$HOME/start_bumblebee.sh"
if systemctl is-active --quiet bumblebee; then stop "служба bumblebee запущена: остановите сами (sudo systemctl stop bumblebee)"; fi
ALLBK=$(ls -d "$HOME"/bench_ws/_bk_start_bumblebee_* 2>/dev/null | LC_ALL=C sort)
[ -n "$ALLBK" ] || stop "нет копий ~/bench_ws/_bk_start_bumblebee_*: нечего откатывать"
# самая новая копия БЕЗ метки RESTORED (так второй запуск снимает предыдущий оверлей); все копии уже откачены: STOP
BK=""
while IFS= read -r c; do [ -e "$c/RESTORED" ] || BK="$c"; done <<< "$ALLBK"
[ -n "$BK" ] || stop "все копии уже откачены (RESTORED): откатывать нечего, решает чат 1"
[ -f "$BK/start_bumblebee.sh.before" ] && [ -f "$BK/start_bumblebee.sh.after" ] || stop "в $BK нет .before или .after"
cmp -s "$S" "$BK/start_bumblebee.sh.after" || stop "start_bumblebee.sh не равен копии .after: после подключения его кто-то менял, откат не делаю"
[ ! -e "$S.bbnew" ] || stop "остался $S.bbnew"
cp -p "$BK/start_bumblebee.sh.before" "$S.bbnew" || stop "не подготовить файл"
mv -f "$S.bbnew" "$S" || stop "не заменить файл"
cmp -s "$S" "$BK/start_bumblebee.sh.before" || stop "файл после отката не равен .before"
date '+%F %T' > "$BK/RESTORED"
echo "BB_DISC_DONE $BK"
