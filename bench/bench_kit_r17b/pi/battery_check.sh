#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2). Батарея 20EC через MAVROS: напряжение, предупреждения, настройки батареи. Ничего не пишет в PX4, детектор не будит, издателей не создаёт.
# Что читает: подписки на топик батареи (sensor_msgs/BatteryState, имя по суффиксу /battery) и на текстовые сообщения PX4 (mavros_msgs/StatusText, суффикс /statustext/recv);
# настройки BAT1_SOURCE, BAT1_N_CELLS, BAT1_V_EMPTY, BAT1_V_CHARGED, BAT1_V_DIV, BAT1_A_PER_V, BAT_LOW_THR, BAT_CRIT_THR, BAT_EMERGEN_THR, COM_LOW_BAT_ACT, CBRK_SUPPLY_CHK
# из таблицы MAVROS (сервис get_parameters, как params_read.sh набора r4; ParamPull не делается: таблица та, что MAVROS получил при подключении к контроллеру).
# Скрипт сам файлов на Pi не создаёт (ros2/rclpy могут вести свои журналы в ~/.ros).
# Аргумент 1: длительность наблюдения в секундах (10..300, по умолчанию 30).
# stdout: строки META / BAT / STATUSTEXT / PARAM / SUMMARY, в конце BB_BATTERY_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
DUR="${1:-30}"
case "$DUR" in ''|*[!0-9]*) echo "STOP: bad duration '$DUR'" >&2; exit 1;; esac
[ "$DUR" -ge 10 ] && [ "$DUR" -le 300 ] || { echo "STOP: duration must be 10..300 s" >&2; exit 1; }
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
echo "META script battery_check.sh dur=$DUR date=$(date '+%F %T')"
export BB_BATT_MAIN=1
python3 - "$DUR" <<'PY'
# BB_BATT_PY_BEGIN
import os, sys, time, re

PARAMS = ['BAT1_SOURCE', 'BAT1_N_CELLS', 'BAT1_V_EMPTY', 'BAT1_V_CHARGED', 'BAT1_V_DIV', 'BAT1_A_PER_V',
          'BAT_LOW_THR', 'BAT_CRIT_THR', 'BAT_EMERGEN_THR', 'COM_LOW_BAT_ACT', 'CBRK_SUPPLY_CHK']
BAT_TEXT = re.compile(r'batt|voltage|power|low\b|critical|emergen|failsafe|undervolt', re.I)


def p(*a):
    print(*a, flush=True)


def fmt(x, nd=3):
    return ('%.' + str(nd) + 'f') % x


def is_battery_text(text):
    """True, если строка PX4 похожа на сообщение о батарее или питании (грубый фильтр только для пометки; в сводку идут ВСЕ строки)."""
    return bool(BAT_TEXT.search(text or ''))


def stats(vals):
    v = [x for x in vals if x == x]
    if not v:
        return None
    return {'n': len(v), 'min': min(v), 'max': max(v), 'mean': sum(v) / len(v)}


def find_topic(names_and_types, suffix, type_suffix):
    """Имя топика с данным суффиксом и типом, оканчивающимся на type_suffix; при нескольких берётся первое в алфавитном порядке."""
    found = sorted(n for n, types in names_and_types if n.endswith(suffix) and any(t.endswith(type_suffix) for t in types))
    return found[0] if found else None


def param_value(pv):
    """rcl_interfaces/ParameterValue -> ('i'|'d', value) или None."""
    t = pv.type
    if t == 1:
        return ('i', 1 if pv.bool_value else 0)
    if t == 2:
        return ('i', pv.integer_value)
    if t == 3:
        return ('d', pv.double_value)
    return None


