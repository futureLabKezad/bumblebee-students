"""Explicit opt-in timestamp policy for the pinned c33 VPE, no ROS imports.

Compose with the parameter factory without editing either module:
    FreshBase = make_node_class(VpeFix, enabled=True)
    Node = parameter_module.make_node_class(FreshBase)

Both factory orders are supported. Only pose receipt/publish paths are wrapped.
"""
from collections import Counter, deque
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import ast
import hashlib
import types
import threading

PIN_C33 = 'c33a52bf1b10bc064ca102bdc720ed03afaa08c691d9c5c34b1d7fadf859b8b9'
_EXPECTED_CONSTANTS = {
    '_POSE_TIMEOUT': 0.5, '_Z_FLOOR_GUARD': -0.30,
    '_Z_CEILING_GUARD': 4.0, '_Z_JUMP_MAX': 0.3,
    '_XY_JUMP_MAX': 0.15, '_MAX_VISION_SPEED': 1.5,
    '_QUALITY_MULTI_TIMEOUT': 1.0, '_QUALITY_SINGLE_TIMEOUT': 1.5,
    '_GATE_HYSTERESIS': 0.5, '_RESEED_CONSISTENT_N': 3,
    '_RESEED_WINDOW': 2.0, '_RESEED_XY_CONSIST': 0.30,
    '_RESEED_Z_CONSIST': 0.25, '_RESEED_FORCE_REJECTS': 15,
    '_POS_VARIANCE': 0.30 ** 2, '_POS_Z_VARIANCE': 0.30 ** 2,
    '_YAW_VARIANCE': 0.05 ** 2,
}
_UNCHANGED_METHODS = (
    'aruco_map_callback', '_maybe_reseed', '_candidates_consistent', '_medoid',
    'publish_timer', '_multi_marker_fresh', '_single_marker_fresh',
    '_vision_quality_ok', '_evaluate_gate', '_apply_gate', 'state_callback',
    'markers_callback', 'markers_used_callback', 'yaw_locked_callback', '_gate_tick',
)


class _MeasurementClock:
    def __init__(self, clock, point):
        self._clock, self._point = clock, point

    def now(self):
        return self._point

    def __getattr__(self, name):
        return getattr(self._clock, name)


class _NoFreshEmission(RuntimeError):
    pass


class _StampedPublisher:
    def __init__(self, owner, publisher):
        self._owner, self.wrapped = owner, publisher

    def publish(self, message):
        owner = self._owner
        with owner._freshness_lock:
            permit = owner._freshness_emission
            if permit is None:
                raise _NoFreshEmission('publisher called without freshness permit')
            pose, point = permit
            now = owner._freshness_real_now()
            if (not owner._freshness_observe_clock(now)
                    or owner.last_pose is not pose
                    or message.pose.pose is not pose
                    or not 0 <= now.nanoseconds - point.nanoseconds
                    <= owner._freshness_pose_timeout_ns):
                owner._freshness_note('expired_during_publish')
                raise _NoFreshEmission('measurement expired before publish')
            # The c33 timer creates a new message; preserve its frame/covariance
            # and pose, replace only its regenerated timestamp.
            message.header.stamp = point.to_msg()
            return self.wrapped.publish(message)

    def __getattr__(self, name):
        return getattr(self.wrapped, name)


