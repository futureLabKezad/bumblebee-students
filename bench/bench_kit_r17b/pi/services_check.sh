#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 11.11.2026, набор r3; поручение чата 1 T47). Первый запуск ДО установки образа (для сравнения), второй после. Состояние трёх служб после установки образа: wifi-manager, notify-manager, led-default.
# Основание: эти службы запускают скрипты из /home/lb/ros2_ws/src/bumblebee/scripts, а они делают sys.path.insert на /home/lb/ros2_ws/src/bumblebee/examples и import drone;
# после установки образа (05) со следующего включения они работают на drone.py r2j (_ПОПРАВКА_20261111_drone_py.md).
# Что делает (только чтение, без sudo, ничего не останавливает, не запускает и не перезапускает, файлов на Pi не создаёт):
#   systemctl is-active <служба>; systemctl show <служба> -p NRestarts (сколько раз systemd сам перезапускал: падения); journalctl -u <служба> --since "-10 min" --no-pager (хвост 15 строк);
#   число «ошибочных» строк в этом окне: Traceback, ImportError, ModuleNotFoundError, AttributeError, «Failed with result», «code=exited, status=1..255», «code=dumped».
# Если журнал прочитать нельзя (нет прав у пользователя lb): SVC_JOURNAL access=denied (это СТОП: проверить нечем; sudo не используется, правило 7).
# stdout: SVC <служба> <состояние>, SVC_RESTARTS <служба> <число|unknown>, SVC_JOURNAL <служба> lines=<n> access=ok|denied, SVC_ERRORS <служба> <n>, JT <служба> | <строка журнала>, BB_SVC_RESULT active=<n> errors=<n> restarts=<n> denied=<n>, BB_SVC_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_SVC_MARK
ERRPAT='Traceback|ImportError|ModuleNotFoundError|AttributeError|Failed with result|code=exited, status=[1-9]|code=dumped'
act=0; errs=0; rst=0; den=0
for s in wifi-manager notify-manager led-default; do
  st=$(systemctl is-active "$s" 2>&1 | head -1)
  [ -n "$st" ] || st=unknown
  echo "SVC $s $st"
  [ "$st" = "active" ] && act=$((act+1))
  nr=$(systemctl show "$s" -p NRestarts --value 2>/dev/null | head -1)
  case "$nr" in ''|*[!0-9]*) echo "SVC_RESTARTS $s unknown";; *) echo "SVC_RESTARTS $s $nr"; rst=$((rst+nr));; esac
  j=$(journalctl -u "$s" --since "-10 min" --no-pager 2>&1)
  access=ok
  case "$j" in *"insufficient permissions"*|*"not seeing messages from other users"*) access=denied; den=$((den+1));; esac
  n=$(printf '%s\n' "$j" | grep -c .)
  echo "SVC_JOURNAL $s lines=$n access=$access"
  e=$(printf '%s\n' "$j" | grep -c -E "$ERRPAT")
  echo "SVC_ERRORS $s $e"
  errs=$((errs+e))
  printf '%s\n' "$j" | tail -n 15 | while IFS= read -r l; do echo "JT $s | $l"; done
done
echo "BB_SVC_RESULT active=$act errors=$errs restarts=$rst denied=$den"
echo "BB_SVC_DONE"
