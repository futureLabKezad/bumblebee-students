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

"""
vpe_fix.py -- VPE publisher AND the sole PX4-parameter gate.

ROLES
=====
1. Publishes /mavros/mavros/pose_cov at 30 Hz from the latest ArUco map pose
   (with quality gating, soft fallback, and sanity guards).
2. Exposes /vpe_fix/set_param (bumblebee/srv/SetParam) -- the ONLY channel
   that writes PX4 parameters in this stack.

ARCHITECTURAL RULE
==================
No other process writes PX4 params. set_params.py and preflight.py are
read-only diagnostics. drone.set_param() in flight scripts publishes to
/vpe_fix/set_param (not /mavros/mavros/set). PX4 config set manually
through QGC / mavlink_shell is sacred -- the gate never clobbers it at
boot, and restores it on shutdown for any param it touched.

GATE BEHAVIOUR (rewritten 2026-06-05)
=====================================
The gate is honest, per-parameter. Original values are read from a cache
populated by /parameter_events (MAVROS 2.x exposes PX4 params as ROS2
parameters of node /mavros/mavros).

  - At startup: trigger ParamPull(force_pull=true), subscribe to
    /parameter_events, wait for cache to fill (>=800 params or 30 s).
  - On set_param:
      - if cache is not warm yet  -> reject with "cache warming up";
      - if param not in cache     -> reject "param '<n>' not in PX4 cache";
      - if cache value == request -> noop (no PX4 write, no journal);
      - else                      -> record (param_id -> original) in journal
                                     ONCE (first-write wins), then ParamSetV2.
  - Revert paths are point-precise (no MAV_CMD_PREFLIGHT_STORAGE reload):
      - on ARMED->DISARMED edge: ParamSetV2(original) for each non-persistent
        override; persistent overrides are left in place;
      - on TTL fire: ParamSetV2(original) for that one param;
      - on shutdown / explicit /vpe_fix/revert_all: every override.

Why this matters: the previous implementation used MAV_CMD_PREFLIGHT_STORAGE
param1=0 to reload PX4 RAM from EEPROM on every disarm. That assumed EEPROM
held the operator's pristine config -- but EEPROM can be polluted (PX4
firmware autosave behaviour, QGC "Save" clicks, old baseline writers). The
result was profile values leaking from auto-flight into subsequent manual
flights.

SAFETY
======
The gate refuses EKF2_EV_CTRL=0 while armed. Toggling EV_CTRL=0
mid-flight caused IMU-only dead-reckoning runaway on 2026-05-13.

VPE PUBLISH LOGIC (unchanged)
=============================
Vision flow is gated by whether vpe_fix publishes /mavros/mavros/pose_cov.
EKF2_EV_CTRL is not toggled in flight -- when the publish flag is False,
the 30 Hz publish_timer emits nothing and PX4 EKF coasts on baro+IMU until
fresh vision returns.

  Publish = True when:
    - Drone is DISARMED (pre-arm warm-up; quality ignored on the ground).
    - ARMED + OFFBOARD + (multi_marker_fresh OR single_marker_fresh).

  Publish = False when:
    - ARMED in non-OFFBOARD mode.
    - ARMED + OFFBOARD + vision bad. Baro is secondary altitude source.

OPERATOR NOTE
=============
EKF2_EV_CTRL must be set on the FCU itself (via QGC) to 11 (hpos+vpos+yaw)
or 15 (hpos+vpos+vel+yaw). If a flight script needs a guaranteed value,
call drone.set_param('EKF2_EV_CTRL', 11, persistent=True) once at start:
the gate reads PX4, writes only if it differs, and leaves it set.
"""

import threading
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import ParamSetV2, ParamPull
from rcl_interfaces.msg import ParameterValue, ParameterType, ParameterEvent
from aruco_pose.msg import MarkerArray
from std_msgs.msg import Int32, Bool
from std_srvs.srv import Trigger

from bumblebee.srv import SetParam


_POS_VARIANCE   = 0.30 ** 2
_POS_Z_VARIANCE = 0.30 ** 2
_YAW_VARIANCE   = 0.05 ** 2

_POSE_TIMEOUT   = 0.5

_SOFT_FALLBACK_TIMEOUT = 4.0
_SOFT_XY_INFLATE = 5.0
_SOFT_Z_INFLATE  = 10.0

