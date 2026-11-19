#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 09.11.2026, v2; v3 и v4 - 13.11.2026). Читает настройки PX4 (компонент 1) через MAVROS и ничего не пишет на дрон. Файлов на Pi не создаёт.
# Основной источник: таблица MAVROS, сервис /mavros/mavros/get_parameters по именам из stdin (как check_flight_profile в drone.py).
#   Перед этим один ParamPull (r2, A-1: больше pull не делаем), потом до 3 повторов только для имён, которых в таблице нет (PARAMETER_NOT_SET).
#   Внимание (r2, A-4): плагин param MAVROS не фильтрует по компоненту, значения общих имён компонентов 1 и 125 могут перепутаться; это учитывает compare_params.ps1.
# v3 (13.11): при запуске MAVROS с общим переименованием (-r __node:=mavros, образ rc3 на 20EC) все 12 узлов-плагинов зовутся
#   /mavros/mavros, и у /mavros/mavros/get_parameters 12 серверов. 11 из них (обычные службы настроек узлов) отвечают пустым
#   списком, таблицу MAVROS отдаёт только плагин param, и его ответ приходит не первым. Обычный клиент rclpy берёт первый
#   ответ, поэтому 12.11 таблица дала 57, 0, 0, 0 из 1107. Теперь на каждый запрос собираются ВСЕ ответы и берётся только
#   полный (длина = числу имён; так отвечает лишь плагин param). Полных ответов несколько и значения расходятся - имя не
#   засчитано. ParamPull ждём до конца (сам MAVROS ждёт до 30 с). Счёт ответов пишется строкой PULL NOTE в файл .raw.txt.
# v4 (13.11, после замера на 20EC в 16:40): у /mavros/mavros/pull один сервер (плагин param). После force pull за 10 с приходит
#   970 из 1127 PARAM_VALUE, остальные MAVROS дозапрашивает только после своего ожидания 30 с, поэтому pull отвечает
#   success=False received=970, а через 2 с (к 31,9 с) приходят все 1127 (доказано подпиской на /mavros/mavros/event).
#   Теперь при success=False или без ответа свежесть доказывается событиями плагина param: каждое имя из stdin должно получить
#   событие ParamEvent ПОСЛЕ запроса (param_count - как у большинства событий после запроса, чтобы не засчитать компонент 125).
#   Доказано для всех имён - строки PULL FAILED нет (строка NOTE это пишет); хоть одно имя без свежего события - PULL FAILED, как в v3.
#   Кроме того, для каждого имени со свежим событием значение в таблице должно совпасть со значением из события (float32 / целое);
#   любое расхождение - PULL FAILED (event/table mismatch). Гейты и оценщик (compare_params.ps1) не менялись.
# Запасной источник: поток /parameter_events (он теряет события при потоке ~1100 подряд, находка F3), строки с префиксом "E ".
# stdout: "P<TAB>ИМЯ<TAB>i|d<TAB>значение" (таблица) и "E <строка yaml>" (поток). stderr: статус и BB_PARAMS_READ_DONE.
# stdin: имена настроек основы, по одному в строке.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
NAMES=$(cat)
[ -n "$NAMES" ] || { echo "STOP: no parameter names on stdin" >&2; exit 1; }
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
SL=$(timeout 30 ros2 service list < /dev/null 2>&1 || true)
printf '%s\n' "$SL" | grep -qx '/mavros/mavros/pull' || { echo "STOP: /mavros/mavros/pull not found" >&2; exit 1; }
printf '%s\n' "$SL" | grep -qx '/mavros/mavros/get_parameters' || { echo "STOP: /mavros/mavros/get_parameters not found" >&2; exit 1; }
echo "recording /parameter_events (fallback) and reading the MAVROS table ..." >&2
timeout 70 ros2 topic echo --full-length /parameter_events < /dev/null 2>/dev/null | sed -u 's/^/E /' &
REC=$!
export BB_NAMES="$NAMES"
# весь скрипт должен уложиться в 120 с ssh на ПК (run_params_check.ps1): python получает остаток до 105 с
export BB_BUDGET=$((105 - SECONDS))
python3 - <<'PY'
import os, sys, time, struct
import rclpy
from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy, DurabilityPolicy
from rcl_interfaces.srv import GetParameters
from mavros_msgs.srv import ParamPull
from mavros_msgs.msg import ParamEvent