class FreshnessMixin:
    """Use make_node_class to enable this mixin only after source validation."""
    def __init__(self, *args, **kwargs):
        if not getattr(type(self), '_freshness_pin_checked', False):
            raise RuntimeError('use the explicit pinned freshness factory')
        self._freshness_lock = threading.RLock()
        self._freshness_context = ContextVar('vpe_measurement_clock', default=None)
        self._freshness_emission = None
        self._freshness_sources = {}
        self._freshness_last_stamp_ns = None
        self._freshness_max_clock_ns = None
        self._freshness_clock_fault = False
        self._freshness_counts = Counter()
        self._freshness_events = deque(maxlen=64)
        super().__init__(*args, **kwargs)
        self.vpe_pub = _StampedPublisher(self, self.vpe_pub)

    def get_clock(self):
        clock = super().get_clock()
        point = self._freshness_context.get()
        return clock if point is None else _MeasurementClock(clock, point)

    def _freshness_real_now(self):
        return super().get_clock().now()

    def _freshness_note(self, reason, stamp_ns=None):
        self._freshness_counts[reason] += 1
        self._freshness_events.append({'reason': reason, 'stamp_ns': stamp_ns})

    def _freshness_observe_clock(self, now):
        value = now.nanoseconds
        if (self._freshness_max_clock_ns is not None
                and value < self._freshness_max_clock_ns):
            self._freshness_clock_fault = True
        if self._freshness_clock_fault:
            self._freshness_note('clock_rollback')
            return False
        self._freshness_max_clock_ns = value
        return True

    @staticmethod
    def _freshness_stamp_ns(message):
        try:
            stamp = message.header.stamp
            sec, nano = stamp.sec, stamp.nanosec
        except AttributeError:
            return None
        if (type(sec) is not int or type(nano) is not int
                or sec < 0 or not 0 <= nano < 1_000_000_000):
            return None
        value = sec * 1_000_000_000 + nano
        return value if value > 0 else None

    def _freshness_prune_sources(self):
        retained = {id(p) for _, p in self._reseed_candidates}
        if self.last_pose is not None:
            retained.add(id(self.last_pose))
        self._freshness_sources = {key: value for key, value
                                   in self._freshness_sources.items()
                                   if key in retained}

    def aruco_map_callback(self, message):
        with self._freshness_lock:
            now = self._freshness_real_now()
            if not self._freshness_observe_clock(now):
                return
            stamp_ns = self._freshness_stamp_ns(message)
            if stamp_ns is None:
                self._freshness_note('invalid_or_zero_stamp')
                return
            age = now.nanoseconds - stamp_ns
            if age < 0:
                self._freshness_note('future_stamp', stamp_ns)
                return
            if age > self._freshness_pose_timeout_ns:
                self._freshness_note('stale_stamp', stamp_ns)
                return
            if (self._freshness_last_stamp_ns is not None
                    and stamp_ns <= self._freshness_last_stamp_ns):
                self._freshness_note('duplicate_or_reordered_stamp', stamp_ns)
                return
            # Source-time validity is established BEFORE c33 can accumulate,
            # reject physically, or reseed. Even a physically rejected sample
            # advances stream order, preventing its later replay as new input.
            self._freshness_last_stamp_ns = stamp_ns
            point = type(now)(nanoseconds=stamp_ns, clock_type=now.clock_type)
            snapshot = deepcopy(message)
            candidate = snapshot.pose.pose
            self._freshness_sources[id(candidate)] = (candidate, point)
            token = self._freshness_context.set(point)
            try:
                # Every physical/quality threshold remains in the pinned c33
                # implementation. Its dt/window now use measurement time.
                return super().aruco_map_callback(snapshot)
            finally:
                self._freshness_context.reset(token)
                source = self._freshness_sources.get(id(self.last_pose))
                if source is not None and source[0] is self.last_pose:
                    # A medoid may be an EARLIER candidate. Never date it as
                    # the most recent rejected sample or callback receipt.
                    self.last_pose_time = source[1]
                self._freshness_prune_sources()
                self._freshness_note('source_time_validated', stamp_ns)

    def publish_timer(self):
        with self._freshness_lock:
            now = self._freshness_real_now()
            if not self._freshness_observe_clock(now):
                return
            source = self._freshness_sources.get(id(self.last_pose))
            if (source is None or source[0] is not self.last_pose
                    or self.last_pose_time is None
                    or source[1].nanoseconds != self.last_pose_time.nanoseconds):
                self._freshness_note('no_measurement_source')
                return
            age = now.nanoseconds - source[1].nanoseconds
            if not 0 <= age <= self._freshness_pose_timeout_ns:
                self._freshness_note('expired_measurement', source[1].nanoseconds)
                return
            self._freshness_emission = source
            try:
                # Real clock here: c33 still applies its original active gate,
                # timeout, covariance and publication count. The publisher
                # replaces only the outgoing stamp and rechecks expiry.
                return super().publish_timer()
            except _NoFreshEmission:
                return
            finally:
                self._freshness_emission = None

    def freshness_diagnostics(self):
        with self._freshness_lock:
            return {'counts': dict(self._freshness_counts),
                    'last_stream_stamp_ns': self._freshness_last_stamp_ns,
                    'clock_fault': self._freshness_clock_fault,
                    'retained_sources': len(self._freshness_sources),
                    'events': list(self._freshness_events)}


