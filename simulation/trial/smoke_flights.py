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

"""Automated smoke flights against PX4 SITL - SIMULATOR ONLY.

Each flight, the same control path the drone uses (simple_offboard: offboard
position setpoints, then AUTO.LAND), over plain MAVLink with pymavlink:

  stream position setpoints at the current spot -> OFFBOARD -> arm ->
  climb to --alt m -> hover --hover s -> AUTO.LAND -> touchdown -> disarm

All waits are measured in PX4 (= simulation) time from the vehicle's own
messages, so a slow simulator only makes a flight take longer, it does not
fail it; a stalled simulator fails by a wall-clock guard.

Safety interlocks - the script refuses to arm unless BOTH hold:
  * the MAVLink endpoint is a UDP port on the loopback interface
    (udpin:127.0.0.1:<port>), never a network address, TCP port or serial;
  * the vehicle reports parameter SIM_GZ_EN = 1, which exists only in PX4
    SITL built with the Gazebo bridge (a real flight controller has no such
    parameter).

It sends GCS heartbeats: the stock SITL airframes set NAV_DLL_ACT=2, so PX4
refuses to arm without a ground-station link ("No connection to the ground
control station").

Exit code: 0 = every flight passed, 1 = at least one flight failed,
2 = setup error (no vehicle, not a simulator, wrong PX4 version).
"""

import argparse
import json
import math
import os
import struct
import sys
import threading
import time

os.environ.setdefault("MAVLINK20", "1")
from pymavlink import mavutil  # noqa: E402

M = mavutil.mavlink

# PX4 custom modes (px4_custom_mode.h): main mode in bits 16-23, sub mode in 24-31.
PX4_MAIN_AUTO = 4
PX4_MAIN_OFFBOARD = 6
PX4_SUB_AUTO_LAND = 6
MODE_NAMES = {(PX4_MAIN_OFFBOARD, 0): "OFFBOARD", (PX4_MAIN_AUTO, PX4_SUB_AUTO_LAND): "AUTO.LAND"}

# MAVLink ESTIMATOR_STATUS_FLAGS
EST_POS_HORIZ_REL = 8
EST_POS_VERT_ABS = 32
EST_CONST_POS_MODE = 128
PREARM_CHECK_BIT = 0x10000000   # MAV_SYS_STATUS_PREARM_CHECK

LANDED_ON_GROUND = 1      # MAV_LANDED_STATE_ON_GROUND
LANDED_IN_AIR = 2         # MAV_LANDED_STATE_IN_AIR
SAFETY_ARMED = 128        # MAV_MODE_FLAG_SAFETY_ARMED
RESULT_ACCEPTED = 0
RESULT_IN_PROGRESS = 5
RESULT_NAMES = {0: "ACCEPTED", 1: "TEMPORARILY_REJECTED", 2: "DENIED", 3: "UNSUPPORTED",
                4: "FAILED", 5: "IN_PROGRESS", 6: "CANCELLED"}

# type_mask for SET_POSITION_TARGET_LOCAL_NED: use x/y/z + yaw, ignore the rest
POS_YAW_MASK = (8 | 16 | 32) | (64 | 128 | 256) | 2048

SETPOINT_HZ = 20.0
SILENCE_S = 20.0          # wall s without any message from PX4 = simulator/PX4 gone
LOOPBACK = ("127.0.0.1", "localhost", "::1")


class FlightError(Exception):
    pass


class SimStalled(FlightError):
    """Simulation time stopped advancing - no point in flying on."""


