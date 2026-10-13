#!/usr/bin/env python3
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Measure Gazebo's real-time factor (RTF) while every camera is rendering.

A Gazebo camera renders only while somebody subscribes to its image topic
(gz-sim Sensors system skips rendering sensors without connections), so this
script subscribes to every camera image topic of the world and counts frames
- proof that rendering really happened during the measurement. At the same
time it samples system CPU/RAM and the CPU/RSS of the processes given with
--proc (Linux /proc).

RTF = (sim time advanced) / (real time elapsed), both from the world's own
/world/<world>/stats messages, over the whole window and over sliding 10 s
windows (worst case).

Runs for --duration seconds of wall time, or until SIGTERM/SIGINT when
--duration is 0 (background use during the flights). Exit code: 0 = pass (or
no criteria given), 1 = a criterion failed, 2 = could not measure.

Needs the Gazebo Python bindings from apt (python3-gz-transport13,
python3-gz-msgs10). Talks to the local Gazebo only (gz-transport; set
GZ_PARTITION/GZ_IP the same as for the gz server).
"""

import argparse
import json
import os
import re
import signal
import statistics
import sys
import threading
import time

try:
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image
    from gz.msgs10.world_stats_pb2 import WorldStatistics
except ImportError as exc:  # pragma: no cover - depends on the machine
    print(f"measure_rtf: Gazebo Python bindings missing ({exc}); "
          "install python3-gz-transport13 python3-gz-msgs10", file=sys.stderr)
    sys.exit(2)

WINDOW_S = 10.0          # sliding window for the worst-case RTF
CAMERA_TOPIC = r"^/world/{world}/model/.+/sensor/[^/]+/image$"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--world", default="default")
    p.add_argument("--duration", type=float, default=120.0,
                   help="wall seconds to measure; 0 = until SIGTERM/SIGINT")
    p.add_argument("--warmup", type=float, default=10.0,
                   help="wall seconds after the cameras are subscribed before the window starts")
    p.add_argument("--interval", type=float, default=1.0, help="sample period, wall seconds")
    p.add_argument("--wait", type=float, default=120.0,
                   help="wall seconds to wait for world stats and camera topics")
    p.add_argument("--require-camera", action="store_true",
                   help="fail unless at least one camera topic exists and every camera delivered frames")
    p.add_argument("--min-rtf", type=float, default=None, help="fail if the window RTF is below this")
    p.add_argument("--proc", action="append", default=[], metavar="NAME=PID",
                   help="process to sample (repeatable), e.g. px4=1234")
    p.add_argument("--label", default="", help="free text stored in the summary")
    p.add_argument("--out", required=True, help="summary JSON")
    p.add_argument("--samples", help="per-interval samples, JSON lines")
    return p.parse_args()


def stamp_s(t):
    return t.sec + t.nsec * 1e-9


# ----------------------------------------------------------------------------- /proc

CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def cpu_total_idle():
    """(total, idle) jiffies over all CPUs, or None off Linux."""
    try:
        with open("/proc/stat") as f:
            vals = [int(v) for v in f.readline().split()[1:9]]
    except OSError:
        return None
    idle = vals[3] + vals[4]          # idle + iowait
    return sum(vals), idle


def mem_mb():
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0])
        return info["MemTotal"] / 1024.0, (info["MemTotal"] - info["MemAvailable"]) / 1024.0
    except (OSError, KeyError, ValueError):
        return None, None


def proc_cpu_s(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
        fields = data[data.rfind(")") + 2:].split()
        return (int(fields[11]) + int(fields[12])) / CLK_TCK     # utime + stime
    except (OSError, IndexError, ValueError):
        return None


def proc_rss_mb(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except (OSError, ValueError):
        pass
    return None


def load1():
    try:
        with open("/proc/loadavg") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------------------- state

class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.stats = []        # (wall, sim_s, real_s, rtf_field)
        self.cams = {}         # topic -> dict

    def on_stats(self, msg):
        now = time.monotonic()
        with self.lock:
            self.stats.append((now, stamp_s(msg.sim_time), stamp_s(msg.real_time),
                               msg.real_time_factor))

    def camera_cb(self, topic):
        def cb(msg):
            now = time.monotonic()
            with self.lock:
                c = self.cams[topic]
                c["frames"].append((now, stamp_s(msg.header.stamp)))
                if not c["width"]:
                    c["width"], c["height"] = msg.width, msg.height
                    c["pixel_format"] = int(msg.pixel_format_type)
        return cb


def rtf_between(a, b):
    """RTF between two stats samples using Gazebo's own sim/real clocks."""
    d_real = b[2] - a[2]
    return (b[1] - a[1]) / d_real if d_real > 0 else None


