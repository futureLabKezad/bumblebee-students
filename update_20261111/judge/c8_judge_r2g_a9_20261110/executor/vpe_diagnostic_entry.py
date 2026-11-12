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
assert hashlib.sha256(helper.read_bytes()).hexdigest()=='66265ad9f87a2940bdd9537c3d78209a178f5fd241728b9bbe196d54d59c60f5'  # c8-r2e-b: vpe_gate_diagnostic_p1.py with the r2e TARGET_SHA256
spec=importlib.util.spec_from_file_location('gate_diagnostic',helper)
diagnostic=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic)
import vpe_fix
assert hashlib.sha256(Path(vpe_fix.__file__).read_bytes()).hexdigest()==diagnostic.TARGET_SHA256
# flight_trial_07 / combined_04 (handover §8 п.5): VPE freshness on the pinned CLEAN c33 VpeFix first (install() verifies
# the c33 file SHA, method bodies and constants), then the diagnostic wrapper on the resulting FreshVpe class.
# vpe_profile_optin.main() re-imports vpe_fix.VpeFix -> NodeClass = parameters(FreshVpe) (FreshBase order).
import vpe_freshness_optin
assert hashlib.sha256(Path(vpe_freshness_optin.__file__).read_bytes()).hexdigest()=='fddfa6ec0693683e1e032ee40e3b2829677613aed9653f496d6205d4206931c3'  # combined_c8_r2e
vpe_freshness_optin.install(vpe_fix,enabled=True)
vpe_fix.VpeFix._evaluate_gate=diagnostic.diagnostic_wrapper(vpe_fix.VpeFix._evaluate_gate)
from vpe_profile_optin import main
main()