class SetupError(Exception):
    pass


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--url", default="udpin:127.0.0.1:14540",
                   help="PX4 SITL offboard link (instance N: port 14540+N)")
    p.add_argument("--flights", type=int, default=10)
    p.add_argument("--alt", type=float, default=1.0, help="hover height above the start, m")
    p.add_argument("--hover", type=float, default=10.0, help="hover time, sim s")
    p.add_argument("--max-xy-drift", type=float, default=1.0,
                   help="fail a flight if it drifts further than this from the start while hovering, m")
    p.add_argument("--max-z-err", type=float, default=0.3,
                   help="fail a flight if the hover height error exceeds this, m")
    p.add_argument("--climb-timeout", type=float, default=30.0, help="sim s to reach the hover height")
    p.add_argument("--land-timeout", type=float, default=60.0, help="sim s to touch down")
    p.add_argument("--allow-const-pos", action="store_true",
                   help="DEMO ONLY: accept EKF constant-position mode on the ground (flow-only "
                        "estimators report it while the flow camera sees no motion); PX4's own "
                        "pre-arm and OFFBOARD checks still apply. Never use for verification runs.")
    p.add_argument("--ready-timeout", type=float, default=180.0,
                   help="sim s to wait for the vehicle to be ready before each flight")
    p.add_argument("--settle", type=float, default=3.0, help="sim s on the ground between flights")
    p.add_argument("--guard-rtf", type=float, default=0.1,
                   help="wall-clock guard: a wait of T sim s fails after T/guard_rtf+20 wall s")
    p.add_argument("--expect-commit", default="",
                   help="PX4 git commit the vehicle must report (AUTOPILOT_VERSION), first 16 hex digits used")
    p.add_argument("--out", required=True, help="results JSON")
    return p.parse_args()


def check_url(url):
    kind, _, rest = url.partition(":")
    host, _, port = rest.rpartition(":")
    if kind not in ("udpin", "udp") or host not in LOOPBACK or not port.isdigit():
        raise SetupError(f"refusing MAVLink endpoint {url!r}: only udpin:127.0.0.1:<port> "
                         "(PX4 SITL on this machine) is allowed")


