#!/usr/bin/env python3
"""Read-only legacy MAVROS config conversion for the isolated freshness candidate.

Keep the container's default name, rename only the param plugin for unchanged
VPE/SDK clients, and never merge local-position output into a vision input.
"""
import argparse
import copy
import tempfile

MAVROS_ARGUMENTS = ['--ros-args', '-r', 'param:__node:=mavros']
MAVROS_REMAPPINGS = [
    ('/mavros/local_position/pose', '/mavros/mavros/pose'),
    ('/mavros/local_position/velocity_body', '/mavros/mavros/velocity_body'),
    ('/mavros/local_position/velocity_local', '/mavros/mavros/velocity_local'),
    ('/mavros/imu/data', '/mavros/mavros/data'),
    ('/mavros/cmd/arming', '/mavros/mavros/arming'),
    ('/mavros/rc/in', '/mavros/mavros/in'),
    ('/mavros/vision_pose/pose_cov', '/mavros/mavros/pose_cov'),
]
TF_KEYS = {'tf.send', 'tf.frame_id', 'tf.child_frame_id', 'use_sim_time'}


def scoped_config(document, use_sim_time=None, fcu_url=None, tgt_system=None):
    """Preserve supplied values and reject ambiguous node-specific overrides."""
    if not isinstance(document, dict) or not document:
        raise ValueError('MAVROS YAML must be a nonempty node mapping')
    for key, value in document.items():
        if not isinstance(value, dict) or set(value) != {'ros__parameters'} or not isinstance(value['ros__parameters'], dict):
            raise ValueError('Unexpected MAVROS section: '+str(key))
    if 'mavros' not in document or 'mavros/mavros' not in document:
        raise ValueError('Expected legacy mavros and mavros/mavros sections')
    shared = document['mavros']['ros__parameters']
    legacy = document['mavros/mavros']['ros__parameters']
    if not shared or not isinstance(shared.get('plugin_allowlist'), list):
        raise ValueError('Expected explicit existing MAVROS plugin_allowlist')
    if set(legacy)-TF_KEYS:
        raise ValueError('Ambiguous legacy plugin parameters: '+str(sorted(set(legacy)-TF_KEYS)))
    result = copy.deepcopy(document)
    container = result.setdefault('mavros_node', {'ros__parameters': {}})['ros__parameters']
    for key, value in shared.items():
        if key in container and container[key] != value:
            raise ValueError('Conflicting mavros_node parameter: '+key)
        container[key] = copy.deepcopy(value)
    local = result.setdefault('mavros/local_position', {'ros__parameters': {}})['ros__parameters']
    for key, value in legacy.items():
        if key in local and local[key] != value:
            raise ValueError('Conflicting local_position parameter: '+key)
        local[key] = copy.deepcopy(value)
    # Keeping the legacy section configures the renamed param plugin. Every
    # other explicit plugin section is preserved; conflicts fail at startup.
    if use_sim_time is not None:
        for section in result.values():
            params = section['ros__parameters']
            if 'use_sim_time' in params and params['use_sim_time'] != use_sim_time:
                raise ValueError('Conflicting use_sim_time value')
            params['use_sim_time'] = bool(use_sim_time)
        result.setdefault('/**', {'ros__parameters': {}})['ros__parameters']['use_sim_time'] = bool(use_sim_time)
    if fcu_url:
        for name in ('mavros', 'mavros_node'):
            result[name]['ros__parameters']['fcu_url'] = fcu_url
    if tgt_system is not None:
        for name in ('mavros', 'mavros_node'):
            result[name]['ros__parameters']['tgt_system'] = int(tgt_system)
    return result


def write_scoped_config(source, destination=None, **kwargs):
    import yaml
    with open(source, encoding='utf-8') as stream:
        result = scoped_config(yaml.safe_load(stream), **kwargs)
    if destination is None:
        with tempfile.NamedTemporaryFile(prefix='bumblebee_mavros_scoped_', suffix='.yaml', delete=False) as stream:
            destination = stream.name
    with open(destination, 'w', encoding='utf-8') as stream:
        yaml.safe_dump(result, stream, sort_keys=False)
    return str(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--sim-time', action='store_true')
    args = parser.parse_args()
    print(write_scoped_config(args.source, args.out, use_sim_time=True if args.sim_time else None))


if __name__ == '__main__':
    main()
