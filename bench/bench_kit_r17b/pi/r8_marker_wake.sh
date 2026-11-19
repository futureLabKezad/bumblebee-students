#!/bin/bash
# МЕНЯЕТ ДРОН временно (Claude, 13.11.2026, набор r8). Шаг 25 (25_metki_nomera.cmd): номера меток и поза по меткам, пока дрон стоит неподвижно над меткой 0.
# Что меняет: будит детектор меток так же, как 03 (pi/vision_measure.sh): Bool true в /aruco_detect/wake раз в секунду, только пока идёт окно записи.
#   Проснувшийся детектор шлёт позу /aruco_map/pose, vpe_fix передаёт её в MAVROS и EKF2 и на НЕвзведённом дроне - меняется оценка положения EKF на земле.
#   Файлы, параметры PX4, режимы и моторы не трогаются; ros2 CLI не вызывается (демон ros2 не запускается); файлов на Pi не создаёт; sudo нет.
#   Как вернуть: детектор засыпает сам через 5 с после последнего wake (aruco_detect.py, WAKE_HOLD_S); EKF - выключить и включить дрон или сверить позицию EKF с рулеткой.
# Сигнал wake уходит только после проверки /mavros/state: связь с FCU есть и дрон НЕ взведён; если дрон взвели во время окна - wake сразу прекращается.
# Читает (только чтение): /mavros/state, /aruco_detect/markers (номер, центр и 4 угла каждой метки), /aruco_map/pose (поза base_link в системе карты),
#   /mavros/local_position/pose (позиция EKF, сведения), карту меток aruco_pose/map/map.txt (номера, место метки 0, sha256),
#   новые строки /tmp/bumblebee.log (туда пишет стек по bumblebee.service, StandardOutput=append) - строки vpe_fix «gate RESEEDED ... new_xyz=(x,y,z)».
# Аргументы: 1 = режим pre|rec; 2 = секунды окна (pre: 4..10, rec: 5..30); 3 = метка точки (латиница, цифры, _ -);
#   4 = с какого байта читать /tmp/bumblebee.log: start (с размера перед первым wake) или число (конец окна прошлой фазы).
# stdout: MN_META, MN_MAP, MN_STATE, MN_WAKE, MN_MSG, MN_POSE, MN_EKF, MN_DETECTOR, MN_LOG, MN_RESEED, MN_END,
#   MN_REFUSED <почему> (отказ по безопасности, до wake или wake прерван), MN_ERROR <почему>; последняя строка BB_R8MN_DONE rc=<код>.
#   Код: 0 записано; 3 отказ (взведён, нет связи с FCU, нет /mavros/state); 4 ошибка.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
MODE="${1:-}"; DUR="${2:-}"; LABEL="${3:-}"; LOGFROM="${4:-}"
case "$MODE" in pre|rec) ;; *) echo "STOP: bad mode '$MODE'" >&2; exit 4;; esac
case "$DUR" in ''|*[!0-9]*) echo "STOP: bad seconds '$DUR'" >&2; exit 4;; esac
if [ "$MODE" = pre ]; then
  { [ "$DUR" -ge 4 ] && [ "$DUR" -le 10 ]; } || { echo "STOP: pre seconds must be 4..10" >&2; exit 4; }
else
  { [ "$DUR" -ge 5 ] && [ "$DUR" -le 30 ]; } || { echo "STOP: rec seconds must be 5..30" >&2; exit 4; }