class Vehicle:
    """MAVLink state of one PX4 SITL instance plus a 20 Hz setpoint/heartbeat sender."""

    def __init__(self, url, guard_rtf, log):
        self.log = log
        self.guard_rtf = guard_rtf
        self.m = mavutil.mavlink_connection(url, source_system=255, source_component=190,
                                            dialect="common")
        self.send_lock = threading.Lock()
        self.sys = None
        self.comp = 1
        self.sim_ms = 0
        self.wall0 = time.monotonic()
        self.last_rx = time.monotonic()
        self.armed = False
        self.custom_mode = 0
        self.landed = None
        self.pos = None          # (x, y, z, vx, vy, vz)
        self.pos_sim_ms = 0
        self.yaw = 0.0
        self.est_flags = None
        self.allow_const_pos = False
        self.prearm_ok = None
        self.sys_status_n = 0   # SYS_STATUS messages received (freshness of prearm_ok)
        self.acks = {}
        self.params = {}
        self.version = None
        self.statustext = []
        self.setpoint = None     # (x, y, z, yaw) or None
        self._run = True
        self._sender = threading.Thread(target=self._send_loop, daemon=True)

    # ------------------------------------------------------------ basics
    @property
    def sim_s(self):
        return self.sim_ms / 1000.0

    @property
    def main_mode(self):
        return (self.custom_mode >> 16) & 0xFF

    @property
    def sub_mode(self):
        return (self.custom_mode >> 24) & 0xFF

    def mode_name(self):
        return MODE_NAMES.get((self.main_mode, self.sub_mode), f"{self.main_mode}.{self.sub_mode}")

    def send(self, fn, *a):
        with self.send_lock:
            fn(*a)

    def _send_loop(self):
        period = 1.0 / SETPOINT_HZ
        next_hb = 0.0
        while self._run:
            now = time.monotonic()
            if now >= next_hb:
                self.send(self.m.mav.heartbeat_send, M.MAV_TYPE_GCS, M.MAV_AUTOPILOT_INVALID, 0, 0,
                          M.MAV_STATE_ACTIVE)
                next_hb = now + 1.0
            sp = self.setpoint
            if sp is not None and self.sys is not None:
                x, y, z, yaw = sp
                ms = int((now - self.wall0) * 1000) & 0xFFFFFFFF
                self.send(self.m.mav.set_position_target_local_ned_send, ms, self.sys, self.comp,
                          M.MAV_FRAME_LOCAL_NED, POS_YAW_MASK, x, y, z, 0, 0, 0, 0, 0, 0, yaw, 0)
            time.sleep(period)

    def close(self):
        self._run = False
        self.setpoint = None
        if self._sender.is_alive():
            self._sender.join(timeout=2)
        self.m.close()

    # ------------------------------------------------------------ receive
    def pump(self, timeout=0.05):
        """Process every pending message (wait up to `timeout` for the first)."""
        msg = self.m.recv_match(blocking=True, timeout=timeout)
        n = 0
        while msg is not None and n < 500:
            self._handle(msg)
            n += 1
            msg = self.m.recv_match(blocking=False)

    def _handle(self, msg):
        t = msg.get_type()
        if t == "BAD_DATA":
            return
        src = msg.get_srcSystem()
        if t == "HEARTBEAT":
            if msg.autopilot != M.MAV_AUTOPILOT_PX4 or msg.get_srcComponent() != 1:
                return
            if self.sys is None:
                self.sys = src
            if src != self.sys:
                return
            self.last_rx = time.monotonic()
            self.armed = bool(msg.base_mode & SAFETY_ARMED)
            self.custom_mode = msg.custom_mode
            return
        if self.sys is None or src != self.sys:
            return
        self.last_rx = time.monotonic()
        if hasattr(msg, "time_boot_ms") and t in ("LOCAL_POSITION_NED", "ATTITUDE", "SYSTEM_TIME"):
            self.sim_ms = max(self.sim_ms, msg.time_boot_ms)
        if t == "LOCAL_POSITION_NED":
            self.pos = (msg.x, msg.y, msg.z, msg.vx, msg.vy, msg.vz)
            self.pos_sim_ms = msg.time_boot_ms
        elif t == "ATTITUDE":
            self.yaw = msg.yaw
        elif t == "EXTENDED_SYS_STATE":
            self.landed = msg.landed_state
        elif t == "SYS_STATUS":
            # PX4 sets this health bit when all its pre-arm checks pass
            self.prearm_ok = bool(msg.onboard_control_sensors_health & PREARM_CHECK_BIT)
            self.sys_status_n += 1
        elif t == "ESTIMATOR_STATUS":
            self.est_flags = msg.flags
        elif t == "COMMAND_ACK":
            self.acks[msg.command] = msg.result
        elif t == "PARAM_VALUE":
            self.params[msg.param_id.rstrip("\x00")] = (msg.param_value, msg.param_type)
        elif t == "AUTOPILOT_VERSION":
            self.version = msg
        elif t == "STATUSTEXT":
            text = msg.text.rstrip("\x00") if isinstance(msg.text, str) else str(msg.text)
            self.statustext.append({"sim_s": round(self.sim_s, 2), "severity": msg.severity, "text": text})
            self.log(f"[PX4] {text}")

    def wait(self, cond, sim_timeout, what):
        """Pump until cond() is true; FlightError after sim_timeout (or the wall guard)."""
        t_sim, t_wall = self.sim_s, time.monotonic()
        wall_limit = sim_timeout / self.guard_rtf + 20.0
        while not cond():
            if self.sim_s - t_sim > sim_timeout:
                raise FlightError(f"timeout after {sim_timeout:.0f} s sim: {what}")
            if time.monotonic() - self.last_rx > SILENCE_S:
                raise SimStalled(f"no MAVLink from PX4 for {SILENCE_S:.0f} s wall: {what}")
            if time.monotonic() - t_wall > wall_limit:
                raise SimStalled(f"simulator stalled ({wall_limit:.0f} s wall, "
                                  f"{self.sim_s - t_sim:.1f} s sim): {what}")
            self.pump()

    def hold(self, sim_seconds):
        t0 = self.sim_s
        self.wait(lambda: self.sim_s - t0 >= sim_seconds, sim_seconds + 5, f"hold {sim_seconds} s")

    # ------------------------------------------------------------ commands
    def command(self, cmd, *params, sim_timeout=5.0, tries=3):
        p = list(params) + [0.0] * (7 - len(params))
        for attempt in range(tries):
            self.acks.pop(cmd, None)
            self.send(self.m.mav.command_long_send, self.sys, self.comp, cmd, attempt, *p)
            try:
                self.wait(lambda: self.acks.get(cmd, RESULT_IN_PROGRESS) != RESULT_IN_PROGRESS,
                          sim_timeout, f"COMMAND_ACK for {cmd}")
            except SimStalled:
                raise
            except FlightError:
                continue
            return self.acks[cmd]
        raise FlightError(f"no COMMAND_ACK for command {cmd} after {tries} tries")

    def set_interval(self, msg_id, hz):
        self.command(M.MAV_CMD_SET_MESSAGE_INTERVAL, msg_id, 1e6 / hz)

    def set_mode(self, main, sub=0):
        name = MODE_NAMES.get((main, sub), f"{main}.{sub}")
        res = self.command(M.MAV_CMD_DO_SET_MODE, M.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, main, sub)
        if res != RESULT_ACCEPTED:
            raise FlightError(f"mode {name} rejected: {RESULT_NAMES.get(res, res)} ({self.last_text()})")
        self.wait(lambda: self.main_mode == main and (sub == 0 or self.sub_mode == sub), 3.0,
                  f"heartbeat shows {name}")

    def arm(self, on=True):
        res = self.command(M.MAV_CMD_COMPONENT_ARM_DISARM, 1.0 if on else 0.0)
        if res != RESULT_ACCEPTED:
            raise FlightError(f"{'arm' if on else 'disarm'} rejected: {RESULT_NAMES.get(res, res)} "
                              f"({self.last_text()})")
        self.wait(lambda: self.armed == on, 3.0, "heartbeat shows " + ("armed" if on else "disarmed"))

    def last_text(self, n=3):
        return " ; ".join(s["text"] for s in self.statustext[-n:]) or "no STATUSTEXT"

    def read_param(self, name, sim_timeout=5.0):
        for _ in range(3):
            self.params.pop(name, None)
            self.send(self.m.mav.param_request_read_send, self.sys, self.comp, name.encode(), -1)
            try:
                self.wait(lambda: name in self.params, sim_timeout, f"PARAM_VALUE {name}")
                return self.params[name]
            except SimStalled:
                raise
            except FlightError:
                continue
        return None

    # ------------------------------------------------------------ state checks
    def estimator_ok(self):
        if self.est_flags is None:
            return None
        f = self.est_flags
        const_ok = self.allow_const_pos or not (f & EST_CONST_POS_MODE)
        return bool(f & EST_POS_HORIZ_REL) and bool(f & EST_POS_VERT_ABS) and const_ok

    def ready(self):
        # On the ground, before switching to OFFBOARD: landed, disarmed and a
        # fresh, valid local position. PX4's EKF often reports constant-position
        # mode here while it is fine to fly (flow sees no motion, GPS models before
        # the first fix), so that flag alone must not block a flight; it is still
        # required when PX4 does not send the pre-arm bit. The pre-arm bit itself
        # is checked later, in OFFBOARD (prearm_ok_now): PX4 evaluates it for the
        # CURRENT mode, and the boot mode Hold needs a global position, which a
        # vehicle without GPS never has.
        fresh = self.pos is not None and self.sim_ms - self.pos_sim_ms < 500
        if not (fresh and not self.armed and self.landed == LANDED_ON_GROUND):
            return False
        if self.prearm_ok is not None:
            return bool((self.est_flags or 0) & EST_POS_HORIZ_REL)
        return self.estimator_ok() is not False

    def prearm_in_offboard(self, n0):
        """PX4's own verdict (SYS_STATUS pre-arm bit) for OFFBOARD: true once two
        SYS_STATUS newer than counter n0 (taken after OFFBOARD was confirmed, so
        not a verdict for Hold or from a previous flight) carry the bit. Leaving
        OFFBOARD while waiting is an error, not "not ready yet"."""
        if self.main_mode != PX4_MAIN_OFFBOARD:
            raise FlightError(f"PX4 left OFFBOARD ({self.mode_name()}) before arming")
        return self.sys_status_n >= n0 + 2 and bool(self.prearm_ok)


