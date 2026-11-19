#!/bin/bash
# Замер работы зрения на Pi 20EC без взвода моторов (Claude, 10.11.2026). Параметры, команды, режимы и setpoint в PX4 не пишутся.
# Скрипт сам файлов на Pi не создаёт (ros2/rclpy могут вести свои журналы в ~/.ros).
# Единственное действие: если WAKE=1, раз в секунду в топик /aruco_detect/wake уходит Bool true (детектор в r2e/r2j спит, пока дрон не взведён;
# aruco_detect.py:544, держит 5 с). Это будит детектор меток; проснувшийся детектор даёт позу, а vpe_fix в r2j на НЕвзведённом дроне её передаёт в MAVROS (vpe_fix.py, функция _evaluate_gate), то есть косвенно зрение может дойти до EKF2.
# Аргументы: 1 = длительность в секундах (10..1800), 2 = метка (латиница, цифры, _ -), 3 = режим measure|vibration, 4 = WAKE 1|0.
#   measure   : перед замером проверяется /mavros/state; если дрон взведён или нет связи с FCU, замер НЕ начинается (REFUSED).
#   vibration : взвод делает владелец пультом; скрипт только пишет журнал (в этом режиме взведённое состояние допустимо).
# stdout: строки META / SAMPLE / EVENT / SUMMARY / J (журнал bumblebee) / REFUSED, в конце BB_BENCH_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
DUR="${1:-300}"; LABEL="${2:-x}"; MODE="${3:-measure}"; WAKE="${4:-1}"
case "$DUR" in ''|*[!0-9]*) echo "STOP: bad duration '$DUR'" >&2; exit 1;; esac
[ "$DUR" -ge 10 ] && [ "$DUR" -le 1800 ] || { echo "STOP: duration must be 10..1800 s" >&2; exit 1; }
case "$LABEL" in *[!A-Za-z0-9_-]*|'') echo "STOP: bad label" >&2; exit 1;; esac
case "$MODE" in measure|vibration) ;; *) echo "STOP: bad mode '$MODE'" >&2; exit 1;; esac
case "$WAKE" in 0|1) ;; *) echo "STOP: bad wake '$WAKE'" >&2; exit 1;; esac
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
START=$(date +%s)
# r17a: stack log size before run; BB_TEST_LOG only in WSL tests
LOGF="${BB_TEST_LOG:-/tmp/bumblebee.log}"; LOG0=$(stat -c %s "$LOGF" 2>/dev/null || echo -1)
find /home/lb -maxdepth 8 \( -name aruco_detect.py -o -name vpe_fix.py -o -name camera_fix.py \) -path '*bumblebee*' 2>/dev/null | head -9 | while IFS= read -r f; do echo "META image_file $(sha256sum "$f" 2>/dev/null | cut -c1-64) $f"; done
echo "META script vision_measure.sh dur=$DUR label=$LABEL mode=$MODE wake=$WAKE start_epoch=$START date=$(date '+%F %T')"
export BB_BENCH_MAIN=1
python3 - "$DUR" "$LABEL" "$MODE" "$WAKE" <<'PY'
# BB_BENCH_PY_BEGIN
import os, sys, time, math, subprocess

CLK_TCK = os.sysconf('SC_CLK_TCK') if hasattr(os, 'sysconf') else 100
WATCH = ['aruco_detect.py', 'vpe_fix.py', 'camera_fix.py', 'v4l2_camera', 'mavros_node', 'qos_relay.py', 'setpoint_freshness.py']


def rate_stats(times, t0, t1, gap_s=0.5):
    """Статистика приходов сообщений. times в секундах (монотонные), окно [t0, t1].
    gaps_over: число пропусков больше gap_s МЕЖДУ сообщениями; start_delay: ожидание первого; end_silence: тишина в конце."""
    dur = max(t1 - t0, 1e-9)
    ts = sorted(t for t in times if t0 <= t <= t1)
    n = len(ts)
    res = {'count': n, 'hz': n / dur, 'gaps_over': 0, 'max_gap': 0.0, 'gaps_top': [], 'start_delay': dur, 'end_silence': dur, 'mean_dt': 0.0}
    if n == 0:
        return res
    res['start_delay'] = ts[0] - t0
    res['end_silence'] = t1 - ts[-1]
    gaps = [ts[i + 1] - ts[i] for i in range(n - 1)]
    if gaps:
        res['mean_dt'] = sum(gaps) / len(gaps)
        res['max_gap'] = max(gaps)
        big = sorted([g for g in gaps if g > gap_s], reverse=True)
        res['gaps_over'] = len(big)
        res['gaps_top'] = big[:5]
    return res