def _code_signature(code):
    constants = tuple(_code_signature(value) if isinstance(value, types.CodeType)
                      else value for value in code.co_consts)
    return (code.co_code, constants, code.co_names, code.co_varnames,
            code.co_freevars, code.co_cellvars, code.co_argcount,
            code.co_posonlyargcount, code.co_kwonlyargcount, code.co_flags)


def _check_methods(base, original, selected):
    tree = ast.parse(selected.read_bytes())
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == 'VpeFix')
    definitions = {node.name: node for node in cls.body
                   if isinstance(node, ast.FunctionDef)}
    for name in _UNCHANGED_METHODS:
        actual = getattr(base, name)
        if actual is not getattr(original, name):
            raise ValueError('vision/quality override is outside this candidate: ' + name)
        env = {}
        shell = ast.ClassDef(name='VpeFix', bases=[], keywords=[],
                             body=[definitions[name]], decorator_list=[],
                             type_params=[])
        ast.copy_location(shell, cls)
        exec(compile(ast.Module(body=[shell], type_ignores=[]),
                     str(selected), 'exec'), env)
        expected = getattr(env['VpeFix'], name)
        expected = getattr(expected, '__func__', expected)
        if (_code_signature(actual.__code__) != _code_signature(expected.__code__)
                or actual.__defaults__ != expected.__defaults__
                or actual.__kwdefaults__ != expected.__kwdefaults__):
            raise ValueError('loaded c33 method was modified: ' + name)


def make_node_class(base, *, enabled=False, source_path=None):
    """Explicit factory, compatible with parameter make_node_class(base).

    Reject an altered effective vision/quality method or altered c33 constants.
    Parameter lifecycle overrides may be inherited; this module never calls
    them except through the unmodified base initialization/state callbacks.
    """
    if enabled is not True:
        raise ValueError('freshness is opt-in: enabled=True is required')
    if issubclass(base, FreshnessMixin):
        raise ValueError('freshness already installed')
    original = next((cls for cls in base.__mro__
                     if 'aruco_map_callback' in cls.__dict__), None)
    if original is None:
        raise ValueError('no pinned VPE callback found')
    callback = original.__dict__['aruco_map_callback']
    location = Path(callback.__code__.co_filename).resolve()
    selected = location if source_path is None else Path(source_path).resolve()
    if selected != location or hashlib.sha256(selected.read_bytes()).hexdigest() != PIN_C33:
        raise ValueError('c33 VPE source PIN mismatch')
    _check_methods(base, original, selected)
    for name, expected in _EXPECTED_CONSTANTS.items():
        if callback.__globals__.get(name) != expected:
            raise ValueError('pinned VPE constant changed: ' + name)

    class FreshVpe(FreshnessMixin, base):
        _freshness_pin_checked = True
        _freshness_pose_timeout_ns = 500_000_000
    return FreshVpe


def install(module, *, enabled=False):
    """Replace an explicitly supplied imported module's class, not its file."""
    module.VpeFix = make_node_class(module.VpeFix, enabled=enabled)
    return module.VpeFix