def int_param(value, ptype):
    """PX4 sends INT32 params byte-wise inside the float field."""
    if ptype == M.MAV_PARAM_TYPE_INT32:
        return struct.unpack("<i", struct.pack("<f", value))[0]
    return value


def connect(args, log):
    v = Vehicle(args.url, args.guard_rtf, log)
    v.allow_const_pos = args.allow_const_pos
    v._sender.start()
    t0 = time.monotonic()
    while v.sys is None:
        if time.monotonic() - t0 > 120:
            raise SetupError(f"no PX4 heartbeat on {args.url} within 120 s")
        v.pump(0.2)
    log(f"PX4 system {v.sys} on {args.url}")

    # Interlock: PX4 SITL with the Gazebo bridge has SIM_GZ_EN; hardware does not.
    p = v.read_param("SIM_GZ_EN")
    if p is None or 1 not in (int_param(*p), p[0]):
        raise SetupError(f"vehicle does not report SIM_GZ_EN=1 (got {p}) - not PX4 SITL + Gazebo; "
                         "refusing to fly")

    v.command(M.MAV_CMD_REQUEST_MESSAGE, M.MAVLINK_MSG_ID_AUTOPILOT_VERSION)
    try:
        v.wait(lambda: v.version is not None, 5.0, "AUTOPILOT_VERSION")
    except FlightError as e:
        raise SetupError(str(e))
    sw = v.version.flight_sw_version
    # PX4 v1.16.1 reports only the first 10 hex digits of its git hash in both
    # middleware_custom_version and flight_custom_version (the rest reads as
    # zeros: SITL here and the real FMU-v6C both report 94cb201279000000), so
    # compare those 10 digits (40 bits, enough to tell commits apart).
    git16 = bytes(v.version.middleware_custom_version)[::-1].hex()
    git10 = bytes(v.version.flight_custom_version)[::-1].hex()[:10]
    info = {"system_id": v.sys,
            "flight_sw_version": f"{(sw >> 24) & 0xFF}.{(sw >> 16) & 0xFF}.{(sw >> 8) & 0xFF} "
                                 f"(type {sw & 0xFF})",
            "git_hash_16": git16, "flight_custom_git_10": git10,
            "sim_gz_en": int_param(*p)}
    if args.expect_commit:
        want = args.expect_commit.lower()
        if not (git16[:10] == want[:10] and git10[:10] == want[:10]):
            raise SetupError(f"PX4 reports git {git16} (flight_custom {git10}), expected {want[:16]}")
        info["commit_check"] = "match"
    log(f"PX4 {info['flight_sw_version']} git {info['git_hash_16']} - SITL interlock OK")

    for msg_id, hz in ((M.MAVLINK_MSG_ID_LOCAL_POSITION_NED, 30), (M.MAVLINK_MSG_ID_ATTITUDE, 20),
                       (M.MAVLINK_MSG_ID_EXTENDED_SYS_STATE, 5), (M.MAVLINK_MSG_ID_ESTIMATOR_STATUS, 2)):
        try:
            v.set_interval(msg_id, hz)
        except FlightError as e:
            log(f"note: message interval {msg_id}: {e}")
    return v, info