def gap_counts(times, t0, t1, limits=(0.4, 1.0, 1.5)):
    """Сколько пропусков между соседними сообщениями длиннее каждого из limits (в секундах), самый длинный пропуск и пять самых длинных.
    Только пропуски МЕЖДУ сообщениями внутри окна [t0, t1] (начало и конец окна не считаются)."""
    ts = sorted(t for t in times if t0 <= t <= t1)
    gaps = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    res = {'n': len(ts), 'max': max(gaps) if gaps else 0.0, 'top': sorted(gaps, reverse=True)[:5]}
    for lim in limits:
        res['over_%s' % lim] = sum(1 for g in gaps if g > lim)
    return res


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(math.floor(k)); c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def latency_stats(vals):
    v = sorted(vals)
    if not v:
        return {'n': 0, 'mean': 0.0, 'p50': 0.0, 'p95': 0.0, 'max': 0.0}
    return {'n': len(v), 'mean': sum(v) / len(v), 'p50': percentile(v, 0.5), 'p95': percentile(v, 0.95), 'max': v[-1]}


THROTTLE_BITS = {0: 'undervoltage_now', 1: 'arm_freq_capped_now', 2: 'throttled_now', 3: 'soft_temp_limit_now',
                 16: 'undervoltage_occurred', 17: 'arm_freq_capped_occurred', 18: 'throttled_occurred', 19: 'soft_temp_limit_occurred'}


def parse_throttled(text):
    """'throttled=0x50005' -> (0x50005, ['undervoltage_now', ...]); при ошибке (None, [])."""
    try:
        s = text.strip().split('=')[-1]
        v = int(s, 16)
    except Exception:
        return None, []
    return v, [name for bit, name in sorted(THROTTLE_BITS.items()) if v & (1 << bit)]


def parse_proc_stat_cpu(line):
    """Первая строка /proc/stat -> (busy, total) в тиках."""
    f = [int(x) for x in line.split()[1:9]]
    idle = f[3] + f[4]
    total = sum(f)
    return total - idle, total


def parse_pid_ticks(stat_text):
    """/proc/PID/stat -> utime+stime (тики). Имя процесса в скобках может содержать пробелы."""
    rest = stat_text[stat_text.rindex(')') + 2:].split()
    return int(rest[11]) + int(rest[12])


def scan_watch(proc_root='/proc'):
    found = {}
    try:
        names = os.listdir(proc_root)
    except Exception:
        return found
    for d in names:
        if not d.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, d, 'cmdline'), 'rb') as fh:
                cmd = fh.read().replace(b'\0', b' ').decode('utf-8', 'replace')
        except Exception:
            continue
        if 'BB_BENCH_PY_BEGIN' in cmd:
            continue
        for w in WATCH:
            if w in cmd and ('python' in cmd or w in ('v4l2_camera', 'mavros_node')):
                found.setdefault(w, []).append(int(d))
    return found


def read_temp_c():
    try:
        out = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, text=True, timeout=3).stdout
        return float(out.split('=')[1].split("'")[0])
    except Exception:
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as fh:
                return int(fh.read().strip()) / 1000.0
        except Exception:
            return None


def read_throttled():
    try:
        out = subprocess.run(['vcgencmd', 'get_throttled'], capture_output=True, text=True, timeout=3).stdout
        return parse_throttled(out)
    except Exception:
        return None, []


def p(*a):
    print(*a, flush=True)


def fmt(x, nd=3):
    return ('%.' + str(nd) + 'f') % x