fi
case "$LABEL" in ''|*[!A-Za-z0-9_-]*) echo "STOP: bad label" >&2; exit 4;; esac
case "$LOGFROM" in start) ;; ''|*[!0-9]*) echo "STOP: bad log offset '$LOGFROM'" >&2; exit 4;; esac
[ "${#LOGFROM}" -le 15 ] || { echo "STOP: bad log offset" >&2; exit 4; }
# Окружение ROS как у стека (как в pi/r7_marker_ids.sh r7 и ros_env pi/r6_sys_check.sh r6): профиль, jazzy, четыре известные строки source
# из ~/start_bumblebee.sh (посторонние строки не выполняются), /etc/bumblebee/ros.env (домен ROS стека) и UDPv4. Только чтение файлов.
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
if [ -f "$HOME/start_bumblebee.sh" ]; then
  while IFS= read -r l; do
    case "$l" in
      "source /home/lb/ros2_ws/install/setup.bash"|"source /home/lb/bench_ws/mavros/install/local_setup.bash"|"source /home/lb/bench_ws/r2j/install/local_setup.bash"|"source /home/lb/bench_ws/port/install/local_setup.bash")
        f="$HOME/${l#source /home/lb/}"; [ -f "$f" ] && source "$f" < /dev/null 2>/dev/null ;;
    esac
  done < "$HOME/start_bumblebee.sh"
fi
if [ -r /etc/bumblebee/ros.env ]; then set -a; . /etc/bumblebee/ros.env; set +a; fi
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4
echo "MN_META script r8_marker_wake.sh mode=$MODE seconds=$DUR label=$LABEL logfrom=$LOGFROM date=$(date '+%F %T')"
python3 - "$MODE" "$DUR" "$LABEL" "$LOGFROM" <<'PY'
# BB_R8MN_PY
import hashlib, math, os, re, sys, time

LOG = os.environ.get('BB_TEST_LOG', '/tmp/bumblebee.log')   # BB_TEST_LOG - только для тестов в WSL (как LOGF в pi/r6_*.sh); по ssh не задаётся
LOG_MAX = 4 * 1024 * 1024
RESEED_RE = re.compile(r'gate RESEEDED \(([^)]*)\) age=(\S+)s new_xyz=\((-?[0-9.]+),(-?[0-9.]+),(-?[0-9.]+)\)')


def p(*a):
    print(*a, flush=True)


def corners(mk):
    pts = []
    for i in (1, 2, 3, 4):
        c = getattr(mk, 'c%d' % i, None)
        try:
            pts.append((float(c.x), float(c.y)))
        except Exception:
            pts.append(None)
    cs = ';'.join(('%.1f,%.1f' % q) if q else 'na,na' for q in pts)
    good = [q for q in pts if q]
    if len(good) == 4:
        ctr = '%.1f,%.1f' % (sum(q[0] for q in good) / 4.0, sum(q[1] for q in good) / 4.0)
    else:
        ctr = 'na,na'
    return ctr, cs


def yaw_of(q):
    try:
        return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
    except Exception:
        return float('nan')


def read_map():
    try:
        from ament_index_python.packages import get_package_share_directory
        path = os.path.join(get_package_share_directory('aruco_pose'), 'map', 'map.txt')
    except Exception as e:
        return 'MN_MAP error=share_not_found_%s' % type(e).__name__
    try:
        with open(path, 'rb') as fh:
            data = fh.read()
    except Exception as e:
        return 'MN_MAP error=unreadable_%s file=%s' % (type(e).__name__, path)
    ids, m0 = [], None
    for line in data.decode('utf-8', 'replace').splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        f = s.split()
        if len(f) < 8:   # как aruco_detect.py (_load_map_file): короче 8 полей - строка пропускается
            continue
        try:
            i = int(f[0]); x, y, z = float(f[2]), float(f[3]), float(f[4])
        except Exception:
            continue
        ids.append(i)
        if i == 0:
            m0 = (x, y, z)
    return 'MN_MAP file=%s sha256=%s ids=%s m0=%s' % (
        path, hashlib.sha256(data).hexdigest(), ','.join(str(i) for i in sorted(set(ids))) or 'none',
        ('%.3f,%.3f,%.3f' % m0) if m0 else 'none')


def log_size():
    try:
        return os.path.getsize(LOG)
    except Exception:
        return -1