def recover(v, log):
    """Get the vehicle back on the ground and disarmed after a failed flight."""
    if not v.armed:
        v.setpoint = None
        return True
    try:
        if (v.main_mode, v.sub_mode) != (PX4_MAIN_AUTO, PX4_SUB_AUTO_LAND):
            v.set_mode(PX4_MAIN_AUTO, PX4_SUB_AUTO_LAND)
        v.setpoint = None
        v.wait(lambda: not v.armed, 90.0, "recovery: land and auto-disarm")
        return True
    except FlightError as e:
        log(f"recovery failed: {e}")
        return False


def fly(v, n, args, log):
    rec = {"flight": n, "ok": False, "error": None, "phases": {}}
    t_sim0, t_wall0 = v.sim_s, time.monotonic()

    def mark(name):
        rec["phases"][name] = {"sim_s": round(v.sim_s - t_sim0, 2),
                               "wall_s": round(time.monotonic() - t_wall0, 2)}

    try:
        v.wait(v.ready, args.ready_timeout,
               f"ready (landed, disarmed, local position valid; estimator flags {v.est_flags})")
        mark("ready")
        x0, y0, z0 = v.pos[:3]
        yaw0 = v.yaw
        rec["start"] = [round(x0, 3), round(y0, 3), round(z0, 3)]
        v.setpoint = (x0, y0, z0, yaw0)      # stream before OFFBOARD, as PX4 requires
        v.hold(1.0)

        for attempt in range(1, 4):
            try:
                v.set_mode(PX4_MAIN_OFFBOARD)
                break
            except SimStalled:
                raise
            except FlightError:
                if attempt == 3:
                    raise
                v.hold(2.0)
        mark("offboard")
        n0 = v.sys_status_n
        v.wait(lambda: v.prearm_in_offboard(n0), args.ready_timeout,
               "PX4 pre-arm checks pass in OFFBOARD")
        mark("prearm_ok")
        for attempt in range(1, 4):
            try:
                if v.main_mode != PX4_MAIN_OFFBOARD:
                    raise FlightError(f"PX4 left OFFBOARD ({v.mode_name()}) before arming")
                v.arm(True)
                break
            except SimStalled:
                raise
            except FlightError:
                if attempt == 3:
                    raise
                v.hold(2.0)
        mark("armed")

        zt = z0 - args.alt                     # NED: up is negative
        v.setpoint = (x0, y0, zt, yaw0)
        v.wait(lambda: abs(v.pos[2] - zt) < 0.10 and abs(v.pos[5]) < 0.2, args.climb_timeout,
               f"climb to {args.alt} m")
        mark("at_altitude")

        t_h = v.sim_s
        drift_max, zerr_max, zerr_sq, k = 0.0, 0.0, 0.0, 0
        in_air = False
        last_ms = -1
        while v.sim_s - t_h < args.hover:
            v.wait(lambda: v.pos_sim_ms != last_ms, 5.0, "position during hover")
            last_ms = v.pos_sim_ms
            if not v.armed or v.main_mode != PX4_MAIN_OFFBOARD:
                raise FlightError(f"left OFFBOARD during hover (mode {v.mode_name()}, armed {v.armed}; "
                                  f"{v.last_text()})")
            in_air = in_air or v.landed == LANDED_IN_AIR
            x, y, z = v.pos[:3]
            drift_max = max(drift_max, math.hypot(x - x0, y - y0))
            ze = z - zt
            zerr_max = max(zerr_max, abs(ze))
            zerr_sq += ze * ze
            k += 1
        rec["hover"] = {"sim_s": round(v.sim_s - t_h, 2), "samples": k,
                        "xy_drift_max_m": round(drift_max, 3), "z_err_max_m": round(zerr_max, 3),
                        "z_err_rms_m": round(math.sqrt(zerr_sq / k), 3) if k else None,
                        "land_detector_in_air": in_air}
        mark("hover_done")
        problems = []
        if drift_max > args.max_xy_drift:
            problems.append(f"hover drift {drift_max:.2f} m > {args.max_xy_drift} m")
        if zerr_max > args.max_z_err:
            problems.append(f"hover height error {zerr_max:.2f} m > {args.max_z_err} m")
        if not in_air:
            problems.append("land detector never reported IN_AIR while hovering")

        v.set_mode(PX4_MAIN_AUTO, PX4_SUB_AUTO_LAND)
        v.setpoint = None
        mark("land_mode")
        v.wait(lambda: v.landed == LANDED_ON_GROUND, args.land_timeout, "touchdown")
        mark("touchdown")
        try:
            v.wait(lambda: not v.armed, 10.0, "auto-disarm after landing")
            rec["disarm"] = "auto"
        except FlightError:
            v.arm(False)
            rec["disarm"] = "command"
        mark("disarmed")
        x, y, _ = v.pos[:3]
        rec["landing_offset_m"] = round(math.hypot(x - x0, y - y0), 3)
        if problems:
            raise FlightError("; ".join(problems))
        rec["ok"] = True
    except FlightError as e:
        rec["error"] = str(e)
        # "not_ready": PX4 never armed (not ready, or refused); "flight": after arming
        rec["failed_phase"] = "flight" if "armed" in rec["phases"] else "not_ready"
        rec["mode_at_error"] = v.mode_name()
        rec["armed_at_error"] = v.armed
        rec["sim_stalled"] = isinstance(e, SimStalled)
        rec["recovered"] = False if rec["sim_stalled"] else recover(v, log)
    finally:
        v.setpoint = None
    rec["sim_s"] = round(v.sim_s - t_sim0, 2)
    rec["wall_s"] = round(time.monotonic() - t_wall0, 2)
    return rec