_QUALITY_MULTI_TIMEOUT  = 1.0
_QUALITY_SINGLE_TIMEOUT = 1.5

_GATE_HYSTERESIS = 0.5

# Floor guard widened 2026-06-03 after camera recalibration shifted the
# PnP-derived z of the static "drone on the floor" setup from +0.075 m to
# about -0.10 m. Map origin / camera TF were not re-zeroed yet, so vision
# pose now sits a few centimetres below the old floor line. -0.30 still
# catches genuine ground-impact / EKF divergence pose but lets normal
# preflight Z through.
_Z_FLOOR_GUARD   = -0.30
_Z_CEILING_GUARD = 4.0
_Z_JUMP_MAX      = 0.3

_XY_JUMP_MAX     = 0.15
_MAX_VISION_SPEED = 1.5

# Reseed hardening (2026-06-10 drift fix): a reseed needs N recent rejected
# poses that mutually agree (an alternating IPPE mirror-flip can never produce
# them), or a forced escape hatch after FORCE_REJECTS consecutive rejects so
# the 2026-05-26 self-heal guarantee is preserved.
_RESEED_CONSISTENT_N  = 3
_RESEED_WINDOW        = 2.0   # s -- candidates older than this are ignored
_RESEED_XY_CONSIST    = 0.30  # m -- max pairwise XY spread between candidates
_RESEED_Z_CONSIST     = 0.25  # m -- max pairwise |dz| between candidates
_RESEED_FORCE_REJECTS = 15    # ~2.5 s at 6 Hz

_PTYPE_INT = 0
_PTYPE_DOUBLE = 1

# Cache warm-up policy: the gate refuses set_param until either CACHE_HOT_MIN
# params have been seen on /parameter_events, or CACHE_HOT_TIMEOUT seconds
# elapsed since startup. PX4 publishes ~1100 params; 800 is the "most are in"
# threshold. 30 s covers ParamPull latency on a cold MAVROS.
_CACHE_HOT_MIN = 800
_CACHE_HOT_TIMEOUT = 30.0
_CACHE_HOT_MIN_TIMEOUT = 200  # if timeout fires with at least this many params, still go hot

# Per-write ParamSetV2 timeout. MAVROS 2.x's set_parameter() can take a few
# seconds to confirm with PX4 over MAVLink; 3 s was too tight after MAVROS did
# an internal undeclare/redeclare cycle on the first SetParamV2.
_PARAM_SET_TIMEOUT = 6.0

# rcl_interfaces ParameterType constants used in ParameterValue.type
_RCL_PT_BOOL    = 1
_RCL_PT_INTEGER = 2
_RCL_PT_DOUBLE  = 3

_MAVROS_NODE = '/mavros/mavros'


class _Override:
    __slots__ = ('original', 'ptype', 'persistent', 'ttl_timer')

    def __init__(self, original, ptype, persistent, ttl_timer):
        self.original = original
        self.ptype = ptype
        self.persistent = persistent
        self.ttl_timer = ttl_timer


