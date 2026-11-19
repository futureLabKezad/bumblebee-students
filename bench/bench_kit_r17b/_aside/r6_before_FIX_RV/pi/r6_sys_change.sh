#!/bin/bash
# МЕНЯЕТ ДРОН (Claude, 12.11.2026, набор r6; ступень 1 разбора P1 /work/pi_load_20261112/P1). Одна системная правка за раз или её откат. ЗАГОТОВКА: Claude её не запускает.
# Запускается из 23a/23b/23c_*.cmd через ssh -tt: sudo спрашивает пароль ВЛАДЕЛЬЦА прямо в окне (вводит только владелец, правило 7).
# Аргументы: правка (fwupd | snaphold | timers) и режим (apply | rollback).
#   fwupd    : sudo systemctl mask --now fwupd-refresh.timer           откат: sudo systemctl unmask ... и start (если после unmask enabled)
#   timers   : то же для man-db.timer motd-news.timer update-notifier-download.timer update-notifier-motd.timer (одна группа)
#   snaphold : sudo snap refresh --hold (все snap, без срока)           откат: sudo snap refresh --unhold
# Порядок: снимок «до» (SYS_BEFORE) -> условия (иначе BB_SYS_STOP, ничего не изменено) -> правка -> проверка, что применилась (SYS_AFTER):
#   apply  : is-enabled = masked и is-active = inactive у каждого таймера; для snap строка «hold: forever» в snap refresh --time
#   rollback: is-enabled = enabled и is-active = active; для snap строки «hold: forever» нет.
# Почему mask --now, а не disable: disable может не сработать (таймер тянет другой юнит или пакет вернёт ссылку); mask держится, --now останавливает таймер
# сразу, а не после перезагрузки (урок Wi-Fi: правка, которая тихо не применилась). Перепроверка после перезагрузки: 20_nichego_ne_otvalilos.cmd.
# Итог: BB_SYS_DONE <правка> <режим> OK (код 0) | BB_SYS_STOP (условия, код 3, ничего не изменено) | BB_SYS_NOCHANGE (команда не выполнена, например sudo
# не принял пароль; состояние как до, код 5) | BB_SYS_FAIL (правка или проверка не прошли, код 4).
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
# BB_R6SYS_MARK
export LC_ALL=C
SYSD="${BB_TEST_ETC:-/etc}/systemd/system"   # BB_TEST_ETC только для тестов на ПК; на дроне /etc
CH="${1:-}"; MODE="${2:-}"
case "$CH" in
  fwupd) UNITS="fwupd-refresh.timer" ;;
  timers) UNITS="man-db.timer motd-news.timer update-notifier-download.timer update-notifier-motd.timer" ;;
  snaphold) UNITS="" ;;
  *) echo "BB_SYS_STOP неизвестная правка '$CH' (ничего не изменено)"; exit 3 ;;
esac
case "$MODE" in apply|rollback) ;; *) echo "BB_SYS_STOP неизвестный режим '$MODE' (ничего не изменено)"; exit 3 ;; esac
st() { echo "enabled=$(systemctl is-enabled "$1" 2>&1 | head -1) active=$(systemctl is-active "$1" 2>&1 | head -1) load=$(systemctl show -p LoadState --value "$1" 2>/dev/null | head -1)"; }
held() { snap refresh --time 2>/dev/null | grep -c -E '^hold:[[:space:]]+forever[[:space:]]*$'; }
echo "SYS_CHANGE $CH $MODE $(date '+%F %T %z') boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
if [ -n "$UNITS" ]; then
  for u in $UNITS; do echo "SYS_BEFORE $u $(st "$u")"; done
else
  command -v snap >/dev/null 2>&1 || { echo "BB_SYS_STOP нет команды snap (ничего не изменено)"; exit 3; }
  snap refresh --time 2>&1 | head -8 | while IFS= read -r l; do echo "SYS_BEFORE_SNAP $l"; done
