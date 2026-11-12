#!/usr/bin/env python3
"""Diagnostic prefix for the exact frozen VPE in isolated localhost SITL.

python vpe_gate_diagnostic.py /work/ws_package1b/install/bumblebee/lib/bumblebee/vpe_fix.py --ros-args ...
No policy, timer, executor, command client or return tuple is replaced.
"""
import functools
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import time

TARGET = '/work/ws_package1b/install/bumblebee/lib/bumblebee/vpe_fix.py'
TARGET_SHA256 = '3b8a93d4d08983694186766b0259fa6fa6b4167079c4078cf402a908d02e9725'  # c8-r2e-b (D2): r2e vpe_fix
HARDWARE_MARKERS = ('/etc/bumblebee', '/etc/bumblebee_version', '/dev/px4')


def validate_target(arguments, environment=None, hardware_markers=HARDWARE_MARKERS):
    environment = os.environ if environment is None else environment
    if environment.get('ROS_DOMAIN_ID') != '83' or environment.get('ROS_LOCALHOST_ONLY') != '1':
        raise RuntimeError('VPE diagnostic requires localhost SITL ROS_DOMAIN_ID=83')
    if any(Path(marker).exists() for marker in hardware_markers):
        raise RuntimeError('VPE diagnostic refuses Bumblebee hardware markers')
    if len(arguments) < 2 or arguments[1] != TARGET:
        raise RuntimeError('VPE diagnostic target must be the exact frozen installed SITL path')
    target = Path(TARGET)
    resolved = target.resolve(strict=True)
    if not resolved.is_relative_to(Path('/work/ws_package1b')):
        raise RuntimeError('VPE diagnostic target resolves outside isolated ws_package1b')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != TARGET_SHA256:
        raise RuntimeError('VPE diagnostic source SHA mismatch: '+digest)
    return target, resolved, digest


def snapshot(node):
    """Best-effort read of actual fields; never changes a policy input."""
    try:
        now = node.get_clock().now()
        def age(field):
            stamp = getattr(node, field, None)
            return None if stamp is None else (now-stamp).nanoseconds*1e-9
        return {
            'now_ros_ns': now.nanoseconds,
            'armed': bool(node.armed), 'in_offboard': bool(node.in_offboard),
            'markers_used': int(node.markers_used), 'yaw_locked': bool(node.yaw_locked),
            'marker_receipt_age_ros_s': age('markers_used_time'),
            'multi_marker_receipt_age_ros_s': age('markers_used_multi_time'),
            'last_good_age_ros_s': age('_last_vision_ok_time'),
            'pose_receipt_age_ros_s': age('last_pose_time'),
            # flight_trial_10: FCU-state knowledge of the P1+P1b candidate, read generically (names start with fcu/_fcu/
            # state_/_state); rclpy Time values are reported as ages. Read-only, never a policy input.
            'fcu_fields': {k: (age(k) if hasattr(v, 'nanoseconds') else v) for k, v in vars(node).items()
                           if k.lstrip('_').startswith(('fcu', 'state_')) and
                           (v is None or isinstance(v, (bool, int, float, str)) or hasattr(v, 'nanoseconds'))},
        }
    except BaseException as error:
        # Diagnostics must not prevent the original method from running.
        return {'snapshot_error': type(error).__name__}


def diagnostic_wrapper(original, source_sha256=TARGET_SHA256):
    sequence = itertools.count(1)

    @functools.wraps(original)
    def wrapped(node, *args, **kwargs):
        before = snapshot(node)
        try:
            # _apply_gate is the immediate caller; distinguish its timer,
            # armed-edge or constructor caller without adding source hooks.
            call_origin = sys._getframe(2).f_code.co_name
        except BaseException:
            call_origin = None
        begin = time.monotonic_ns()
        try:
            result = original(node, *args, **kwargs)  # exactly once; unchanged result/exception
        except BaseException as error:
            try:
                node.get_logger().info('VPE_GATE_DIAG '+json.dumps({
                    'sequence': next(sequence), 'source_sha256': source_sha256,
                    'call_origin': call_origin,
                    'call_begin_monotonic_ns': begin, 'call_end_monotonic_ns': time.monotonic_ns(),
                    'before': before, 'original_exception': type(error).__name__,
                }, sort_keys=True, allow_nan=False))
            except BaseException:
                pass
            raise
        end = time.monotonic_ns()
        try:
            after = snapshot(node)
            node.get_logger().info('VPE_GATE_DIAG '+json.dumps({
                'sequence': next(sequence), 'source_sha256': source_sha256,
                'call_origin': call_origin,
                'call_begin_monotonic_ns': begin, 'call_end_monotonic_ns': end,
                'diagnostic_system_wall_ns': time.time_ns(),
                'before': before, 'after': after,
                'result': {'publish': result[0], 'reason': result[1]},
            }, sort_keys=True, allow_nan=False))
        except BaseException:
            pass  # even failed logging/serialization cannot change the original tuple
        return result

    return wrapped


def main():
    original_argv = list(sys.argv)
    target, resolved, digest = validate_target(original_argv)
    target_argv = original_argv[1:]
    try:
        print('VPE_GATE_DIAG_START '+json.dumps({
            'target': str(target), 'resolved_target': str(resolved), 'source_sha256': digest,
            'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'wrapper_original_argv': original_argv, 'preserved_target_argv': target_argv,
            'ros_domain_id': 83, 'localhost_only': True,
            'policy_changed': False, 'additional_control_clients': False,
        }, sort_keys=True), flush=True)
    except BaseException:
        pass  # Startup diagnostic output is also best-effort.
    # Match normal script execution: rclpy.init consumes the original target
    # argv, and sibling imports resolve relative to the target script folder.
    sys.argv = target_argv
    sys.path[0] = str(target.parent)
    spec = importlib.util.spec_from_file_location('bbsim_frozen_vpe_diagnostic_target', target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    original = module.VpeFix._evaluate_gate
    module.VpeFix._evaluate_gate = diagnostic_wrapper(original, digest)
    module.main()  # original init, Node, executor, clients, shutdown and exception behavior


if __name__ == '__main__':
    main()
