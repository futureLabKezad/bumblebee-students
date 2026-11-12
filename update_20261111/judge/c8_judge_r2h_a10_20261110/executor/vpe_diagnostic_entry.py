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
helper=Path(__file__).with_name('vpe_gate_diagnostic_p1.py')  # flight_trial_22 (as flight_trial_10): P1 FCU-state fields
assert hashlib.sha256(helper.read_bytes()).hexdigest()=='220fccd755ac3c4fe29a8d5c052f8f5dad8c253d2cbccbfa1ba1fb49531736bb'  # A10: vpe_gate_diagnostic_p1.py with the r2h TARGET_SHA256
spec=importlib.util.spec_from_file_location('gate_diagnostic',helper)
diagnostic=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic)
import vpe_fix
assert hashlib.sha256(Path(vpe_fix.__file__).read_bytes()).hexdigest()==diagnostic.TARGET_SHA256
# A10 (T44, chat 1 variant B, 10.11.2026): NO freshness opt-in. vpe_fix publishes as on the drone (aruco.launch.py runs
# vpe_fix.py itself; the freshness mixin published only the newest pose and dropped the r2h B2 medoid). What stays:
# the gate diagnostic below (observation only, same result) and the profile opt-in class (parameter service only).
# vpe_profile_optin.main() re-imports vpe_fix.VpeFix -> NodeClass = parameters(VpeFix).
vpe_fix.VpeFix._evaluate_gate=diagnostic.diagnostic_wrapper(vpe_fix.VpeFix._evaluate_gate)
from vpe_profile_optin import main
main()