def main():
    dur = int(sys.argv[1]); label = sys.argv[2]; mode = sys.argv[3]; wake = sys.argv[4] == '1'
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
        from std_msgs.msg import Bool, Int32
        from mavros_msgs.msg import State
        from sensor_msgs.msg import Image
    except Exception as e:
        p('REFUSED import_failed %r' % (e,))
        return 4
    try:
        from aruco_pose.msg import MarkerArray
    except Exception as e:
        MarkerArray = None
        p('META markers_import_failed %r' % (e,))
    try:
        from geometry_msgs.msg import PoseWithCovarianceStamped, PoseStamped
    except Exception:
        PoseWithCovarianceStamped = PoseStamped = None

    rclpy.init()
    node = rclpy.create_node('bb_bench_measure')
    st = {'connected': None, 'armed': None, 'mode': None, 'first': False}
    events = []
    t_start_mono = time.monotonic()

    def on_state(m):
        cur = (bool(m.connected), bool(m.armed), str(m.mode))
        if not st['first'] or cur != (st['connected'], st['armed'], st['mode']):
            if st['first']:
                p('EVENT t=%s state connected=%s armed=%s mode=%s' % (fmt(time.monotonic() - t_start_mono, 1), cur[0], cur[1], cur[2]))
                events.append(time.monotonic())
            st['connected'], st['armed'], st['mode'] = cur
            st['first'] = True

    node.create_subscription(State, '/mavros/state', on_state, QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE))
    t_wait = time.monotonic()
    while not st['first'] and time.monotonic() - t_wait < 8.0:
        rclpy.spin_once(node, timeout_sec=0.2)
    if not st['first']:
        p('REFUSED no_mavros_state (топик /mavros/state молчит 8 с)')
        rclpy.shutdown(); return 3
    p('META initial_state connected=%s armed=%s mode=%s' % (st['connected'], st['armed'], st['mode']))
    if not st['connected']:
        p('REFUSED fcu_not_connected (MAVROS не связан с полётным контроллером; vpe_fix тогда молчит, замер бессмыслен)')
        rclpy.shutdown(); return 3
    if mode == 'measure' and st['armed']:
        p('REFUSED armed (дрон взведён: замер без взвода не начат, детектор не будился)')
        rclpy.shutdown(); return 3

    times = {'markers': [], 'camera': [], 'vision': {}}
    lat = []
    nmarkers = []
    ids_count = {}
    best = QoSProfile(depth=5, reliability=QoSReliabilityPolicy.BEST_EFFORT, history=QoSHistoryPolicy.KEEP_LAST)

    def on_markers(m):
        now = time.monotonic()
        times['markers'].append(now)
        arr = list(getattr(m, 'markers', []))
        nmarkers.append(len(arr))
        for mk in arr:
            ids_count[int(mk.id)] = ids_count.get(int(mk.id), 0) + 1
        try:
            s = m.header.stamp
            if s.sec or s.nanosec:
                lat.append((node.get_clock().now().nanoseconds - (s.sec * 10 ** 9 + s.nanosec)) / 1e6)
        except Exception:
            pass

    if MarkerArray is not None:
        node.create_subscription(MarkerArray, '/aruco_detect/markers', on_markers, 10)

    def on_cam(_raw):
        times['camera'].append(time.monotonic())

    cam_mode = 'raw'
    try:
        node.create_subscription(Image, '/main_camera/image_raw', on_cam, best, raw=True)
    except TypeError:
        cam_mode = 'not_available (rclpy без raw=True)'
    p('META camera_subscription %s' % cam_mode)

    # r2 (T37 §5, T42 §3): кадры до camera_fix (image_raw_yuv, если такой топик есть) и сообщения детектора markers_used (Int32: сколько меток принято в кадре)
    cam_yuv_topic = None
    try:
        for name, types in node.get_topic_names_and_types():
            if name.endswith('/image_raw_yuv') and any(tp.endswith('Image') for tp in types):
                cam_yuv_topic = name
                break
    except Exception:
        pass
    if cam_yuv_topic:
        times['camera_yuv'] = []

        def on_cam_yuv(_raw):
            times['camera_yuv'].append(time.monotonic())
        try:
            node.create_subscription(Image, cam_yuv_topic, on_cam_yuv, best, raw=True)
        except TypeError:
            cam_yuv_topic = None
    p('META camera_yuv_topic %s' % (cam_yuv_topic or 'none_found'))
    used = []

    def on_used(m):
        used.append((time.monotonic(), int(m.data)))
    node.create_subscription(Int32, '/aruco_detect/markers_used', on_used, 10)

    vision_topics = []
    try:
        for name, types in node.get_topic_names_and_types():
            if ('pose_cov' in name or 'vision_pose' in name) and name not in ('/parameter_events',):
                for tp in types:
                    if tp.endswith('PoseWithCovarianceStamped') and PoseWithCovarianceStamped is not None:
                        vision_topics.append((name, PoseWithCovarianceStamped))
                    elif tp.endswith('PoseStamped') and PoseStamped is not None:
                        vision_topics.append((name, PoseStamped))
    except Exception as e:
        p('META topic_discovery_failed %r' % (e,))
    for name, cls in vision_topics[:4]:
        times['vision'][name] = []
        node.create_subscription(cls, name, (lambda m, n=name: times['vision'][n].append(time.monotonic())), 10)
    p('META vision_topics %s' % (','.join(n for n, _ in vision_topics) or 'none_found'))

    wake_pub = None
    wake_count = [0]
    if wake:
        wake_pub = node.create_publisher(Bool, '/aruco_detect/wake', 10)

        def wake_tick():
            wake_pub.publish(Bool(data=True)); wake_count[0] += 1
        node.create_timer(1.0, wake_tick)
        p('META wake publishing_1Hz_to /aruco_detect/wake')
    else:
        p('META wake off')

    watch0 = scan_watch()
    p('META processes_start %s' % ' '.join('%s=%s' % (k, ','.join(map(str, v))) for k, v in sorted(watch0.items())))

    def read_cpu():
        with open('/proc/stat') as fh:
            return parse_proc_stat_cpu(fh.readline())

    def pid_ticks(pid):
        try:
            with open('/proc/%d/stat' % pid) as fh:
                return parse_pid_ticks(fh.read())
        except Exception:
            return None

    busy0, total0 = read_cpu()
    prev_pid = {}
    for k, pids in watch0.items():
        for pid in pids:
            prev_pid[pid] = (k, pid_ticks(pid))
    cpu_samples = []; temp_samples = []; thr_seen = set(); thr_last = None
    proc_cpu_samples = {}
    t_begin = time.monotonic(); t_end = t_begin + dur
    next_sample = t_begin + 5.0
    last_sample_t = t_begin
    last_busy, last_total = busy0, total0
    while time.monotonic() < t_end:
        rclpy.spin_once(node, timeout_sec=0.1)
        now = time.monotonic()
        if now >= next_sample:
            next_sample += 5.0
            b, t = read_cpu()
            cpu = 100.0 * (b - last_busy) / max(t - last_total, 1)
            last_busy, last_total = b, t
            cpu_samples.append(cpu)
            tc = read_temp_c()
            if tc is not None:
                temp_samples.append(tc)
            thr, flags = read_throttled()
            if thr is not None:
                thr_last = thr
                thr_seen.update(flags)
            dt = max(now - last_sample_t, 1e-6)
            last_sample_t = now
            cur = scan_watch()
            parts = []
            newprev = {}
            for k, pids in sorted(cur.items()):
                for pid in pids:
                    tk = pid_ticks(pid)
                    old = prev_pid.get(pid)
                    if tk is not None and old is not None and old[1] is not None:
                        pc = 100.0 * (tk - old[1]) / (CLK_TCK * dt)
                        parts.append('%s[%d]=%s' % (k, pid, fmt(pc, 1)))
                        proc_cpu_samples.setdefault(k, []).append(pc)
                    newprev[pid] = (k, tk)
            gone = sorted(set(k for (k, _t) in prev_pid.values()) - set(cur.keys()))
            for g in gone:
                p('EVENT t=%s process_gone %s' % (fmt(now - t_begin, 1), g))
            new_pids = [(k, pid) for k, pids in cur.items() for pid in pids if pid not in prev_pid]
            for k, pid in new_pids:
                p('EVENT t=%s process_new %s pid=%d (перезапуск или новый процесс)' % (fmt(now - t_begin, 1), k, pid))
            prev_pid = newprev
            p('SAMPLE t=%s cpu_total=%s temp=%s throttled=%s %s' % (fmt(now - t_begin, 0), fmt(cpu, 1), ('%.1f' % tc) if tc is not None else 'n/a',
                                                                   ('0x%x' % thr) if thr is not None else 'n/a', ' '.join(parts)))
    t_fin = time.monotonic()
    watch1 = scan_watch()

    # итоги
    def line(k, v):
        p('SUMMARY %s %s' % (k, v))
    line('label', label); line('mode', mode); line('wake', 'on (%d сообщений)' % wake_count[0] if wake else 'off')
    line('duration_s', fmt(t_fin - t_begin, 1))
    ms = rate_stats(times['markers'], t_begin, t_fin)
    line('markers_msgs', 'count=%d hz=%s gaps_over_0.5s=%d max_gap_s=%s start_delay_s=%s end_silence_s=%s top_gaps=%s' % (
        ms['count'], fmt(ms['hz'], 2), ms['gaps_over'], fmt(ms['max_gap'], 2), fmt(ms['start_delay'], 2), fmt(ms['end_silence'], 2),
        ','.join(fmt(g, 2) for g in ms['gaps_top']) or '-'))
    if nmarkers:
        with_m = sum(1 for n in nmarkers if n > 0)
        line('markers_in_frame', 'frames=%d with_marker=%d (%s%%) per_frame_mean=%s min=%d max=%d' % (
            len(nmarkers), with_m, fmt(100.0 * with_m / len(nmarkers), 1), fmt(sum(nmarkers) / len(nmarkers), 2), min(nmarkers), max(nmarkers)))
        line('marker_ids_seen', ' '.join('%d:%d' % (k, v) for k, v in sorted(ids_count.items())) or 'none')
    else:
        line('markers_in_frame', 'frames=0 (сообщений /aruco_detect/markers не было)')
    ls = latency_stats(lat)
    line('latency_ms_header_to_now', 'n=%d mean=%s p50=%s p95=%s max=%s' % (ls['n'], fmt(ls['mean'], 1), fmt(ls['p50'], 1), fmt(ls['p95'], 1), fmt(ls['max'], 1)))
    cs = rate_stats(times['camera'], t_begin, t_fin)
    line('camera_image_raw', 'count=%d hz=%s gaps_over_0.5s=%d max_gap_s=%s (подписка %s)' % (cs['count'], fmt(cs['hz'], 2), cs['gaps_over'], fmt(cs['max_gap'], 2), cam_mode))
    if 'camera_yuv' in times:
        ys = rate_stats(times['camera_yuv'], t_begin, t_fin)
        line('camera_image_raw_yuv', 'count=%d hz=%s gaps_over_0.5s=%d max_gap_s=%s (кадры до camera_fix, топик %s)' % (ys['count'], fmt(ys['hz'], 2), ys['gaps_over'], fmt(ys['max_gap'], 2), cam_yuv_topic))
    else:
        line('camera_image_raw_yuv', 'топик image_raw_yuv не найден')
    upos = [t for t, n in used if n >= 1]
    uz = sum(1 for _t, n in used if n == 0)
    if used:
        ug = gap_counts(upos, t_begin, t_fin)
        line('markers_used', 'msgs=%d with_ge1=%d (%s%%) with_0=%d hz_all=%s' % (len(used), len(upos), fmt(100.0 * len(upos) / len(used), 1), uz, fmt(len(used) / max(t_fin - t_begin, 1e-9), 2)))
        line('markers_used_ge1_pauses', 'между сообщениями со значением >= 1: over_0.4s=%d over_1.0s=%d over_1.5s=%d max_s=%s top=%s (так шлюз vpe_fix видит «метка свежая»: r2j держит 1,5 с, r2g раньше требовал последнее сообщение >= 1)' % (
            ug['over_0.4'], ug['over_1.0'], ug['over_1.5'], fmt(ug['max'], 2), ','.join(fmt(g, 2) for g in ug['top']) or '-'))
    else:
        line('markers_used', 'сообщений /aruco_detect/markers_used не было')
    if not times['vision']:
        line('vision_pose', 'топики не найдены')
    for name, ts in sorted(times['vision'].items()):
        vs = rate_stats(ts, t_begin, t_fin)
        line('vision_pose %s' % name, 'count=%d hz=%s gaps_over_0.5s=%d max_gap_s=%s' % (vs['count'], fmt(vs['hz'], 2), vs['gaps_over'], fmt(vs['max_gap'], 2)))
        vg = gap_counts(ts, t_begin, t_fin)
        line('vision_pose_pauses %s' % name, 'over_0.4s=%d over_1.0s=%d over_1.5s=%d max_s=%s top=%s (0,4 с: после такой паузы EKF2 теряет зрение и при возврате сбрасывает положение, T42 §1б)' % (
            vg['over_0.4'], vg['over_1.0'], vg['over_1.5'], fmt(vg['max'], 2), ','.join(fmt(g, 2) for g in vg['top']) or '-'))
        # частота НОВЫХ поз нельзя узнать по сообщениям: таймер vpe_fix 30 Гц повторяет последнюю позу
    line('vision_pose_note','vpe_fix в r2j на НЕвзведённом дроне пропускает позу в MAVROS (vpe_fix.py, функция _evaluate_gate, disarmed (warm-up), по коду), поэтому при видимой метке count больше 0; на взведённом не в OFFBOARD публикации нет (vpe_fix.py, функция _evaluate_gate)')
    if cpu_samples:
        line('cpu_total_pct', 'mean=%s max=%s samples=%d' % (fmt(sum(cpu_samples) / len(cpu_samples), 1), fmt(max(cpu_samples), 1), len(cpu_samples)))
    for k, v in sorted(proc_cpu_samples.items()):
        line('cpu_proc_pct %s' % k, 'mean=%s max=%s (100 = одно ядро)' % (fmt(sum(v) / len(v), 1), fmt(max(v), 1)))
    if temp_samples:
        line('temp_c', 'mean=%s max=%s' % (fmt(sum(temp_samples) / len(temp_samples), 1), fmt(max(temp_samples), 1)))
    line('throttled_last', ('0x%x' % thr_last) if thr_last is not None else 'n/a')
    line('throttled_flags_seen', ','.join(sorted(thr_seen)) or 'none')
    line('state_changes_count', len(events))
    line('processes_start', ' '.join('%s=%s' % (k, ','.join(map(str, v))) for k, v in sorted(watch0.items())) or 'none')
    line('processes_end', ' '.join('%s=%s' % (k, ','.join(map(str, v))) for k, v in sorted(watch1.items())) or 'none')
    same = all(sorted(watch0.get(k, [])) == sorted(watch1.get(k, [])) for k in set(list(watch0.keys()) + list(watch1.keys())))
    line('process_ids_changed', 'no' if same else 'YES (перезапуск процесса во время замера)')
    rclpy.shutdown()
    return 0


