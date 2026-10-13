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

"""Turn one run_trial.sh output directory into summary.json + summary.md.

Trial criteria: RTF >= --min-rtf over the measurement window while every
camera renders, and all --flights smoke flights passed. Exit 0 = met, 1 = not.
"""

import argparse
import glob
import json
import os
import sys


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def kv_file(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep:
                    out[k] = v
    except OSError:
        pass
    return out


def fmt(v, nd=2, unit=""):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}{unit}"
    return f"{v}{unit}"


def cams_line(rtf):
    if not rtf or not rtf.get("cameras"):
        return "none"
    parts = []
    for topic, c in rtf["cameras"].items():
        sensor = topic.split("/sensor/")[-1].rsplit("/", 1)[0]
        parts.append(f"{sensor} {c['width']}x{c['height']}: {c['frames']} frames, "
                     f"{fmt(c.get('fps_sim'), 1)} fps sim / {fmt(c.get('fps_wall'), 1)} fps wall")
    return "; ".join(parts)


def proc_line(rtf):
    if not rtf:
        return "-"
    s = rtf.get("system") or {}
    cpu = s.get("cpu_pct") or {}
    mem = s.get("mem_used_mb") or {}
    parts = [f"system CPU {fmt(cpu.get('mean'), 0)} % mean / {fmt(cpu.get('max'), 0)} % max of "
             f"{rtf.get('ncpu')} CPUs, RAM used {fmt(mem.get('max'), 0)} of {fmt(s.get('mem_total_mb'), 0)} MB"]
    for name, p in (rtf.get("procs") or {}).items():
        c = p.get("cpu_pct_one_core") or {}
        r = p.get("rss_mb") or {}
        parts.append(f"{name} {fmt(c.get('mean'), 0)} % of one core (max {fmt(c.get('max'), 0)}), "
                     f"RSS {fmt(r.get('max'), 0)} MB")
    return "; ".join(parts)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dir", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--render", default="")
    p.add_argument("--flights", type=int, required=True)
    p.add_argument("--min-rtf", type=float, required=True)
    p.add_argument("--build-report")
    a = p.parse_args()

    d = a.dir
    rtf = load(os.path.join(d, "rtf.json"))
    rtf_fl = load(os.path.join(d, "rtf_flights.json"))
    fl = load(os.path.join(d, "flights.json"))
    times = load(os.path.join(d, "timings.json")) or {}
    exits = {k: times.pop(k) for k in list(times) if k.endswith("_exit")}
    build = kv_file(a.build_report) if a.build_report else {}
    ulogs = glob.glob(os.path.join(d, "px4_rootfs", "log", "**", "*.ulg"), recursive=True)

    rtf_val = rtf.get("rtf") if rtf else None
    rendering = bool(rtf and rtf.get("camera_rendering"))
    fsum = (fl or {}).get("summary") or {}
    checks = {
        "rtf": rtf_val is not None and rtf_val >= a.min_rtf,
        "camera_rendering": rendering,
        "flights": bool(fsum.get("all_ok")) and fsum.get("passed") == a.flights,
    }
    passed = all(checks.values())
    px4 = (fl or {}).get("px4") or {}

    summary = {
        "model": a.model, "render": a.render, "pass": passed, "checks": checks,
        "min_rtf": a.min_rtf, "rtf": rtf_val,
        "rtf_10s_min": ((rtf or {}).get("rtf_10s_windows") or {}).get("min"),
        "rtf_during_flights": (rtf_fl or {}).get("rtf"),
        "cameras": (rtf or {}).get("cameras"),
        "flights": fsum, "setup_error": (fl or {}).get("setup_error"),
        "px4": px4, "build": build, "timings_s": times, "exit_codes": exits, "ulog_files": len(ulogs),
        "ulog_mb": round(sum(os.path.getsize(u) for u in ulogs) / 1e6, 1),
        "resources_rtf_window": {k: (rtf or {}).get(k) for k in ("system", "procs", "ncpu")},
        "resources_flights": {k: (rtf_fl or {}).get(k) for k in ("system", "procs", "ncpu")},
    }
    with open(os.path.join(d, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")

    ok = {True: "PASS", False: "FAIL"}
    w = (rtf or {}).get("rtf_10s_windows") or {}
    lines = [
        f"## Simulator trial: {a.model} - {ok[passed]}",
        "",
        f"PX4 {px4.get('flight_sw_version', '?')} git {px4.get('git_hash_16', '?')}, "
        f"render {a.render}, {(rtf or {}).get('ncpu', '?')} CPUs",
        "",
        "| Check | Result | Verdict |",
        "|---|---|---|",
        f"| RTF, cameras rendering, {fmt((rtf or {}).get('window_wall_s'), 0)} s | "
        f"{fmt(rtf_val, 3)} (10 s windows: min {fmt(w.get('min'), 3)}, median {fmt(w.get('median'), 3)}) | "
        f"{ok[checks['rtf']]} (>= {a.min_rtf}) |",
        f"| Cameras | {cams_line(rtf)} | {ok[checks['camera_rendering']]} |",
        f"| Smoke flights | {fsum.get('passed', 0)}/{a.flights} passed"
        + (f", first failure #{fsum.get('first_failure')}" if fsum.get("first_failure") else "")
        + (f", setup error: {summary['setup_error']}".replace("|", "/") if summary["setup_error"] else "")
        + f" | {ok[checks['flights']]} |",
        f"| RTF during flights | {fmt(summary['rtf_during_flights'], 3)} | info |",
        "",
        f"- Resources (RTF window): {proc_line(rtf)}",
        f"- Resources (flights): {proc_line(rtf_fl)}",
        f"- Per flight: {fmt(fsum.get('wall_s_per_flight_mean'), 1)} s wall, "
        f"{fmt(fsum.get('sim_s_per_flight_mean'), 1)} s sim; max hover drift "
        f"{fmt(fsum.get('hover_xy_drift_max_m'), 2)} m",
        f"- Timings (s from start): {', '.join(f'{k} {v}' for k, v in times.items())}; "
        f"exit codes: {', '.join(f'{k} {v}' for k, v in exits.items()) or '-'}",
        f"- Build: {', '.join(f'{k}={v}' for k, v in build.items()) or 'n/a'}",
        f"- Logs: {len(ulogs)} ulog files ({summary['ulog_mb']} MB), px4.log, gz.log, flights.json, rtf*.json",
    ]
    if fl and fl.get("flights"):
        lines += ["", "| # | Result | Climb (sim s) | Hover drift max (m) | z err max (m) | Wall s | Error |",
                  "|---|---|---|---|---|---|---|"]
        for r in fl["flights"]:
            ph = r.get("phases", {})
            climb = None
            if "armed" in ph and "at_altitude" in ph:
                climb = ph["at_altitude"]["sim_s"] - ph["armed"]["sim_s"]
            h = r.get("hover", {})
            lines.append(f"| {r['flight']} | {'OK' if r['ok'] else 'FAIL'} | {fmt(climb, 1)} | "
                         f"{fmt(h.get('xy_drift_max_m'), 3)} | {fmt(h.get('z_err_max_m'), 3)} | "
                         f"{fmt(r.get('wall_s'), 1)} | {(r.get('error') or '').replace('|', '/')} |")
    md = "\n".join(lines) + "\n"
    with open(os.path.join(d, "summary.md"), "w") as f:
        f.write(md)
    print(md)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
