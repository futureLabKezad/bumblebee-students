#!/usr/bin/env python3
"""Observe the inherited gate; retain the reviewed opt-in parameter entry point."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
assert os.environ['ROS_DOMAIN_ID']=='83' and os.environ['ROS_LOCALHOST_ONLY']=='1'
candidate=Path(os.environ['BB_COMBINED_ROOT'])/'parameters'
sys.path.insert(0,str(candidate))
helper=Path('/work/sim/ros_stack/vpe_gate_diagnostic.py')
assert hashlib.sha256(helper.read_bytes()).hexdigest()=='3b0a0594ee8838bfaa602f3500025eaf5cff25c49f185f46a768c5953e726459'
spec=importlib.util.spec_from_file_location('gate_diagnostic',helper)
diagnostic=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic)
import vpe_fix
assert hashlib.sha256(Path(vpe_fix.__file__).read_bytes()).hexdigest()==diagnostic.TARGET_SHA256
vpe_fix.VpeFix._evaluate_gate=diagnostic.diagnostic_wrapper(vpe_fix.VpeFix._evaluate_gate)
from vpe_profile_optin import main
main()
