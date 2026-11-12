#!/usr/bin/env python3
"""Use the already verified scoped routes; keep EKF output out of vision input."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys

if os.environ.get('ROS_DOMAIN_ID') != '83' or os.environ.get('ROS_LOCALHOST_ONLY') != '1':
    raise RuntimeError('Isolated local SITL required')
source = Path(os.environ['C8_PRODUCT_SRC'])/'launch/mavros_scoped_config.py'  # c8: product src parameter; same pinned SHA below
if hashlib.sha256(source.read_bytes()).hexdigest() != 'c4f578a0c9630b8ab375a97b04ccb1df352c2402a81e21fab48678f67ee3b5da':
    raise RuntimeError('Pinned MAVROS routing changed')
spec = importlib.util.spec_from_file_location('reviewed_mavros_routes', source)
routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routes)
legacy, scoped = map(Path, sys.argv[1:])
if not all(p.resolve().is_relative_to(Path('/work/sim/runs')) for p in (legacy, scoped)):
    raise RuntimeError('Run-owned configuration paths required')
routes.write_scoped_config(legacy, scoped, use_sim_time=True)
executable = os.environ['C8_MAVROS_INSTALL'].rstrip('/')+'/mavros/lib/mavros/mavros_node'  # flight_trial_12 / c8: MAVROS install parameter (pinned by run.sh)
arguments = [executable, *routes.MAVROS_ARGUMENTS, '--params-file', str(scoped)]
for source_topic, destination in routes.MAVROS_REMAPPINGS:
    arguments += ['-r', source_topic+':='+destination]
os.execv(executable, arguments)