def write_json(path, obj):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def main():
    args = parse_args()
    t_start = time.monotonic()

    def log(text):
        print(f"[flights {time.monotonic() - t_start:7.1f}s] {text}", flush=True)

    result = {"args": vars(args), "flights": [], "px4": None}
    try:
        check_url(args.url)
        v, info = connect(args, log)
    except (SetupError, FlightError) as e:
        log(f"SETUP ERROR: {e}")
        result["setup_error"] = str(e)
        write_json(args.out, result)
        return 2
    result["px4"] = info
    try:
        for n in range(1, args.flights + 1):
            log(f"flight {n}/{args.flights}")
            rec = fly(v, n, args, log)
            result["flights"].append(rec)
            log(f"flight {n}: {'OK' if rec['ok'] else 'FAILED - ' + rec['error']} "
                f"({rec['sim_s']} s sim, {rec['wall_s']} s wall)")
            write_json(args.out, result)
            if not rec["ok"] and not rec.get("recovered", True):
                log("simulator stalled or vehicle not recovered - stopping the series")
                break
            try:
                v.hold(args.settle)
            except FlightError as e:
                log(f"settle: {e}")
    finally:
        result["statustext"] = v.statustext[-300:]
        v.close()

    fl = result["flights"]
    ok = [f for f in fl if f["ok"]]
    hov = [f["hover"]["xy_drift_max_m"] for f in fl if "hover" in f]
    result["summary"] = {
        "requested": args.flights, "flown": len(fl), "passed": len(ok), "failed": len(fl) - len(ok),
        "failed_not_ready": sum(1 for f in fl if f.get("failed_phase") == "not_ready"),
        "all_ok": len(ok) == args.flights,
        "first_failure": next((f["flight"] for f in fl if not f["ok"]), None),
        "wall_s_per_flight_mean": round(sum(f["wall_s"] for f in fl) / len(fl), 1) if fl else None,
        "sim_s_per_flight_mean": round(sum(f["sim_s"] for f in fl) / len(fl), 1) if fl else None,
        "hover_xy_drift_max_m": max(hov) if hov else None,
        "wall_s_total": round(time.monotonic() - t_start, 1),
    }
    write_json(args.out, result)
    s = result["summary"]
    log(f"{s['passed']}/{s['requested']} flights passed")
    return 0 if s["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