class VpeFix(Node):
    def __init__(self):
        super().__init__('vpe_fix')

        # ----- Callback groups -----
        # Service handlers can block on MAVROS client futures only if the
        # client callbacks live in a *different* group than the handler.
        # Otherwise the spinner thread holding the handler also owns the
        # future-resolution callback -> deadlock.
        self._cb_grp_handlers = MutuallyExclusiveCallbackGroup()
        self._cb_grp_clients  = ReentrantCallbackGroup()

        # ----- VPE publisher -----
        self.vpe_pub = self.create_publisher(
            PoseWithCovarianceStamped, '/mavros/mavros/pose_cov', 1)

        # ----- MAVROS param clients -----
        self.param_set_client = self.create_client(
            ParamSetV2, '/mavros/mavros/set',
            callback_group=self._cb_grp_clients)
        self.param_pull_client = self.create_client(
            ParamPull, '/mavros/mavros/pull',
            callback_group=self._cb_grp_clients)

        # ----- PX4 param cache (fed by /parameter_events) -----
        # name -> (rcl_type_int, value) where rcl_type_int is one of
        # _RCL_PT_INTEGER / _RCL_PT_DOUBLE (we ignore bool/string).
        self._px4_cache = {}
        self._cache_lock = threading.Lock()
        self._cache_hot = False
        self._cache_started_at = self.get_clock().now()

        events_qos = QoSProfile(depth=200, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(
            ParameterEvent, '/parameter_events',
            self._on_parameter_event, events_qos,
            callback_group=self._cb_grp_clients)

        # ----- Override journal -----
        self._overrides = {}
        self._overrides_lock = threading.Lock()

        # ----- VPE state -----
        self.last_pose = None
        self.last_cov = None
        self.last_pose_time = None
        self.visible_ids = []
        self.published = 0
        self.vpe_active = False
        self.soft_mode = False
        self.armed = False
        self.in_offboard = False
        self._last_soft_suppress_log = 0.0

        # Self-healing reject counter (z-jump self-lock incident 2026-05-26).
        self._consec_rejects = 0
        # Recent rejected poses considered for a hardened reseed.
        self._reseed_candidates = deque(maxlen=_RESEED_CONSISTENT_N)
        self._last_reseed_defer_log = 0.0

        self.markers_used = 0
        self.markers_used_time = None
        self.markers_used_multi_time = None
        self.yaw_locked = False

        self._last_vision_ok_time = None

        state_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(State, '/mavros/state', self.state_callback, state_qos)
        self.create_subscription(
            PoseWithCovarianceStamped, '/aruco_map/pose',
            self.aruco_map_callback, 1)
        self.create_subscription(
            MarkerArray, '/aruco_detect/markers',
            self.markers_callback, 1)
        self.create_subscription(
            Int32, '/aruco_detect/markers_used',
            self.markers_used_callback, 10)
        self.create_subscription(
            Bool, '/aruco_detect/yaw_locked',
            self.yaw_locked_callback, 10)
        self.create_timer(1.0 / 30.0, self.publish_timer)
        self.create_timer(1.0, self._gate_tick)

        # Cache warm-up: trigger ParamPull(force=true) once after MAVROS comes
        # up. Single-shot timer cancels itself the first time it fires.
        self._initial_pull_done = False
        self.create_timer(3.0, self._initial_pull_tick,
                          callback_group=self._cb_grp_clients)

        # Cache warm-up timeout: mark hot after _CACHE_HOT_TIMEOUT even if we
        # didn't see >=_CACHE_HOT_MIN params, as long as we got at least
        # _CACHE_HOT_MIN_TIMEOUT.
        self._warmup_timeout_done = False
        self.create_timer(_CACHE_HOT_TIMEOUT, self._warmup_timeout_tick,
                          callback_group=self._cb_grp_clients)

        # ----- Override services -----
        self.set_param_srv = self.create_service(
            SetParam, '/vpe_fix/set_param', self._handle_set_param,
            callback_group=self._cb_grp_handlers)
        self.revert_all_srv = self.create_service(
            Trigger, '/vpe_fix/revert_all', self._handle_revert_all,
            callback_group=self._cb_grp_handlers)

        self.get_logger().info(
            'vpe_fix ready: VPE gate=DISARMED|(OFFBOARD&vision_ok); '
            'PX4-param gate exposes /vpe_fix/set_param (per-param restore, '
            'no EEPROM reload)')

    # ==================================================================
    # PX4 param cache (fed by /parameter_events)
    # ==================================================================

    def _on_parameter_event(self, msg):
        # /parameter_events carries events from every node in the graph.
        # Filter for MAVROS's plugin container, which owns PX4 params.
        if msg.node != _MAVROS_NODE:
            return
        with self._cache_lock:
            for p in msg.new_parameters:
                v = self._pv_to_cache(p.value)
                if v is not None:
                    self._px4_cache[p.name] = v
            for p in msg.changed_parameters:
                v = self._pv_to_cache(p.value)
                if v is not None:
                    self._px4_cache[p.name] = v
            # NOTE: deleted_parameters intentionally ignored. MAVROS 2.x
            # publishes delete+add cycles around its own set_parameter calls
            # (and during ParamPull), which would race with our writes and
            # transiently empty the cache. PX4 params are never *really*
            # deleted in the operational sense; we only need to track latest
            # known values, so a stale value is preferable to "not in cache".
            n = len(self._px4_cache)
            if not self._cache_hot and n >= _CACHE_HOT_MIN:
                self._cache_hot = True
                self.get_logger().info(
                    'vpe_fix gate: cache HOT (%d params)' % n)

    @staticmethod
    def _pv_to_cache(pv):
        """Convert rcl_interfaces ParameterValue to (rcl_type, value)."""
        t = int(pv.type)
        if t == _RCL_PT_INTEGER:
            return (_RCL_PT_INTEGER, int(pv.integer_value))
        if t == _RCL_PT_DOUBLE:
            return (_RCL_PT_DOUBLE, float(pv.double_value))
        # PX4 params are int or double; ignore other types.
        return None

    def _initial_pull_tick(self):
        if self._initial_pull_done:
            return
        self._initial_pull_done = True
        if not self.param_pull_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn(
                'vpe_fix gate: ParamPull service unavailable, '
                'cache will fill from passive events only')
            return
        self.get_logger().info('vpe_fix gate: triggering initial ParamPull')
        ok = self._param_pull_blocking(timeout=10.0)
        with self._cache_lock:
            n = len(self._px4_cache)
        self.get_logger().info(
            'vpe_fix gate: initial ParamPull %s, cache=%d'
            % ('OK' if ok else 'FAILED', n))

    def _warmup_timeout_tick(self):
        if self._warmup_timeout_done:
            return
        self._warmup_timeout_done = True
        with self._cache_lock:
            n = len(self._px4_cache)
            if self._cache_hot:
                return
            if n >= _CACHE_HOT_MIN_TIMEOUT:
                self._cache_hot = True
                self.get_logger().warn(
                    'vpe_fix gate: cache HOT after timeout '
                    '(%d params, expected >=%d)' % (n, _CACHE_HOT_MIN))
            else:
                # Mark hot anyway; per-name lookups will fail with a useful
                # message instead of hanging forever.
                self._cache_hot = True
                self.get_logger().error(
                    'vpe_fix gate: cache warm-up degraded (%d params, '
                    'expected >=%d); per-param lookups may fail' % (n, _CACHE_HOT_MIN_TIMEOUT))

    def _update_cache_from_write(self, name, value, ptype):
        """After our own successful ParamSetV2, push the new value into the
        cache immediately so subsequent reads don't depend on /parameter_events
        round-trip (which sometimes drops or delays under MAVROS load)."""
        rcl_type = _RCL_PT_INTEGER if ptype == _PTYPE_INT else _RCL_PT_DOUBLE
        stored = int(round(value)) if ptype == _PTYPE_INT else float(value)
        with self._cache_lock:
            self._px4_cache[name] = (rcl_type, stored)

    # ==================================================================
    # PX4-param gate
    # ==================================================================

    def _handle_set_param(self, request, response):
        name = request.param_id
        value = float(request.value)
        ptype = int(request.ptype)
        ttl = float(request.ttl_sec)
        persistent = bool(request.persistent)

        # --- safety: never let EKF2_EV_CTRL=0 land in PX4 while armed ---
        if name == 'EKF2_EV_CTRL' and int(round(value)) == 0 and self.armed:
            response.success = False
            response.message = ('refused: EKF2_EV_CTRL=0 while armed is unsafe '
                                '(2026-05-13 incident)')
            response.original_value = float('nan')
            self.get_logger().warn('vpe_fix gate: %s' % response.message)
            return response

        if not self._cache_hot:
            response.success = False
            response.message = 'cache warming up'
            response.original_value = float('nan')
            return response

        with self._cache_lock:
            cache_entry = self._px4_cache.get(name)
        if cache_entry is None:
            response.success = False
            response.message = "param '%s' not in PX4 cache" % name
            response.original_value = float('nan')
            self.get_logger().warn('vpe_fix gate: %s' % response.message)
            return response

        _cur_type, cur_value = cache_entry

        # Skip-if-equal: PX4 already holds the requested value. No write, no
        # journal entry, no revert on disarm.
        if self._values_equal(cur_value, value, ptype):
            response.success = True
            response.message = 'noop: already %g' % cur_value
            response.original_value = float(cur_value)
            return response

        # First-write wins: only record original on the FIRST override of a
        # given param. Subsequent writes (e.g. profile A then profile B) keep
        # the same "golden" original so disarm restores all the way back.
        is_first_write = False
        with self._overrides_lock:
            entry = self._overrides.get(name)
            if entry is None:
                entry = _Override(
                    original=float(cur_value), ptype=ptype,
                    persistent=persistent, ttl_timer=None)
                self._overrides[name] = entry
                is_first_write = True
            else:
                entry.persistent = persistent
                if entry.ttl_timer is not None:
                    entry.ttl_timer.cancel()
                    entry.ttl_timer = None
            original = entry.original

        ok, msg = self._param_set_with_retry(name, value, ptype)
        if not ok:
            if is_first_write:
                with self._overrides_lock:
                    self._overrides.pop(name, None)
            response.success = False
            response.message = msg
            response.original_value = float('nan')
            return response

        self._update_cache_from_write(name, value, ptype)

        if ttl > 0 and not persistent:
            self._arm_ttl(name, ttl)

        response.success = True
        response.message = ('applied %s=%g%s'
                            % (name, value, ', persistent' if persistent else ''))
        response.original_value = float(original)
        self.get_logger().info(
            'vpe_fix gate: %s (orig=%g)' % (response.message, original))
        return response

    @staticmethod
    def _values_equal(a, b, ptype):
        if ptype == _PTYPE_INT:
            return int(round(a)) == int(round(b))
        return abs(float(a) - float(b)) < 1e-6

    def _handle_revert_all(self, request, response):
        with self._overrides_lock:
            count = len(self._overrides)
        if count == 0:
            response.success = True
            response.message = 'no overrides to revert'
            return response
        self._revert_all(reason='explicit_revert_all')
        response.success = True
        response.message = ('reverted %d override(s) point-precise' % count)
        return response

    def _param_set_with_retry(self, name, value, ptype):
        """Issue ParamSetV2 once; if it fails, retry once after a short pause.

        We deliberately do NOT force-pull between attempts: ParamPull floods
        /parameter_events for several seconds, which saturates the executor
        and causes the second ParamSetV2 future to never complete (its done
        callback can't get a thread). The thinner retry path is more reliable.
        """
        ok, msg = self._param_set_once(name, value, ptype, timeout=_PARAM_SET_TIMEOUT)
        if ok:
            return True, 'ok'
        self.get_logger().warn(
            'vpe_fix gate: set %s=%g failed (attempt 1, %s); retrying in 0.3 s'
            % (name, value, msg))
        # Short pause lets MAVROS's queue settle.
        threading.Event().wait(0.3)
        ok, msg = self._param_set_once(name, value, ptype, timeout=_PARAM_SET_TIMEOUT)
        if ok:
            return True, 'ok on retry'
        return False, msg

    def _param_set_once(self, name, value, ptype, timeout=_PARAM_SET_TIMEOUT):
        if not self.param_set_client.wait_for_service(timeout_sec=timeout):
            return False, 'service /mavros/mavros/set not available'
        pval = ParameterValue()
        if ptype == _PTYPE_INT:
            pval.type = ParameterType.PARAMETER_INTEGER
            pval.integer_value = int(round(value))
        else:
            pval.type = ParameterType.PARAMETER_DOUBLE
            pval.double_value = float(value)
        req = ParamSetV2.Request()
        req.param_id = name
        req.value = pval
        fut = self.param_set_client.call_async(req)
        evt = threading.Event()
        fut.add_done_callback(lambda _f: evt.set())
        if not evt.wait(timeout=timeout):
            # Future never resolved -- usually means MAVROS is busy or the
            # client callback group lost its thread to /parameter_events.
            return False, 'future timeout after %.1fs' % timeout
        try:
            res = fut.result()
        except Exception as e:
            return False, 'raised %s' % e
        if res is None:
            return False, 'future returned None'
        if not res.success:
            return False, 'MAVROS returned success=False'
        return True, 'ok'

    def _param_pull_blocking(self, timeout=3.0):
        if not self.param_pull_client.wait_for_service(timeout_sec=timeout):
            return False
        req = ParamPull.Request()
        req.force_pull = True
        fut = self.param_pull_client.call_async(req)
        evt = threading.Event()
        fut.add_done_callback(lambda _f: evt.set())
        return evt.wait(timeout=timeout)

    def _arm_ttl(self, name, ttl_sec):
        """Schedule a one-shot restore TTL_SEC seconds from now."""
        with self._overrides_lock:
            entry = self._overrides.get(name)
            if entry is None:
                return
            if entry.ttl_timer is not None:
                entry.ttl_timer.cancel()
            def _fire(name=name):
                self._restore_one(name, reason='ttl_expired')
            entry.ttl_timer = self.create_timer(ttl_sec, _fire)

    def _restore_one(self, name, reason='manual'):
        """Restore a single param to its captured original via ParamSetV2."""
        with self._overrides_lock:
            entry = self._overrides.pop(name, None)
        if entry is None:
            return
        if entry.ttl_timer is not None:
            try:
                entry.ttl_timer.cancel()
            except Exception:
                pass
        ok, msg = self._param_set_with_retry(name, entry.original, entry.ptype)
        if ok:
            self._update_cache_from_write(name, entry.original, entry.ptype)
            self.get_logger().info(
                'vpe_fix gate: restored %s=%g (%s)'
                % (name, entry.original, reason))
        else:
            self.get_logger().error(
                'vpe_fix gate: FAILED to restore %s=%g (%s): %s'
                % (name, entry.original, reason, msg))

    def _revert_all_non_persistent(self, reason):
        with self._overrides_lock:
            to_revert = sorted(
                n for n, e in self._overrides.items() if not e.persistent)
        if not to_revert:
            return
        self.get_logger().info(
            'vpe_fix gate: reverting %d non-persistent overrides (%s): %s'
            % (len(to_revert), reason, to_revert))
        for n in to_revert:
            self._restore_one(n, reason=reason)

    def _revert_all(self, reason):
        with self._overrides_lock:
            names = sorted(self._overrides.keys())
        if not names:
            return
        self.get_logger().info(
            'vpe_fix gate: reverting %d overrides (%s): %s'
            % (len(names), reason, names))
        for n in names:
            self._restore_one(n, reason=reason)

    # ==================================================================
    # VPE publish path (unchanged)
    # ==================================================================

    def _multi_marker_fresh(self):
        if self.markers_used_multi_time is None:
            return False
        age = (self.get_clock().now() - self.markers_used_multi_time).nanoseconds / 1e9
        return age <= _QUALITY_MULTI_TIMEOUT

    def _single_marker_fresh(self):
        if self.markers_used_time is None or not self.yaw_locked or self.markers_used < 1:
            return False
        age = (self.get_clock().now() - self.markers_used_time).nanoseconds / 1e9
        return age <= _QUALITY_SINGLE_TIMEOUT

    def _vision_quality_ok(self):
        return self._multi_marker_fresh() or self._single_marker_fresh()

    def _evaluate_gate(self):
        if not self.armed:
            return True, 'disarmed (warm-up)'
        if not self.in_offboard:
            return False, 'armed in manual (no publish)'
        if self._multi_marker_fresh() or self._single_marker_fresh():
            self._last_vision_ok_time = self.get_clock().now()
            return True, 'OFFBOARD + vision_ok'
        if self._last_vision_ok_time is not None:
            age = (self.get_clock().now() - self._last_vision_ok_time).nanoseconds / 1e9
            if age < _GATE_HYSTERESIS:
                return True, 'OFFBOARD + recent vision ok (coasting %.1fs)' % age
        return False, 'OFFBOARD + vision_bad (publish suspended)'

    def _apply_gate(self, force=False):
        publish, reason = self._evaluate_gate()
        if publish != self.vpe_active or force:
            self.vpe_active = publish
            self.get_logger().info(
                'vpe_fix: %s -> publish=%s' % (reason, publish))

    def state_callback(self, msg):
        was_armed = self.armed
        self.armed = bool(msg.armed)
        self.in_offboard = (msg.mode == 'OFFBOARD')
        if self.armed != was_armed:
            self._apply_gate()
            if was_armed and not self.armed:
                # ARMED -> DISARMED edge: point-precise restore of every
                # non-persistent override.
                self._revert_all_non_persistent(reason='disarmed')

    def _maybe_reseed(self, msg_pose, now, reason):
        """Soft-reject helper: count consecutive rejects and reseed last_pose
        if the gate appears self-locked (z-jump self-lock incident 2026-05-26).
        Always still drops the current frame; reseed only affects future
        comparisons. Hard altitude guards (floor/ceiling) must NOT call this.

        Reseed hardening (2026-06-10 drift fix): a single rejected pose is no
        longer accepted wholesale -- one IPPE mirror-flip frame used to become
        the 30 Hz republished baseline and snap the EKF. A reseed now requires
        _RESEED_CONSISTENT_N recent rejected poses that mutually agree; the
        medoid of them becomes the new baseline. The escape hatch after
        _RESEED_FORCE_REJECTS consecutive rejects keeps the self-heal
        guarantee: reseed always eventually happens."""
        self._consec_rejects += 1
        self._reseed_candidates.append((now, msg_pose))
        count_limit = 7 if self.armed else 5
        age_limit = 0.5 if self.armed else 1.0
        if self.last_pose_time is not None:
            age = (now - self.last_pose_time).nanoseconds / 1e9
        else:
            age = float('inf')
        if not (self._consec_rejects >= count_limit or age > age_limit):
            return
        cands = [(t, p) for (t, p) in self._reseed_candidates
                 if (now - t).nanoseconds / 1e9 <= _RESEED_WINDOW]
        consistent = (len(cands) >= _RESEED_CONSISTENT_N
                      and self._candidates_consistent(cands))
        forced = self._consec_rejects >= _RESEED_FORCE_REJECTS
        if not (consistent or forced):
            now_s = now.nanoseconds * 1e-9
            if now_s - self._last_reseed_defer_log >= 1.0:
                self._last_reseed_defer_log = now_s
                self.get_logger().warn(
                    'vpe_fix: reseed deferred (%s, %d/%d consistent candidates, age=%.2fs)'
                    % (reason, len(cands), _RESEED_CONSISTENT_N, age))
            return
        seed = self._medoid([p for _, p in cands]) if cands else msg_pose
        self.last_pose = seed
        self.last_pose_time = now
        self.last_cov = None
        self._consec_rejects = 0
        self._reseed_candidates.clear()
        self.get_logger().warn(
            'vpe_fix: gate RESEEDED (%s%s) age=%.2fs new_xyz=(%.3f,%.3f,%.3f)'
            % (reason, ' FORCED' if forced and not consistent else '', age,
               seed.position.x, seed.position.y, seed.position.z))

    @staticmethod
    def _candidates_consistent(cands):
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                p, q = cands[i][1], cands[j][1]
                dxy = ((p.position.x - q.position.x) ** 2 +
                       (p.position.y - q.position.y) ** 2) ** 0.5
                if dxy > _RESEED_XY_CONSIST:
                    return False
                if abs(p.position.z - q.position.z) > _RESEED_Z_CONSIST:
                    return False
        return True

    @staticmethod
    def _medoid(poses):
        """Pose minimizing the summed 3D distance to the other candidates."""
        best, best_cost = None, None
        for p in poses:
            cost = 0.0
            for q in poses:
                cost += ((p.position.x - q.position.x) ** 2 +
                         (p.position.y - q.position.y) ** 2 +
                         (p.position.z - q.position.z) ** 2) ** 0.5
            if best_cost is None or cost < best_cost:
                best, best_cost = p, cost
        return best

    def aruco_map_callback(self, msg):
        z = msg.pose.pose.position.z
        if z < _Z_FLOOR_GUARD or z > _Z_CEILING_GUARD:
            self.get_logger().warn(
                'vpe_fix: rejected pose z=%.3f (out of [%.2f, %.2f])'
                % (z, _Z_FLOOR_GUARD, _Z_CEILING_GUARD))
            return
        now = self.get_clock().now()
        if self.last_pose is not None:
            dz = abs(z - self.last_pose.position.z)
            if dz > _Z_JUMP_MAX:
                self.get_logger().warn(
                    'vpe_fix: rejected pose z-jump %.3f (>%.2f)' % (dz, _Z_JUMP_MAX))
                self._maybe_reseed(msg.pose.pose, now, 'z-jump')
                return
            dx = msg.pose.pose.position.x - self.last_pose.position.x
            dy = msg.pose.pose.position.y - self.last_pose.position.y
            horiz = (dx * dx + dy * dy) ** 0.5
            if horiz > _XY_JUMP_MAX:
                self.get_logger().warn(
                    'vpe_fix: rejected pose xy-jump %.3f (>%.2f)' % (horiz, _XY_JUMP_MAX))
                self._maybe_reseed(msg.pose.pose, now, 'xy-jump')
                return
            if self.last_pose_time is not None:
                dt = (now - self.last_pose_time).nanoseconds / 1e9
                if 0.0 < dt < 0.5:
                    speed = horiz / dt
                    if speed > _MAX_VISION_SPEED:
                        self.get_logger().warn(
                            'vpe_fix: rejected pose vel=%.2f m/s (>%.2f)' % (speed, _MAX_VISION_SPEED))
                        self._maybe_reseed(msg.pose.pose, now, 'vel')
                        return
        self.last_pose = msg.pose.pose
        self.last_pose_time = now
        self._consec_rejects = 0
        self._reseed_candidates.clear()
        if any(msg.pose.covariance):
            self.last_cov = list(msg.pose.covariance)
        else:
            self.last_cov = None

    def markers_callback(self, msg):
        self.visible_ids = [m.id for m in msg.markers]

    def markers_used_callback(self, msg):
        self.markers_used = int(msg.data)
        self.markers_used_time = self.get_clock().now()
        if self.markers_used >= 2:
            self.markers_used_multi_time = self.markers_used_time

    def yaw_locked_callback(self, msg):
        self.yaw_locked = bool(msg.data)

    def _gate_tick(self):
        self._apply_gate()

    def _log_soft_suppressed_ratelimited(self, age, armed):
        now = self.get_clock().now().nanoseconds * 1e-9
        last = getattr(self, '_last_soft_suppress_log', 0.0)
        if now - last >= 2.0:
            self._last_soft_suppress_log = now
            self.get_logger().info(
                'vpe_fix: soft-fallback SUPPRESSED (age=%.2fs, armed=%s)' % (age, armed))

    def publish_timer(self):
        if self.last_pose is None or not self.vpe_active:
            if self.soft_mode:
                self.soft_mode = False
                self.get_logger().info('vpe_fix: soft-fallback EXIT (gate closed)')
            return
        age = (self.get_clock().now() - self.last_pose_time).nanoseconds / 1e9

        if age <= _POSE_TIMEOUT:
            soft = False
        else:
            # Soft-fallback disabled (2026-05-27): EKF2 drift from inflated-cov last-known pose.
            # vpe_fix is now silent during vision dropouts; EKF2 coasts on baro+IMU.
            if self.soft_mode:
                self.soft_mode = False
                self.get_logger().info(
                    'vpe_fix: soft-fallback EXIT (age=%.2fs yaw_lock=%s)' %
                    (age, self.yaw_locked))
            self._log_soft_suppressed_ratelimited(age, self.armed)
            return

        if soft != self.soft_mode:
            self.soft_mode = soft
            if soft:
                self.get_logger().info(
                    'vpe_fix: soft-fallback ENTER (age=%.2fs, '
                    'cov XY=%.3f Z=%.3f)' % (
                        age,
                        _POS_VARIANCE * _SOFT_XY_INFLATE,
                        _POS_Z_VARIANCE * _SOFT_Z_INFLATE))
            else:
                self.get_logger().info('vpe_fix: soft-fallback EXIT (fresh pose)')

        out = PoseWithCovarianceStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = 'map'
        out.pose.pose = self.last_pose

        if self.last_cov is not None and not soft:
            out.pose.covariance = self.last_cov
        else:
            xy = _POS_VARIANCE * (_SOFT_XY_INFLATE if soft else 1.0)
            z  = _POS_Z_VARIANCE * (_SOFT_Z_INFLATE if soft else 1.0)
            cov = [0.0] * 36
            cov[0]  = xy
            cov[7]  = xy
            cov[14] = z
            cov[21] = 1e6
            cov[28] = 1e6
            cov[35] = _YAW_VARIANCE
            out.pose.covariance = cov

        self.vpe_pub.publish(out)
        self.published += 1
        if self.published % 90 == 1:
            self.get_logger().info(
                'vpe_fix: published %d | z=%.3f | markers=%s | soft=%s' % (
                    self.published, out.pose.pose.position.z,
                    self.visible_ids, soft))


def main():
    rclpy.init()
    node = VpeFix()
    # Multi-threaded executor so the gate service handler can block on
    # MAVROS service futures without deadlocking the spin thread.
    # 8 threads: handlers (1) + clients (reentrant, up to ~3 in flight) +
    # subscriptions (state, pose, markers, parameter_events) need their own
    # threads when MAVROS floods /parameter_events during ParamPull.
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node._revert_all(reason='shutdown')
        except Exception as e:
            node.get_logger().warn('vpe_fix: revert_all on shutdown failed: %s' % e)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