if __name__ == '__main__' and os.environ.get('BB_BENCH_MAIN', '1') == '1':
    sys.exit(main())
# BB_BENCH_PY_END
PY
PYRC=$?
echo "META python_exit $PYRC"
# журнал bumblebee за время замера (если разрешён доступ); только чтение
if [ "$PYRC" = "0" ]; then
  JALL=$(journalctl -u bumblebee --since "@$START" --no-pager -o cat 2>&1 | grep -E 'detection ACTIVE|detection IDLE|publish=|rejected pose|reseed|vpe_fix:|SIGSEGV|Traceback|Exception|died|exited|respawn|restart|process has died' | cut -c1-220)
  JN=$(printf '%s' "$JALL" | grep -c .)
  if [ -n "$JALL" ]; then printf '%s\n' "$JALL" | head -80 | while IFS= read -r l; do echo "J $l"; done; else echo "J (в журнале bumblebee за время замера нужных строк нет или доступ к журналу закрыт)"; fi
  [ "$JN" -gt 80 ] && echo "J_CUT shown=80 total=$JN"
  # r17a: joint rms from stack log, new bytes only, read only
  if [ -f "$LOGF" ] && [ "$LOG0" -ge 0 ]; then
    [ "$(stat -c %s "$LOGF" 2>/dev/null || echo 0)" -lt "$LOG0" ] && { echo "JR_NOTE log shrank, reading all"; LOG0=0; }
    JRALL=$(tail -c +$((LOG0 + 1)) "$LOGF" 2>/dev/null | grep -a -E 'joint (PnP )?rms median|map mismatch cleared' | cut -c1-220)
    JRN=$(printf '%s' "$JRALL" | grep -c .)
    [ "$JRN" -gt 0 ] && printf '%s\n' "$JRALL" | head -60 | sed 's/^/JR /'
    [ "$JRN" -gt 60 ] && echo "JR_CUT shown=60 total=$JRN"
    echo "JR_COUNT $JRN"
  else echo "JR_NOLOG"; fi
fi
echo "BB_BENCH_DONE rc=$PYRC"
exit "$PYRC"
