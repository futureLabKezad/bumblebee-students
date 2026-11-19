#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 13.11.2026, набор r7). Шаг 25 (25_metki_nomera.cmd): какие номера меток выдаёт детектор стека, пока дрон стоит неподвижно над меткой 0.
# Только подписка: /mavros/state и /aruco_detect/markers (номер и 4 угла каждой метки в кадре). Ничего не публикует: детектор НЕ будится
# (/aruco_detect/wake не трогается), моторы, режимы и параметры PX4 не трогаются. ros2 CLI не вызывается (демон ros2 не запускается),
# файлов на Pi не создаёт, sudo нет. По коду образа (aruco_detect.py, gate_by_flight_state) без взвода детектор кадры не берёт и молчит - это честно видно в MN_DETECTOR.
# Аргументы: 1 = режим pre|rec; 2 = секунды прослушивания (pre: 2..10, rec: 5..30); 3 = метка точки (латиница, цифры, _ -).
# stdout: MN_META, MN_STATE, MN_DETECTOR, MN_MSG (только rec: t=<с> n=<меток>, для каждой метки id=<номер> c=x1,y1;x2,y2;x3,y3;x4,y4), MN_END,
#   MN_REFUSED <почему> (отказ по безопасности), MN_ERROR <почему> (нет rclpy или сообщений); последняя строка BB_R7MN_DONE rc=<код>.
#   Код: 0 прочитано; 3 отказ (взведён, нет связи с FCU, нет /mavros/state); 4 ошибка.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
MODE="${1:-}"; DUR="${2:-}"; LABEL="${3:-}"
case "$MODE" in pre|rec) ;; *) echo "STOP: bad mode '$MODE'" >&2; exit 4;; esac
case "$DUR" in ''|*[!0-9]*) echo "STOP: bad seconds '$DUR'" >&2; exit 4;; esac
if [ "$MODE" = pre ]; then
  { [ "$DUR" -ge 2 ] && [ "$DUR" -le 10 ]; } || { echo "STOP: pre seconds must be 2..10" >&2; exit 4; }
else
  { [ "$DUR" -ge 5 ] && [ "$DUR" -le 30 ]; } || { echo "STOP: rec seconds must be 5..30" >&2; exit 4; }
fi
case "$LABEL" in ''|*[!A-Za-z0-9_-]*) echo "STOP: bad label" >&2; exit 4;; esac
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
echo "MN_META script r7_marker_ids.sh mode=$MODE seconds=$DUR label=$LABEL date=$(date '+%F %T')"
python3 - "$MODE" "$DUR" "$LABEL" <<'PY'
# BB_R7MN_PY
import sys, time


def p(*a):
    print(*a, flush=True)


def corners(mk):
    out = []
    for i in (1, 2, 3, 4):
        c = getattr(mk, 'c%d' % i, None)
        try:
            out.append('%.1f,%.1f' % (float(c.x), float(c.y)))
        except Exception:
            out.append('na,na')
    return ';'.join(out)


def run(node, rclpy, mode, dur, label, State, MarkerArray, QoSProfile, Rel):
    st = {}

    def on_state(m):
        st['c'] = bool(m.connected); st['a'] = bool(m.armed); st['m'] = str(m.mode)
    node.create_subscription(State, '/mavros/state', on_state, QoSProfile(depth=10, reliability=Rel.RELIABLE))
    msgs = []
    t0 = [None]

    def on_markers(m):
        if t0[0] is None:
            return   # до начала окна не считаем
        msgs.append((time.monotonic() - t0[0], list(getattr(m, 'markers', []))))
    node.create_subscription(MarkerArray, '/aruco_detect/markers', on_markers, 10)
    tw = time.monotonic()
    while 'c' not in st and time.monotonic() - tw < 8.0:
        rclpy.spin_once(node, timeout_sec=0.2)
    if 'c' not in st:
        p('MN_REFUSED no_mavros_state (/mavros/state молчит 8 с)')
        return 3
    p('MN_STATE connected=%s armed=%s mode=%s' % (st['c'], st['a'], st['m']))
    if not st['c']:
        p('MN_REFUSED fcu_not_connected (MAVROS не связан с полётным контроллером: не видно, взведён ли дрон)')
        return 3
    if st['a']:
        p('MN_REFUSED armed (дрон взведён: шаг только для невзведённого дрона)')
        return 3
    t0[0] = time.monotonic()
    tend = t0[0] + dur
    while time.monotonic() < tend:
        rclpy.spin_once(node, timeout_sec=0.1)
        if st.get('a'):
            p('MN_REFUSED armed_during (дрон взвели во время записи, запись прервана)')
            return 3
    try:
        pubs = list(node.get_publishers_info_by_topic('/aruco_detect/markers'))
        subs = list(node.get_subscriptions_info_by_topic('/main_camera/image_raw'))
        pub_nodes = sorted(set(str(e.node_name) for e in pubs))
        cam = 'yes' if any(str(e.node_name) == 'aruco_detect' for e in subs) else 'no'
    except Exception as e:
        pubs, pub_nodes, cam = [], ['graph_error_%s' % type(e).__name__], 'unknown'
    with_m = sum(1 for _t, arr in msgs if arr)
    p('MN_DETECTOR label=%s publishers=%d nodes=%s camera_subscription=%s msgs=%d with_markers=%d seconds=%d' % (
        label, len(pubs), ','.join(pub_nodes) or '-', cam, len(msgs), with_m, dur))
    ids = {}
    for t, arr in msgs:
        parts = []
        for mk in arr:
            i = int(getattr(mk, 'id', -1))
            ids[i] = ids.get(i, 0) + 1
            parts.append('id=%d c=%s' % (i, corners(mk)))
        if mode == 'rec':
            p(('MN_MSG t=%.3f n=%d ' % (t, len(arr)) + ' '.join(parts)).rstrip())
    p('MN_END label=%s msgs=%d with_markers=%d ids=%s' % (label, len(msgs), with_m, ','.join('%d:%d' % (k, v) for k, v in sorted(ids.items())) or 'none'))
    return 0


def main():
    mode, dur, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    try:
        import rclpy
        from rclpy.qos import QoSProfile, QoSReliabilityPolicy
        from mavros_msgs.msg import State
    except Exception as e:
        p('MN_ERROR import_failed %r' % (e,))
        return 4
    try:
        from aruco_pose.msg import MarkerArray
    except Exception as e:
        p('MN_ERROR markers_import_failed %r' % (e,))
        return 4
    rclpy.init()
    node = rclpy.create_node('bb_r7_marker_ids')
    try:
        return run(node, rclpy, mode, dur, label, State, MarkerArray, QoSProfile, QoSReliabilityPolicy)
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass


sys.exit(main())
PY
RC=$?
echo "BB_R7MN_DONE rc=$RC"
exit "$RC"
# BB_R7MN_MARK (метка для подделки ssh в тестах)