fi
why=""
if [ -n "$UNITS" ]; then
  for u in $UNITS; do
    e=$(systemctl is-enabled "$u" 2>&1 | head -1); l=$(systemctl show -p LoadState --value "$u" 2>/dev/null | head -1)
    if [ "$MODE" = apply ]; then
      [ "$e" = enabled ] || why="$why $u:is-enabled=$e(ждали_enabled)"
      [ "$l" = loaded ] || why="$why $u:LoadState=$l(ждали_loaded)"
      # свой файл юнита в /etc помешал бы mask (и это чужая правка): решает чат 1
      [ ! -e "$SYSD/$u" ] && [ ! -L "$SYSD/$u" ] || why="$why $u:есть_/etc/systemd/system/$u"
    else
      [ "$e" = masked ] || why="$why $u:is-enabled=$e(ждали_masked)"
      [ "$(readlink "$SYSD/$u" 2>/dev/null)" = /dev/null ] || why="$why $u:маска_не_в_/etc/systemd/system"
    fi
  done
else
  h=$(held)
  if [ "$MODE" = apply ]; then [ "$h" = 0 ] || why="$why snap:уже_hold_forever"; else [ "$h" -ge 1 ] || why="$why snap:нет_hold_forever"; fi
fi
if [ -n "$why" ]; then echo "BB_SYS_STOP условия не выполнены:$why (ничего не изменено)"; exit 3; fi
echo "SYS_SUDO Сейчас sudo спросит ПАРОЛЬ. Его вводит только владелец (символы не видны), потом Enter."
# подсказка sudo кончается переводом строки: окно на ПК показывает вывод построчно, без перевода строки подсказку не было бы видно
P=$'SYS_SUDO_PROMPT пароль sudo (вводит только владелец, символы не видны), потом Enter:\n'
rc=0
case "$CH:$MODE" in
  fwupd:apply|timers:apply) sudo -p "$P" systemctl mask --now $UNITS || rc=$? ;;
  fwupd:rollback|timers:rollback)
    sudo -p "$P" systemctl unmask $UNITS || rc=$?
    if [ "$rc" = 0 ]; then
      for u in $UNITS; do
        if [ "$(systemctl is-enabled "$u" 2>&1 | head -1)" = enabled ]; then sudo -p "$P" systemctl start "$u" || rc=$?; fi
      done
    fi ;;
  snaphold:apply) sudo -p "$P" snap refresh --hold || rc=$? ;;
  snaphold:rollback) sudo -p "$P" snap refresh --unhold || rc=$? ;;
esac
echo "SYS_CMD_RC $rc"
bad=0
if [ -n "$UNITS" ]; then
  for u in $UNITS; do
    echo "SYS_AFTER $u $(st "$u")"
    e=$(systemctl is-enabled "$u" 2>&1 | head -1); a=$(systemctl is-active "$u" 2>&1 | head -1)
    if [ "$MODE" = apply ]; then { [ "$e" = masked ] && [ "$a" = inactive ]; } || bad=1
    else { [ "$e" = enabled ] && [ "$a" = active ]; } || bad=1; fi
    systemctl list-timers --all --no-pager 2>/dev/null | grep -F "$u" | while IFS= read -r l; do echo "SYS_TIMER $l"; done
  done
else
  snap refresh --time 2>&1 | head -8 | while IFS= read -r l; do echo "SYS_AFTER_SNAP $l"; done
  h=$(held)
  if [ "$MODE" = apply ]; then [ "$h" -ge 1 ] || bad=1; else [ "$h" = 0 ] || bad=1; fi
fi
if [ "$rc" = 0 ] && [ "$bad" = 0 ]; then echo "BB_SYS_DONE $CH $MODE OK"; exit 0; fi
# не прошло: изменилось ли что-нибудь? (например, sudo не принял пароль: тогда состояние как до)
same=1
if [ -n "$UNITS" ]; then
  for u in $UNITS; do
    e=$(systemctl is-enabled "$u" 2>&1 | head -1)
    if [ "$MODE" = apply ]; then [ "$e" = enabled ] || same=0; else [ "$e" = masked ] || same=0; fi
  done
else
  h=$(held)
  if [ "$MODE" = apply ]; then [ "$h" = 0 ] || same=0; else [ "$h" -ge 1 ] || same=0; fi
fi
if [ "$rc" != 0 ] && [ "$same" = 1 ]; then echo "BB_SYS_NOCHANGE $CH $MODE rc=$rc (команда не выполнена, состояние как до)"; exit 5; fi
echo "BB_SYS_FAIL $CH $MODE rc=$rc check=$bad"
exit 4