def main():
    dur = int(sys.argv[1])
    try:
        import rclpy
        from mavros_msgs.msg import State, StatusText
        from sensor_msgs.msg import BatteryState
        from rcl_interfaces.srv import GetParameters
        from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
    except Exception as e:
        p('ERROR import_failed %r' % (e,))
        return 4
    rclpy.init()
    node = rclpy.create_node('bb_battery_check')
    st = {'seen': False, 'connected': None, 'armed': None, 'mode': None}

    def on_state(m):
        st.update(seen=True, connected=bool(m.connected), armed=bool(m.armed), mode=str(m.mode))

    node.create_subscription(State, '/mavros/state', on_state, QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE))
    t_wait = time.monotonic()
    while not st['seen'] and time.monotonic() - t_wait < 8.0:
        rclpy.spin_once(node, timeout_sec=0.2)
    if st['seen']:
        p('META state connected=%s armed=%s mode=%s' % (st['connected'], st['armed'], st['mode']))
    else:
        p('META state none (топик /mavros/state молчит 8 с)')
    names = node.get_topic_names_and_types()
    t_bat = find_topic(names, '/battery', 'BatteryState')
    t_txt = find_topic(names, '/statustext/recv', 'StatusText')
    p('META battery_topic %s' % (t_bat or 'none_found'))
    p('META statustext_topic %s' % (t_txt or 'none_found'))
    bat = []
    texts = []
    t0 = time.monotonic()
    best = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.BEST_EFFORT, history=QoSHistoryPolicy.KEEP_LAST)

    def on_bat(m):
        bat.append((time.monotonic() - t0, float(m.voltage), float(m.percentage), float(m.current), bool(m.present), len(list(m.cell_voltage))))

    def on_txt(m):
        texts.append((time.monotonic() - t0, int(m.severity), str(m.text)))

    if t_bat:
        node.create_subscription(BatteryState, t_bat, on_bat, best)
    if t_txt:
        node.create_subscription(StatusText, t_txt, on_txt, 10)
    t_end = t0 + dur
    while time.monotonic() < t_end:
        rclpy.spin_once(node, timeout_sec=0.1)
    t_fin = time.monotonic() - t0
    # настройки
    svc = None
    try:
        for n, types in node.get_service_names_and_types():
            if n == '/mavros/mavros/get_parameters' and any(t.endswith('GetParameters') for t in types):
                svc = n
                break
    except Exception as e:
        p('META service_discovery_failed %r' % (e,))
    got = {}
    if svc:
        cli = node.create_client(GetParameters, svc)
        if cli.wait_for_service(timeout_sec=5.0):
            req = GetParameters.Request()
            req.names = list(PARAMS)
            fut = cli.call_async(req)
            rclpy.spin_until_future_complete(node, fut, timeout_sec=8.0)
            r = fut.result() if fut.done() else None
            vals = list(r.values) if r is not None else []
            for j, n in enumerate(PARAMS):
                v = param_value(vals[j]) if j < len(vals) else None
                if v is not None:
                    got[n] = v
        else:
            p('META get_parameters service not answering (%s)' % svc)
    else:
        p('META get_parameters service not found')
    # вывод
    for t, v, pc, cur, pres, nc in bat[:5]:
        p('BAT t=%s voltage_v=%s percentage=%s current_a=%s present=%s cells_reported=%d' % (fmt(t, 1), fmt(v, 2), fmt(pc, 2), fmt(cur, 2), pres, nc))
    if len(bat) > 5:
        t, v, pc, cur, pres, nc = bat[-1]
        p('BAT t=%s voltage_v=%s percentage=%s current_a=%s present=%s cells_reported=%d (последний из %d)' % (fmt(t, 1), fmt(v, 2), fmt(pc, 2), fmt(cur, 2), pres, nc, len(bat)))
    for t, sev, tx in texts[:60]:
        p('STATUSTEXT t=%s severity=%d battery_related=%s text=%s' % (fmt(t, 1), sev, 'yes' if is_battery_text(tx) else 'no', tx.replace('\n', ' ')[:200]))
    for n in PARAMS:
        if n in got:
            p('PARAM %s %s %r' % (n, got[n][0], got[n][1]))
        else:
            p('PARAM %s not_in_MAVROS_table' % n)
    p('SUMMARY duration_s %s' % fmt(t_fin, 1))
    sv = stats([b[1] for b in bat])
    if sv:
        sp = stats([b[2] for b in bat])
        p('SUMMARY battery_msgs count=%d hz=%s voltage_v min=%s max=%s mean=%s percentage min=%s max=%s present_values=%s cells_reported=%s' % (
            sv['n'], fmt(sv['n'] / max(t_fin, 1e-9), 2), fmt(sv['min'], 2), fmt(sv['max'], 2), fmt(sv['mean'], 2),
            fmt(sp['min'], 2) if sp else 'n/a', fmt(sp['max'], 2) if sp else 'n/a',
            ','.join(sorted(set(str(b[4]) for b in bat))), ','.join(str(x) for x in sorted(set(b[5] for b in bat)))))
    else:
        p('SUMMARY battery_msgs count=0 (напряжение по MAVROS не пришло: темы нет или она молчит)')
    nb = sum(1 for t in texts if is_battery_text(t[2]))
    p('SUMMARY statustext count=%d battery_related=%d (все строки выше, до 60)' % (len(texts), nb))
    p('SUMMARY params_read %d of %d' % (len(got), len(PARAMS)))
    rclpy.shutdown()
    return 0


if __name__ == '__main__' and os.environ.get('BB_BATT_MAIN', '1') == '1':
    sys.exit(main())
# BB_BATT_PY_END
PY
PYRC=$?
echo "META python_exit $PYRC"
echo "BB_BATTERY_DONE rc=$PYRC"
exit "$PYRC"