def window_rtfs(samples):
    """RTF over every WINDOW_S-long stretch (by Gazebo real time)."""
    out = []
    j = 0
    for i, a in enumerate(samples):
        j = max(j, i)
        while j < len(samples) and samples[j][2] - a[2] < WINDOW_S:
            j += 1
        if j >= len(samples):
            break
        r = rtf_between(a, samples[j])
        if r is not None:
            out.append(r)
    return out


def percentile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[k]


def write_json(path, obj):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def main():
    args = parse_args()
    procs = {}
    for spec in args.proc:
        name, _, pid = spec.partition("=")
        if not pid.isdigit():
            sys.exit(f"--proc expects NAME=PID, got {spec!r}")
        procs[name] = int(pid)
    procs.setdefault("measure_rtf", os.getpid())   # this observer's own cost

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    rec = Recorder()
    node = Node()
    stats_topic = f"/world/{args.world}/stats"
    if not node.subscribe(WorldStatistics, stats_topic, rec.on_stats):
        print(f"measure_rtf: cannot subscribe to {stats_topic}", file=sys.stderr)
        return 2

    # Wait for the world, then for the camera topics (the vehicle is spawned
    # after the world starts, so its sensors appear a little later).
    t_wait = time.monotonic()
    cam_re = re.compile(CAMERA_TOPIC.format(world=re.escape(args.world)))
    topics = []
    while not stop.is_set() and time.monotonic() - t_wait < args.wait:
        topics = sorted(t for t in node.topic_list() if cam_re.match(t))
        with rec.lock:
            have_stats = bool(rec.stats)
        if have_stats and (topics or not args.require_camera):
            break
        time.sleep(0.5)
    with rec.lock:
        have_stats = bool(rec.stats)
    if not have_stats:
        print(f"measure_rtf: no {stats_topic} messages within {args.wait:.0f}s", file=sys.stderr)
        return 2
    if args.require_camera and not topics:
        print(f"measure_rtf: no camera image topics in world '{args.world}' within "
              f"{args.wait:.0f}s", file=sys.stderr)
        return 2
    if topics:
        time.sleep(2.0)    # sensors of one model are advertised together; catch them all
        topics = sorted(t for t in node.topic_list() if cam_re.match(t))
    for t in topics:
        rec.cams[t] = {"frames": [], "width": 0, "height": 0, "pixel_format": 0}
        if not node.subscribe(Image, t, rec.camera_cb(t)):
            print(f"measure_rtf: cannot subscribe to {t}", file=sys.stderr)
            return 2
    print(f"measure_rtf: world '{args.world}', cameras: {', '.join(topics) or 'none'}", flush=True)

    stop.wait(args.warmup)
    t_start = time.monotonic()
    ncpu = os.cpu_count() or 1
    mem_total, _ = mem_mb()
    samples_f = open(args.samples, "w") if args.samples else None

    prev_cpu = cpu_total_idle()
    prev_proc = {n: proc_cpu_s(p) for n, p in procs.items()}
    prev_wall = t_start
    with rec.lock:
        prev_stat = rec.stats[-1]
        prev_frames = {t: len(c["frames"]) for t, c in rec.cams.items()}
    series = {"sys_cpu_pct": [], "mem_used_mb": [], "load1": []}
    proc_series = {n: {"cpu_pct": [], "rss_mb": []} for n in procs}

    while not stop.is_set():
        if args.duration > 0:
            left = t_start + args.duration - time.monotonic()
            if left <= 0:
                break
            stop.wait(min(args.interval, left))
        else:
            stop.wait(args.interval)
        now = time.monotonic()
        dt = now - prev_wall
        if dt <= 0:
            continue
        sample = {"t": round(now - t_start, 3)}
        with rec.lock:
            last = rec.stats[-1]
            frames = {t: len(c["frames"]) for t, c in rec.cams.items()}
        sample["sim_s"] = round(last[1], 4)
        r = rtf_between(prev_stat, last)
        sample["rtf"] = round(r, 4) if r is not None else None
        sample["rtf_gz"] = round(last[3], 4)
        prev_stat = last
        cpu = cpu_total_idle()
        if cpu and prev_cpu and cpu[0] > prev_cpu[0]:
            pct = 100.0 * (1.0 - (cpu[1] - prev_cpu[1]) / (cpu[0] - prev_cpu[0]))
            sample["sys_cpu_pct"] = round(pct, 1)
            series["sys_cpu_pct"].append(pct)
        prev_cpu = cpu
        _, used = mem_mb()
        if used is not None:
            sample["mem_used_mb"] = round(used)
            series["mem_used_mb"].append(used)
        la = load1()
        if la is not None:
            sample["load1"] = la
            series["load1"].append(la)
        sample["procs"] = {}
        for n, pid in procs.items():
            c = proc_cpu_s(pid)
            rss = proc_rss_mb(pid)
            entry = {}
            if c is not None and prev_proc[n] is not None:
                entry["cpu_pct"] = round(100.0 * (c - prev_proc[n]) / dt, 1)   # 100 = one core
                proc_series[n]["cpu_pct"].append(entry["cpu_pct"])
            if rss is not None:
                entry["rss_mb"] = round(rss, 1)
                proc_series[n]["rss_mb"].append(rss)
            prev_proc[n] = c
            sample["procs"][n] = entry
        sample["frames"] = {t.split("/model/")[1]: frames[t] - prev_frames[t] for t in topics}
        prev_frames = frames
        prev_wall = now
        if samples_f:
            samples_f.write(json.dumps(sample) + "\n")
            samples_f.flush()
    t_end = time.monotonic()
    if samples_f:
        samples_f.close()

    # ------------------------------------------------------------------ summary
    with rec.lock:
        win = [s for s in rec.stats if t_start <= s[0] <= t_end]
        cams = {t: dict(c, frames=[f for f in c["frames"] if t_start <= f[0] <= t_end])
                for t, c in rec.cams.items()}
    try:
        from google.protobuf.internal import api_implementation
        pb_impl = api_implementation.Type()
    except Exception:  # noqa: BLE001 - informational only
        pb_impl = None
    summary = {
        "label": args.label, "world": args.world, "ncpu": ncpu, "protobuf_impl": pb_impl,
        "window_wall_s": round(t_end - t_start, 2),
        "warmup_s": args.warmup, "stats_samples": len(win),
    }
    reasons = []
    if len(win) >= 2:
        summary["sim_s"] = round(win[-1][1] - win[0][1], 3)
        summary["real_s"] = round(win[-1][2] - win[0][2], 3)
        summary["rtf"] = round(rtf_between(win[0], win[-1]), 4)
        d_wall = win[-1][0] - win[0][0]
        summary["rtf_vs_wall_clock"] = round((win[-1][1] - win[0][1]) / d_wall, 4) if d_wall > 0 else None
        w = window_rtfs(win)
        summary["rtf_10s_windows"] = {
            "count": len(w),
            "min": round(min(w), 4) if w else None,
            "p05": round(percentile(w, 0.05), 4) if w else None,
            "median": round(statistics.median(w), 4) if w else None,
            "max": round(max(w), 4) if w else None,
        }
    else:
        summary["rtf"] = None
        reasons.append("fewer than 2 world stats samples in the window")

    cam_out = {}
    for t, c in cams.items():
        fr = c["frames"]
        e = {"frames": len(fr), "width": c["width"], "height": c["height"],
             "pixel_format": c["pixel_format"]}
        if len(fr) >= 2:
            e["fps_wall"] = round((len(fr) - 1) / (fr[-1][0] - fr[0][0]), 2) if fr[-1][0] > fr[0][0] else None
            d_sim = fr[-1][1] - fr[0][1]
            e["fps_sim"] = round((len(fr) - 1) / d_sim, 2) if d_sim > 0 else None
        cam_out[t] = e
    summary["cameras"] = cam_out
    rendering = bool(cam_out) and all(e["frames"] > 0 for e in cam_out.values())
    summary["camera_rendering"] = rendering

    def stat(vals, nd=1):
        if not vals:
            return None
        return {"mean": round(statistics.fmean(vals), nd), "max": round(max(vals), nd),
                "p95": round(percentile(vals, 0.95), nd)}
    summary["system"] = {"cpu_pct": stat(series["sys_cpu_pct"]),
                         "mem_used_mb": stat(series["mem_used_mb"], 0),
                         "mem_total_mb": round(mem_total) if mem_total else None,
                         "load1": stat(series["load1"], 2)}
    summary["procs"] = {n: {"pid": procs[n], "cpu_pct_one_core": stat(v["cpu_pct"]),
                            "rss_mb": stat(v["rss_mb"], 0)} for n, v in proc_series.items()}

    if args.require_camera and not rendering:
        reasons.append("no camera frames in the window" if cam_out else "no camera topics")
    if args.min_rtf is not None:
        summary["min_rtf"] = args.min_rtf
        if summary.get("rtf") is None or summary["rtf"] < args.min_rtf:
            reasons.append(f"RTF {summary.get('rtf')} < {args.min_rtf}")
    summary["pass"] = not reasons
    summary["reasons"] = reasons
    write_json(args.out, summary)

    cams_txt = "; ".join(f"{t.split('/model/')[1]} {e['width']}x{e['height']} "
                         f"{e['frames']} frames {e.get('fps_wall')} fps wall / {e.get('fps_sim')} fps sim"
                         for t, e in cam_out.items()) or "none"
    print(f"measure_rtf: RTF {summary.get('rtf')} over {summary['window_wall_s']} s wall "
          f"(10 s windows min {summary.get('rtf_10s_windows', {}).get('min')}); cameras: {cams_txt}; "
          f"{'PASS' if summary['pass'] else 'FAIL: ' + ', '.join(reasons)}", flush=True)
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
