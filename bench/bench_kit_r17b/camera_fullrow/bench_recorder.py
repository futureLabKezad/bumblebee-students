#!/usr/bin/env python3
"""Read-only recorder for the camera full-row measurement (PC rehearsal and the real Pi; motors off).

Subscribes only (never publishes):
  --pose-topic     geometry_msgs/PoseWithCovarianceStamped (bench detector output): rate, latency = arrival - stamp
  --markers-topic  aruco_pose/MarkerArray (bench detector output): rate, frames with >= 1 marker, latency
  --image-topic    sensor_msgs/Image, RAW subscription (no Python deserialization): rate, latency from the CDR header
Samples every second: /proc/stat (per core), /proc/<pid>/stat of every process whose command line contains one of
--procs (name=substring), CPU temperature (/sys/class/thermal), 'vcgencmd get_throttled' and 'measure_clock arm'
when vcgencmd exists, MemAvailable.
Writes <out>/summary.json and <out>/samples.csv; refuses to overwrite an existing <out>.
Usage: python3 bench_recorder.py --out DIR --duration 120 --pose-topic /bench/aruco_map/pose \
         --markers-topic /bench/aruco_detect/markers --image-topic /main_camera/image_raw \
         --procs camfix=camera_fix.py aruco_bench=aruco_detect_bench aruco=lib/bumblebee/aruco_detect.py ...
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy, qos_profile_sensor_data

CLK_TCK = os.sysconf('SC_CLK_TCK')


def pct(v, p):
    if not v:
        return None
    s = sorted(v)
    return round(s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))], 2)


def cpu_times():
    out = {}
    with open('/proc/stat') as f:
        for ln in f:
            if ln.startswith('cpu'):
                p = ln.split()
                v = [int(x) for x in p[1:]]
                idle = v[3] + v[4]
                out[p[0]] = (sum(v[:8]), idle)
    return out


def find_pids(procs):
    found = {k: [] for k in procs}
    me = os.getpid()
    for d in os.listdir('/proc'):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            cmd = open('/proc/%s/cmdline' % d, 'rb').read().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        for k, sub in procs.items():
            if sub in cmd and 'bench_recorder.py' not in cmd:
                found[k].append(int(d))
    return found


def proc_cpu(pid):
    try:
        p = open('/proc/%d/stat' % pid).read().rsplit(')', 1)[1].split()
        rss_pages = int(p[21])
        return (int(p[11]) + int(p[12])) / CLK_TCK, rss_pages * os.sysconf('SC_PAGE_SIZE') / 1e6
    except (OSError, IndexError, ValueError):
        return None, None


def temp_c():
    try:
        return int(open('/sys/class/thermal/thermal_zone0/temp').read()) / 1000.0
    except (OSError, ValueError):
        return None


def vcgencmd(*args):
    if not shutil.which('vcgencmd'):
        return None
    try:
        return subprocess.run(['vcgencmd', *args], capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def mem_avail_mb():
    for ln in open('/proc/meminfo'):
        if ln.startswith('MemAvailable:'):
            return int(ln.split()[1]) / 1024.0
    return None


class Rec(Node):
    def __init__(self, a):
        super().__init__('camera_fullrow_bench_recorder')
        self.lat = {}
        self.cnt = {}
        self.nonempty = 0
        self.t0 = time.monotonic()
        rel = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE, history=QoSHistoryPolicy.KEEP_LAST, depth=10)
        self.xyz = []
        if a.pose_topic:
            from geometry_msgs.msg import PoseWithCovarianceStamped

            def pose(m):
                self._stamp('pose', m.header.stamp)
                p = m.pose.pose.position
                self.xyz.append((p.x, p.y, p.z))
            self.create_subscription(PoseWithCovarianceStamped, a.pose_topic, pose, rel)
        if a.markers_topic:
            from aruco_pose.msg import MarkerArray

            def mk(m):
                self._stamp('markers', m.header.stamp)
                if len(m.markers):
                    self.nonempty += 1
            self.create_subscription(MarkerArray, a.markers_topic, mk, rel)
        if a.image_topic:
            from sensor_msgs.msg import Image
            self.create_subscription(Image, a.image_topic, self._raw_image, qos_profile_sensor_data, raw=True)

    def _now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def _stamp(self, key, st):
        self.cnt[key] = self.cnt.get(key, 0) + 1
        self.lat.setdefault(key, []).append((self._now() - (st.sec + st.nanosec * 1e-9)) * 1e3)

    def _raw_image(self, data):
        sec, nsec = struct.unpack_from('<iI', data, 4)          # CDR: 4-byte encapsulation, then header.stamp
        self.cnt['image'] = self.cnt.get('image', 0) + 1
        self.lat.setdefault('image', []).append((self._now() - (sec + nsec * 1e-9)) * 1e3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--duration', type=float, default=120.0)
    ap.add_argument('--pose-topic', default='')
    ap.add_argument('--markers-topic', default='')
    ap.add_argument('--image-topic', default='')
    ap.add_argument('--procs', nargs='*', default=[])
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        print('STOP: %s exists (no overwrite)' % out)
        sys.exit(2)
    out.mkdir(parents=True)
    procs = dict(p.split('=', 1) for p in a.procs)
    rclpy.init()
    node = Rec(a)
    pids = find_pids(procs)
    th0 = vcgencmd('get_throttled')
    c0 = cpu_times()
    p0 = {k: [proc_cpu(p)[0] for p in v] for k, v in pids.items()}
    rows = []
    t_start = time.monotonic()
    t_next = t_start + 1.0
    prev = c0
    temps, clocks = [], []
    while time.monotonic() - t_start < a.duration:
        rclpy.spin_once(node, timeout_sec=0.05)
        if time.monotonic() >= t_next:
            t_next += 1.0
            c = cpu_times()
            busy = {k: round(100.0 * (1 - (c[k][1] - prev[k][1]) / max(1, c[k][0] - prev[k][0])), 1) for k in c}
            prev = c
            t = temp_c()
            temps.append(t)
            clk = vcgencmd('measure_clock', 'arm')
            if clk and '=' in clk:
                clocks.append(int(clk.split('=')[1]) / 1e6)
            rows.append(dict(t=round(time.monotonic() - t_start, 2), temp_c=t, arm_mhz=clocks[-1] if clk else None,
                             mem_avail_mb=round(mem_avail_mb(), 1), **{'busy_' + k: v for k, v in busy.items()}))
    dur = time.monotonic() - t_start
    c1 = cpu_times()
    th1 = vcgencmd('get_throttled')
    proc_res = {}
    for k, v in pids.items():
        tot, rss = 0.0, 0.0
        ok = 0
        for p, s0 in zip(v, p0[k]):
            s1, r = proc_cpu(p)
            if s0 is not None and s1 is not None:
                tot += s1 - s0
                rss += r
                ok += 1
        proc_res[k] = dict(pids=v, alive=ok, cpu_pct_of_one_core=round(100.0 * tot / dur, 1), rss_mb=round(rss, 1))
    ncores = len([k for k in c1 if k != 'cpu'])
    tot_busy = 100.0 * (1 - (c1['cpu'][1] - c0['cpu'][1]) / max(1, c1['cpu'][0] - c0['cpu'][0]))
    core_busy = {k: round(100.0 * (1 - (c1[k][1] - c0[k][1]) / max(1, c1[k][0] - c0[k][0])), 1) for k in c1 if k != 'cpu'}
    topics = {}
    for k in sorted(set(list(node.cnt) + ['pose', 'markers', 'image'])):
        L = node.lat.get(k, [])
        topics[k] = dict(count=node.cnt.get(k, 0), hz=round(node.cnt.get(k, 0) / dur, 2),
                         latency_ms_p50=pct(L, 50), latency_ms_p95=pct(L, 95), latency_ms_max=pct(L, 100))
    tv = [x for x in temps if x is not None]
    pose_stats = None
    if node.xyz:
        import statistics as st
        med = [st.median(c) for c in zip(*node.xyz)]
        dev_xy = [((x - med[0]) ** 2 + (y - med[1]) ** 2) ** 0.5 * 100 for x, y, z in node.xyz]
        dev_z = [abs(z - med[2]) * 100 for x, y, z in node.xyz]
        pose_stats = dict(n=len(node.xyz), median_xyz_m=[round(v, 4) for v in med],
                          xy_dev_from_median_cm_p50=pct(dev_xy, 50), xy_dev_cm_p95=pct(dev_xy, 95),
                          xy_dev_cm_max=pct(dev_xy, 100), z_dev_cm_p95=pct(dev_z, 95))
    summ = dict(pose_values=pose_stats,host=os.uname().nodename, duration_s=round(dur, 1), ncores=ncores,
                total_cpu_busy_pct=round(tot_busy, 1), core_busy_pct=core_busy,
                idle_pct_of_all_cores=round(100.0 - tot_busy, 1), processes=proc_res, topics=topics,
                markers_nonempty=node.nonempty, temp_c_start=tv[0] if tv else None, temp_c_max=max(tv) if tv else None,
                arm_mhz_min=min(clocks) if clocks else None, arm_mhz_max=max(clocks) if clocks else None,
                throttled_start=th0, throttled_end=th1, args=vars(a))
    (out / 'summary.json').write_text(json.dumps(summ, indent=1) + '\n')
    keys = sorted({k for r in rows for k in r})
    with open(out / 'samples.csv', 'w') as f:
        f.write(','.join(keys) + '\n')
        for r in rows:
            f.write(','.join('' if r.get(k) is None else str(r.get(k)) for k in keys) + '\n')
    print(json.dumps(dict(topics=topics, processes={k: v['cpu_pct_of_one_core'] for k, v in proc_res.items()},
                          total_cpu_busy_pct=summ['total_cpu_busy_pct'], temp_c_max=summ['temp_c_max'],
                          throttled_end=th1), indent=None))
    print('RECORDER ГОТОВО: %s' % out)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