def read_log(frm):
    """Новые байты /tmp/bumblebee.log с frm до конца (не больше LOG_MAX). (размер, rotated, cut, строки) или (None, причина, '', [])."""
    try:
        size = os.path.getsize(LOG)
        rot = 'no'
        if frm > size:      # файл стал короче (начат заново) - читаем с начала
            frm, rot = 0, 'yes'
        start, cut = frm, 'no'
        if size - start > LOG_MAX:
            start, cut = size - LOG_MAX, 'yes'
        with open(LOG, 'rb') as fh:
            fh.seek(start)
            data = fh.read(size - start)
        return size, rot, cut, data.decode('utf-8', 'replace').splitlines()
    except Exception as e:
        return None, type(e).__name__, '', []


def run(node, rclpy, mode, dur, label, logfrom, M):
    st = {}

    def on_state(m):
        st['c'] = bool(m.connected); st['a'] = bool(m.armed); st['m'] = str(m.mode)
    node.create_subscription(M['State'], '/mavros/state', on_state, M['QoSProfile'](depth=10, reliability=M['Rel'].RELIABLE))
    msgs, poses, ekf = [], [], []
    t0 = [None]

    def on_markers(m):
        if t0[0] is not None:
            msgs.append((time.monotonic() - t0[0], list(getattr(m, 'markers', []))))

    def on_pose(m):
        if t0[0] is not None:
            pp = m.pose.pose
            poses.append((time.monotonic() - t0[0], pp.position.x, pp.position.y, pp.position.z, yaw_of(pp.orientation)))

    def on_ekf(m):
        if t0[0] is not None:
            ekf.append((m.pose.position.x, m.pose.position.y, m.pose.position.z))
    node.create_subscription(M['MarkerArray'], '/aruco_detect/markers', on_markers, 10)
    node.create_subscription(M['PoseCov'], '/aruco_map/pose', on_pose, 10)
    node.create_subscription(M['PoseStamped'], '/mavros/local_position/pose', on_ekf,
                             M['QoSProfile'](depth=10, reliability=M['Rel'].BEST_EFFORT))
    p(read_map())
    tw = time.monotonic()
    while 'c' not in st and time.monotonic() - tw < 8.0:
        rclpy.spin_once(node, timeout_sec=0.2)
    if 'c' not in st:
        p('MN_REFUSED no_mavros_state (/mavros/state молчит 8 с; wake не посылался)')
        return 3
    p('MN_STATE connected=%s armed=%s mode=%s' % (st['c'], st['a'], st['m']))
    if not st['c']:
        p('MN_REFUSED fcu_not_connected (MAVROS не связан с полётным контроллером: не видно, взведён ли дрон; wake не посылался)')
        return 3
    if st['a']:
        p('MN_REFUSED armed (дрон взведён: шаг только для невзведённого дрона; wake не посылался)')
        return 3
    lf = log_size() if logfrom == 'start' else int(logfrom)
    # единственная публикация: Bool true в /aruco_detect/wake раз в секунду (как pi/vision_measure.sh шага 03), только после проверок выше
    wake_pub = node.create_publisher(M['Bool'], '/aruco_detect/wake', 10)
    sent = [0]

    def wake_tick():
        wake_pub.publish(M['Bool'](data=True)); sent[0] += 1
    wake_tick()
    timer = node.create_timer(1.0, wake_tick)
    stopped = ['']
    warm = 2.0 if mode == 'rec' else 0.0
    tend_w = time.monotonic() + warm
    while time.monotonic() < tend_w and not stopped[0]:
        rclpy.spin_once(node, timeout_sec=0.1)
        if st.get('a'):
            stopped[0] = 'armed_during'
    t0[0] = time.monotonic()
    tend = t0[0] + dur
    while time.monotonic() < tend and not stopped[0]:
        rclpy.spin_once(node, timeout_sec=0.1)
        if st.get('a'):
            stopped[0] = 'armed_during'
    node.destroy_timer(timer)    # wake больше не уходит; детектор уснёт сам через 5 с
    p('MN_WAKE sent=%d topic=/aruco_detect/wake hz=1 warmup_s=%.0f' % (sent[0], warm))
    if stopped[0]:
        p('MN_REFUSED armed_during (дрон взвели во время записи: wake прекращён, запись прервана)')
        return 3
    try:
        pubs = list(node.get_publishers_info_by_topic('/aruco_detect/markers'))
        subs = list(node.get_subscriptions_info_by_topic('/main_camera/image_raw'))
        pub_nodes = sorted(set(str(e.node_name) for e in pubs))
        cam = 'yes' if any(str(e.node_name) == 'aruco_detect' for e in subs) else 'no'
    except Exception as e:
        pubs, pub_nodes, cam = [], ['graph_error_%s' % type(e).__name__], 'unknown'
    with_m = sum(1 for _t, arr in msgs if arr)
    ids = {}
    for t, arr in msgs:
        parts = []
        for mk in arr:
            i = int(getattr(mk, 'id', -1))
            ids[i] = ids.get(i, 0) + 1
            ctr, cs = corners(mk)
            parts.append('id=%d ctr=%s c=%s' % (i, ctr, cs))
        p(('MN_MSG t=%.3f n=%d ' % (t, len(arr)) + ' '.join(parts)).rstrip())
    for t, x, y, z, yw in poses:
        p('MN_POSE t=%.3f x=%.3f y=%.3f z=%.3f yaw=%.3f' % (t, x, y, z, yw))
    if ekf:
        x, y, z = ekf[-1]
        p('MN_EKF n=%d x=%.3f y=%.3f z=%.3f (последняя /mavros/local_position/pose, сведения)' % (len(ekf), x, y, z))
    else:
        p('MN_EKF n=0')
    p('MN_DETECTOR label=%s publishers=%d nodes=%s camera_subscription=%s msgs=%d with_markers=%d poses=%d seconds=%d' % (
        label, len(pubs), ','.join(pub_nodes) or '-', cam, len(msgs), with_m, len(poses), dur))
    size, rot, cut, lines = read_log(lf if lf >= 0 else 0)
    if size is None or lf < 0:
        p('MN_LOG file=%s readable=no reason=%s' % (LOG, rot if size is None else 'size_unknown_at_start'))
    else:
        rs = [l for l in lines if 'gate RESEEDED' in l]
        p('MN_LOG file=%s readable=yes from=%d to=%d rotated=%s cut=%s lines=%d reseeded=%d deferred=%d rejected=%d' % (
            LOG, lf, size, rot, cut, len(lines), len(rs), sum(1 for l in lines if 'reseed deferred' in l), sum(1 for l in lines if 'rejected pose' in l)))
        for l in rs:
            mm = RESEED_RE.search(l)
            if mm:
                p('MN_RESEED reason=%s x=%s y=%s z=%s line=%s' % (mm.group(1).replace(' ', '_'), mm.group(3), mm.group(4), mm.group(5), l.strip()[:200]))
            else:
                p('MN_RESEED reason=unparsed x=na y=na z=na line=%s' % l.strip()[:200])
    p('MN_END label=%s msgs=%d with_markers=%d ids=%s poses=%d' % (
        label, len(msgs), with_m, ','.join('%d:%d' % (k, v) for k, v in sorted(ids.items())) or 'none', len(poses)))
    return 0


def main():
    mode, dur, label, logfrom = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    M = {}
    try:
        import rclpy
        from rclpy.qos import QoSProfile, QoSReliabilityPolicy
        from std_msgs.msg import Bool
        from mavros_msgs.msg import State
        from geometry_msgs.msg import PoseWithCovarianceStamped, PoseStamped
        M.update(QoSProfile=QoSProfile, Rel=QoSReliabilityPolicy, Bool=Bool, State=State, PoseCov=PoseWithCovarianceStamped, PoseStamped=PoseStamped)
    except Exception as e:
        p('MN_ERROR import_failed %r' % (e,))
        return 4
    try:
        from aruco_pose.msg import MarkerArray
        M['MarkerArray'] = MarkerArray
    except Exception as e:
        p('MN_ERROR markers_import_failed %r' % (e,))
        return 4
    rclpy.init()
    node = rclpy.create_node('bb_r8_marker_wake')
    try:
        return run(node, rclpy, mode, dur, label, logfrom, M)
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
echo "BB_R8MN_DONE rc=$RC"
exit "$RC"
# BB_R8MN_MARK (метка для подделки ssh в тестах)