T0 = time.monotonic()
BUDGET = max(20.0, min(80.0, float(os.environ.get('BB_BUDGET', '80'))))
names = [n for n in os.environ.get('BB_NAMES', '').split() if n]
rclpy.init()
node = rclpy.create_node('bb_params_read')
# v3: отдельный узел для чтения таблицы; его никто не крутит (spin), ответы забираем сами, все до одного
tnode = rclpy.create_node('bb_params_read_table')
tqos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=500,
                  reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
gp = tnode.create_client(GetParameters, '/mavros/mavros/get_parameters', qos_profile=tqos)
pl = node.create_client(ParamPull, '/mavros/mavros/pull')
# v4: события плагина param; считаются только пришедшие после запроса pull. Ключ - (имя, param_count): компонент 125 не смешивается
EV = {}
EVC = {}
EVV = {}
TREQ = [None]
FRESH = [False]
def on_event(m):
    t = time.monotonic()
    if TREQ[0] is None or t < TREQ[0]:
        return
    c = int(m.param_count)
    EVC[c] = EVC.get(c, 0) + 1
    # value в ParamEvent - rcl_interfaces/ParameterValue (проверено на 20EC: ros2 interface show mavros_msgs/msg/ParamEvent)
    v = val(m.value)
    EV[(m.param_id, c)] = (t, v)
    EVV.setdefault((m.param_id, c), set()).add(v)
eqos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=2000,
                  reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
esub = node.create_subscription(ParamEvent, '/mavros/mavros/event', on_event, eqos)

def err(s):
    sys.stderr.write(s + '\n')
    sys.stderr.flush()

def note(s):
    # заметка остаётся в .raw.txt на ПК и попадает в строку «ParamPull:» отчёта
    print('PULL\tNOTE\t' + s, flush=True)

def call(cli, req, t):
    f = cli.call_async(req)
    rclpy.spin_until_future_complete(node, f, timeout_sec=t)
    return f.result() if f.done() else None

def dom():
    return max(EVC, key=EVC.get) if EVC else None

def uncovered():
    d = dom()
    return [n for n in names if (n, d) not in EV]

def pull():
    if not pl.wait_for_service(timeout_sec=3.0):
        err('pull service missing')
        print('PULL\tFAILED\tno pull service', flush=True)
        return
    r = ParamPull.Request()
    r.force_pull = True
    # события, пришедшие до запроса и ждущие в очереди, выбираем и не считаем (TREQ ещё нет)
    td = time.monotonic()
    while time.monotonic() - td < 0.3:
        rclpy.spin_once(node, timeout_sec=0.05)
    TREQ[0] = time.monotonic()
    res = call(pl, r, 35.0)
    ok = None
    if res is None:
        err('pull: timeout')
        print('PULL\tNOTE\ttimeout', flush=True)
    else:
        ok = getattr(res, 'success', None)
        err('pull: done success=%s transferred=%s' % (ok, getattr(res, 'param_received', '?')))
        print('PULL\tNOTE\tdone success=%s received=%s' % (ok, getattr(res, 'param_received', '?')), flush=True)
    if ok is True:
        return
    # v4: ждём, пока каждое имя получит свежее значение от PX4 после запроса; оставляем на таблицу не меньше 30 с бюджета
    deadline = min(TREQ[0] + 45.0, T0 + BUDGET - 30.0)
    while time.monotonic() < deadline and uncovered():
        rclpy.spin_once(node, timeout_sec=0.05)
    miss = uncovered()
    if not miss:
        last = max(EV[(n, dom())][0] for n in names) - TREQ[0]
        FRESH[0] = True
        note('fresh by events: %d of %d names got PARAM_VALUE after the forced request (last at %.1f s, param_count %s)'
             % (len(names), len(names), last, dom()))
        return
    note('fresh by events: %d of %d, no fresh value for: %s' % (len(names) - len(miss), len(names), ' '.join(miss[:10])))
    err('PULL_FAILED: the MAVROS table may be stale')
    print('PULL\tFAILED\t' + ('not fresh (pull timeout)' if res is None else 'success=False'), flush=True)

def val(pv):
    t = pv.type
    if t == 1:
        return ('i', 1 if pv.bool_value else 0)
    if t == 2:
        return ('i', pv.integer_value)
    if t == 3:
        return ('d', pv.double_value)
    return None

def f32(x):
    return struct.unpack('f', struct.pack('f', float(x)))[0]

def ask(chunk):
    # один запрос; собираем все ответы до 3 с (после первого полного ответа ждём ещё 0,5 с)
    req = GetParameters.Request()
    req.names = chunk
    with gp.handle:
        seq = gp.handle.send_request(req)
    t1 = time.monotonic()
    first_full = None
    answers = 0
    full = []
    while True:
        now = time.monotonic()
        if now - t1 > 3.0 or (first_full is not None and now - first_full > 0.5):
            break
        with gp.handle:
            hr = gp.handle.take_response(GetParameters.Response)
        if hr is None or hr[0] is None:
            time.sleep(0.002)
            continue
        header, resp = hr
        if header.request_id.sequence_number != seq:
            continue                      # поздний ответ на прошлый запрос
        answers += 1
        if len(resp.values) == len(chunk):
            full.append(list(resp.values))
            if first_full is None:
                first_full = time.monotonic()
    return answers, full

def merge(chunk, full):
    # имя засчитано, если среди полных ответов ровно одно значение; разные значения - конфликт, не засчитано
    out = {}
    conflict = []
    for j, n in enumerate(chunk):
        seen = set()
        for vals in full:
            v = val(vals[j])
            if v is not None:
                seen.add(v)
        if len(seen) == 1:
            out[n] = seen.pop()
        elif len(seen) > 1:
            conflict.append(n)
    return out, conflict

if not gp.wait_for_service(timeout_sec=5.0):
    err('STOP: get_parameters service not answering')
    sys.exit(1)
pull()
time.sleep(1)
got = {}
missing = list(names)
n_req = 0
ans_seen = []
full_seen = []
conflicts = set()
for rnd in range(4):
    if rnd > 0:
        err('read pass %d: %d names not in the MAVROS table yet (re-asking only these names, no new pull)' % (rnd + 1, len(missing)))
        time.sleep(2)
    still = []
    for i in range(0, len(missing), 150):
        chunk = missing[i:i + 150]
        if time.monotonic() - T0 > BUDGET:
            still.extend(chunk)
            continue
        answers, full = ask(chunk)
        n_req += 1
        ans_seen.append(answers)
        full_seen.append(len(full))
        part, conflict = merge(chunk, full)
        for n in conflict:
            conflicts.add(n)
        for n in chunk:
            if n in part:
                got[n] = part[n]
                print('P\t%s\t%s\t%r' % (n, part[n][0], part[n][1]), flush=True)
            else:
                still.append(n)
    missing = still
    if not missing:
        break
err('TABLE_READ %d of %d' % (len(got), len(names)))
if n_req:
    note('table v3: requests %d, answers per request %d..%d, full answers per request %d..%d, conflicts %d, read %d of %d'
         % (n_req, min(ans_seen), max(ans_seen), min(full_seen), max(full_seen), len(conflicts), len(got), len(names)))
if conflicts:
    err('CONFLICT (not counted): ' + ' '.join(sorted(conflicts)[:20]))
# v4: значение в таблице = значению из свежего события (для каждого имени, у которого событие после запроса есть)
d = dom()
bad = []
checked = 0
for n, (k, v) in got.items():
    e = EV.get((n, d))
    if e is None:
        continue
    checked += 1
    ev = e[1]
    if len(EVV.get((n, d), ())) > 1:
        same = False                      # после запроса пришли разные значения одного имени (возможно, компонент 125)
    elif ev is None or ev[0] != k:
        same = False
    elif k == 'd':
        same = f32(v) == f32(ev[1])
    else:
        same = int(v) == int(ev[1])
    if not same:
        bad.append(n)
if EV:
    note('event/table check: %d names compared, %d differ' % (checked, len(bad)))
if bad:
    err('EVENT_TABLE_MISMATCH: ' + ' '.join(sorted(bad)[:20]))
    print('PULL\tFAILED\tevent/table mismatch: ' + ' '.join(sorted(bad)[:10]), flush=True)
if time.monotonic() - T0 > BUDGET and missing:
    err('time budget used up, %d names not read' % len(missing))
tnode.destroy_node()
node.destroy_node()
rclpy.shutdown()
PY
PYRC=$?
wait $REC || true
[ "$PYRC" = "0" ] || { echo "STOP: the table read failed (python exit $PYRC)" >&2; exit 2; }
echo "BB_PARAMS_READ_DONE" >&2
