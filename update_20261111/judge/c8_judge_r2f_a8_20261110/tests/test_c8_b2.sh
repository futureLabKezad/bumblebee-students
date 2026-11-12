#!/usr/bin/env bash
# T28 static tests (no Gazebo, no PX4, no node started). Run from anywhere: bash tests/test_c8_b.sh
# Writes nothing outside tests/out_<time>/ of this folder (no bytecode: PYTHONDONTWRITEBYTECODE=1).
set -uo pipefail
D=/work/c8_judge_r2f_a8_20261110
export PYTHONDONTWRITEBYTECODE=1
O=$D/tests/out_$(date +%H%M%S); mkdir -p "$O"
PASS=0; FAIL=0
D1_ALLOWED=''   # A5 (chat 1 09.11): setup changes none of the 4061 values
ok() { echo "PASS $1"; PASS=$((PASS+1)); }
bad() { echo "FAIL $1"; FAIL=$((FAIL+1)); }
t() { local name=$1; shift; if "$@" >"$O/$name.log" 2>&1; then ok "$name"; else bad "$name (see $O/$name.log)"; fi; }

# 1. syntax
t bash_syntax bash -c "bash -n $D/executor/run.sh && bash -n $D/executor/run_sim.snapshot.sh && bash -n $D/launcher/host_run_wsl_c8_r2e_b.sh"
t py_syntax python3 -B -c "
import ast,glob
for f in glob.glob('$D/executor/*.py')+glob.glob('$D/candidate/*/*.py')+['$D/verify_flight_c8.py','$D/legacy/verify_package1b_gates_c8.py']:
    ast.parse(open(f).read(),f)
print('ok')"

# 2. launcher pins pre-check exactly as the launcher runs it (heredoc extracted), default target set
t launcher_pins_ok bash -c "
sed -n '/^  python3 -I - \"\$COMBINED\"/,/^PY\$/p' $D/launcher/host_run_wsl_c8_r2e_b.sh | sed '1d;\$d' > $O/precheck.py
env C8_AF_FILE=/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4070_gz_bumblebee_final_4061_bat0_sdlog1 \
  C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf \
  C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
  C8_DRONE_PY=/work/fixed_image_r2f_20261110/src/bumblebee/examples/drone.py \
  python3 -I $O/precheck.py $D/candidate $D/pins/frozen_inputs_c8_r2f_a8_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
# control: the old v31 pins are not accepted by this launcher
t launcher_pins_refuses_old bash -c "! env C8_AF_FILE=/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4061_gz_bumblebee_candidate_4060_disarm_rcl_obl \
  C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
  C8_DRONE_PY=/work/fixed_image_r2f_20261110/src/bumblebee/examples/drone.py \
  python3 -I $O/precheck.py /work/parallel_work/20261015/integration/combined_13 /work/c8_executor_20261109/pins/frozen_inputs_c8_r2e_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"

# 3. profile: sitl_setup manifest 13, candidate closure 18 == judge c8_4061 names
t profile_13_closure_18 python3 -B -I -c "
import sys,importlib.util
def load(n,p):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ss=load('ss','$D/executor/sitl_setup.py'); man=ss.profile_manifest(); assert man['count']==13 and 'COM_SPOOLUP_TIME' not in man['names'], man['count']
cl=load('cl','$D/candidate/parameters/sitl_profile_closure_candidate.py'); names=set(cl.closure_names(cl.profile_values())); assert len(names)==18, len(names)
vj=load('vj','$D/verify_flight_c8.py'); assert names==set(vj.IDENTITIES['c8_4061']['names']), names^set(vj.IDENTITIES['c8_4061']['names'])
assert set(vj.IDENTITIES['rel3_4030']['names'])-names=={'COM_SPOOLUP_TIME'}
# the run copy of flight_profile.py is the candidate copy
import hashlib; h=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
assert h('$D/candidate/parameters/flight_profile.py')==h('/work/fixed_image_r2f_20261110/src/bumblebee/examples/flight_profile.py')
print('13 / 18 ok')"

# 4. D1: the REAL composition lines of sitl_setup.py main() change on airframe 4061 (its ULog before any setup) exactly
#    the names in D1_ALLOWED (decided by the owner); the RC contract asserts the 4061 values
U4061=$(ls /work/goal_step5b_20261109/runs/l1_r2e_4061_loop/rootfs/log/*/*.ulg | tail -1)
t d1_setup_changes_on_4061 $HOME/px4-venv/bin/python3 -B -I $D/tests/d1_check.py "$U4061" "$D1_ALLOWED"
t d1_rc_contract python3 -B -I -c "
import json
rc=json.load(open('$D/candidate/parameters/rc_expected09.json')); old=json.load(open('/work/parallel_work/20261015/integration/combined_13/parameters/rc_expected09.json'))
assert rc['NAV_RCL_ACT']==3.0 and rc['COM_RCL_EXCEPT']==0.0
assert {k:v for k,v in rc.items() if k not in ('NAV_RCL_ACT','COM_RCL_EXCEPT')}=={k:v for k,v in old.items() if k not in ('NAV_RCL_ACT','COM_RCL_EXCEPT')}
af=open('/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4061_gz_bumblebee_candidate_4060_disarm_rcl_obl').read()
for l in ('param set-default NAV_RCL_ACT 3','param set-default COM_RCL_EXCEPT 0','param set-default COM_DISARM_LAND 0.5','param set-default COM_OBL_RC_ACT 4'):
    assert l in af, l
print('ok')"

# 5. D7: the VPE opt-in refuses a wrong / missing airframe and passes 4061 up to the MAVROS route check
cat > $O/optin_case.py <<'PY'
import json, sys, runpy
D = '/work/c8_judge_r2f_a8_20261110'
audit, o = json.loads(sys.argv[1]), sys.argv[2]
cfg = o + '/fake_mavros.yaml'; open(cfg, 'w').write('fcu_url: wrong\n')
audit.update(sim_gz_en_1=True, all_fcu_paths_guarded=True, no_hardware=True, raw_topics_verified=True, exclusive_profile_writer=True,
             mavros_config=cfg)
open(o + '/audit.json', 'w').write(json.dumps(audit))
sys.argv = ['vpe_profile_optin.py', '--sitl-opt-in', '--audit', o + '/audit.json', '--guard-directory', o, '--journal', o + '/j.json']
sys.path.insert(0, D + '/candidate/parameters')
try:
    runpy.run_path(D + '/candidate/parameters/vpe_profile_optin.py', run_name='__main__')
except RuntimeError as e:
    print(e)
PY
t d7_optin_refuses_4030 bash -c "python3 -B -I $O/optin_case.py '{\"sitl_autostart\":4030,\"sitl_autostart_source\":\"rc_ready.json:sys_autostart\"}' $O | grep -qx 'SITL airframe is not 4070'"
t d7_optin_refuses_old_label bash -c "python3 -B -I $O/optin_case.py '{\"sitl_4030\":true}' $O | grep -qx 'SITL airframe is not 4070'"
t d7_optin_refuses_4061 bash -c "python3 -B -I $O/optin_case.py '{\"sitl_autostart\":4061,\"sitl_autostart_source\":\"rc_ready.json:sys_autostart\"}' $O | grep -qx 'SITL airframe is not 4070'"
t d7_optin_4070_reaches_route_check bash -c "python3 -B -I $O/optin_case.py '{\"sitl_autostart\":4070,\"sitl_autostart_source\":\"rc_ready.json:sys_autostart\"}' $O | grep -qx 'MAVROS must use the existing guarded proxy route'"

# 6. D2: VPE composition with the r2e vpe_fix (ROS sourced, no node started): freshness + diagnostic wrapper + opt-in class
t d2_vpe_composition bash -c "set +u; source /opt/ros/jazzy/setup.bash; source /work/ws_sitl/install/setup.bash; source /work/ws_mavros214_bp02/install/local_setup.bash; source /work/fixed_image_r2f_20261110/install/local_setup.bash; set -u; ROS_DOMAIN_ID=83 ROS_LOCALHOST_ONLY=1 python3 -B -c \"
import sys, hashlib, importlib.util
from pathlib import Path
sys.path.insert(0, '$D/candidate/parameters')
spec = importlib.util.spec_from_file_location('gate_diagnostic', '$D/executor/vpe_gate_diagnostic_p1.py')
diagnostic = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnostic)
import vpe_fix
assert hashlib.sha256(Path(vpe_fix.__file__).read_bytes()).hexdigest() == diagnostic.TARGET_SHA256 == '3b8a93d4d08983694186766b0259fa6fa6b4167079c4078cf402a908d02e9725'
import vpe_freshness_optin, vpe_profile_optin
c33 = vpe_fix.VpeFix
vpe_freshness_optin.install(vpe_fix, enabled=True)
vpe_fix.VpeFix._evaluate_gate = diagnostic.diagnostic_wrapper(vpe_fix.VpeFix._evaluate_gate)
Node = vpe_profile_optin.make_node_class(vpe_fix.VpeFix)
mro = [c.__name__ for c in Node.__mro__]
assert 'FreshnessMixin' in mro and issubclass(vpe_fix.VpeFix, c33) and Node._freshness_pose_timeout_ns == 500000000, mro
print(mro[:5])
\""
# control: the combined_13 freshness opt-in refuses the r2e vpe_fix (the pin is real)
t d2_old_pin_refuses_r2e bash -c "set +u; source /opt/ros/jazzy/setup.bash; source /work/ws_sitl/install/setup.bash; source /work/ws_mavros214_bp02/install/local_setup.bash; source /work/fixed_image_r2f_20261110/install/local_setup.bash; set -u; mkdir -p $O/mix; cp $D/candidate/parameters/vpe_fix.py $O/mix/; cp /work/parallel_work/20261015/integration/combined_13/parameters/vpe_freshness_optin.py $O/mix/; python3 -B -c \"
import sys; sys.path.insert(0, '$O/mix')
import vpe_fix, vpe_freshness_optin
try:
    vpe_freshness_optin.install(vpe_fix, enabled=True); print('ACCEPTED'); sys.exit(1)
except ValueError as e:
    print('refused:', e)
\""
# 7. vpe_diagnostic_entry pins = the new helper and the candidate freshness file
t d2_entry_pins python3 -B -I -c "
import hashlib,re
h=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
s=open('$D/executor/vpe_diagnostic_entry.py').read()
assert h('$D/executor/vpe_gate_diagnostic_p1.py') in s and h('$D/candidate/parameters/vpe_freshness_optin.py') in s
print('ok')"

# 8. judge copy: refusals
J="/work/analysis/layout/.venv/bin/python -B -I $D/verify_flight_c8.py --run /work/sim/runs/INT_flight_pc_rel3_kill_01 --expected-manifest /work/parallel_work/20261015/integration/combined_13/manifest.json --frozen-pins /work/parallel_work/20261015/integration/flight_verification_03/frozen_inputs_32.json"
t judge_needs_identity bash -c "$J --out $D/reviews/x_noid.json > $O/noid.txt 2>&1; rc=\$?; [ \$rc = 2 ] && grep -q 'the following arguments are required: --identity' $O/noid.txt && [ ! -e $D/reviews/x_noid.json ]"
# the ledger run.sh will write equals the pins' ledger_files, keyed as the judge keys it
t ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2f_a8_01.json
t judge_refuses_unknown_identity bash -c "$J --out $D/reviews/x_bad.json --identity c8_4030 2>&1 | grep -q 'invalid choice'; [ ! -e $D/reviews/x_bad.json ]"
t judge_refuses_out_outside bash -c "$J --out $O/x.json --identity rel3_4030 2>&1 | grep -q 'only inside c8_judge_r2e_20261109/reviews'; [ ! -e $O/x.json ]"
t judge_refuses_overwrite bash -c "$J --out $D/reviews/OVERWRITE_GUARD.json --identity rel3_4030 2>&1 | grep -q 'only inside c8_judge_r2e_20261109/reviews'"
# 9. judge copy: the identity takes effect and changes only the identity / profile-name checks (rel3 kill run, 4030)
mkdir -p $D/reviews/tests_$(basename $O)
t judge_c8_identity_effect bash -c "$J --identity c8_4061 --out $D/reviews/tests_$(basename $O)/kill_as_c8_4061.json >/dev/null; python3 -B -I -c \"
import json
a=json.load(open('/work/c8_judge_r2e_20261109/reviews/rel3_proof_v2/INT_flight_pc_rel3_kill_01_review.json'))
b=json.load(open('$D/reviews/tests_$(basename $O)/kill_as_c8_4061.json'))
la,lb=a['legacy_full_report']['checks'],b['legacy_full_report']['checks']
diff=sorted(k for k in set(la)|set(lb) if la.get(k,{}).get('status')!=lb.get(k,{}).get('status'))
assert diff==['candidate4030','real_parameters_before_arm'], diff
assert lb['candidate4030']['status']=='failed' and set(lb['candidate4030']['evidence']['mismatches'])=={'SYS_AUTOSTART'}
assert lb['candidate4030']['evidence']['mismatches']['SYS_AUTOSTART']['expected']==4061
# v2 (A5): the rel3 run holds the 20EC-file values, the c8 expectation the 5 values of 4061 -> exactly these 5 mismatch
rp=lb['real_parameters_before_arm']
assert rp['status']=='failed' and set(rp['evidence']['mismatches'])=={'NAV_RCL_ACT','COM_RCL_EXCEPT','COM_DISARM_LAND','COM_SPOOLUP_TIME','BAT1_SOURCE'}, rp['evidence']['mismatches']
assert {k:v['expected'] for k,v in rp['evidence']['mismatches'].items()}=={'NAV_RCL_ACT':3.0,'COM_RCL_EXCEPT':0.0,'COM_DISARM_LAND':0.5,'COM_SPOOLUP_TIME':1.0,'BAT1_SOURCE':1}
assert rp['evidence']['expected_count']==la['real_parameters_before_arm']['evidence']['expected_count']
assert [s['path'] for s in rp['evidence']['sources']]==['$D/expect/flight_real_params_4061.json','$D/expect/rc_real_params_4061.json']
assert la['simulation_only_parameters']==lb['simulation_only_parameters']
pa,pb=a['profile19']['checks'],b['profile19']['checks']
pd=sorted(k for k in pa if pa[k]['status']!=pb[k]['status'])
assert set(pd)<={'journal_names','independent_before','independent_after','independent_stable','journal_expected','journal_final_readback'} and 'journal_names' in pd, pd
assert all(pb[k]['status']=='failed' for k in pd), {k:pb[k]['status'] for k in pd}
assert b['scenario_status']=='failed' and a['scenario_status']=='pass'
assert a['provenance']==b['provenance'] and a['supplementary']==b['supplementary']
print('legacy diff',diff,'profile diff',pd)
\""
# 10. v2 (variant A): the 4061 expectation files differ from sim/ros_stack in exactly 5 numbers (A5)
t expect_diff_exactly_five python3 -B -I -c "
import json
def flat(p):
    d=json.load(open(p)); return {(sec,k):v for sec in ('parameters','sim_only','excluded_from_test') for k,v in d.get(sec,{}).items()}, {k:v for k,v in d.items() if k not in ('parameters','sim_only','excluded_from_test')}
diffs=[]
for o,n in (('/work/sim/ros_stack/flight_real_params.json','$D/expect/flight_real_params_4061.json'),('/work/sim/ros_stack/rc_real_params.json','$D/expect/rc_real_params_4061.json')):
    (a,ma),(b,mb)=flat(o),flat(n)
    assert ma==mb and set(a)==set(b)
    diffs+=[(k[1],a[k]['value'],b[k]['value']) for k in a if a[k]!=b[k]]
    assert all(a[k]['type']==b[k]['type'] for k in a)
assert sorted(diffs)==[('BAT1_SOURCE',-1,1),('COM_DISARM_LAND',2.0,0.5),('COM_RCL_EXCEPT',4.0,0.0),('COM_SPOOLUP_TIME',0.0,1.0),('NAV_RCL_ACT',0.0,3.0)], diffs
import subprocess
t=subprocess.run(['diff','/work/sim/ros_stack/rc_real_params.json','$D/expect/rc_real_params_4061.json'],capture_output=True,text=True).stdout
t+=subprocess.run(['diff','/work/sim/ros_stack/flight_real_params.json','$D/expect/flight_real_params_4061.json'],capture_output=True,text=True).stdout
assert sum(1 for l in t.splitlines() if l.startswith('>'))==5, t
print(diffs)"
# 11. v2: a changed expectation file makes the judge refuse (sha pin), and rel3_4030 never uses the expectation files
t judge_expect_pin_enforced /work/analysis/layout/.venv/bin/python -B -I -c "
import importlib.util
s=importlib.util.spec_from_file_location('vj','$D/verify_flight_c8.py'); vj=importlib.util.module_from_spec(s); s.loader.exec_module(vj)
vj.use_identity('rel3_4030'); m=vj.load_legacy(); assert m.REAL_PARAMS is None and m.AUTOSTART==4030
vj.use_identity('c8_4061'); m=vj.load_legacy(); assert m.AUTOSTART==4061 and sorted(m.REAL_PARAMS)==['flight_real_params.json','rc_real_params.json']
p,h=vj.IDENTITIES['c8_4061']['real_params']['rc_real_params.json']
vj.IDENTITIES['c8_4061']['real_params']['rc_real_params.json']=(p,'0'*64)
try:
    vj.load_legacy(); raise SystemExit('accepted a wrong expectation sha')
except ValueError as e:
    print('refused:',e)"
# 12. v2: launcher accepts only pins 02 (pins 01 pin the judge copy v1)
t launcher_refuses_pins_01 bash -c "! env C8_AF_FILE=/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4061_gz_bumblebee_candidate_4060_disarm_rcl_obl \
  C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
  C8_DRONE_PY=/work/fixed_image_r2f_20261110/src/bumblebee/examples/drone.py \
  python3 -I $O/precheck.py $D/candidate /work/c8_judge_r2e_a7_20261110/pins/frozen_inputs_c8_r2e_a7_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"

# A6: apply order on the 4061 baseline (candidate KnownCapsModel = the PX4 committed clamps): new order reaches every
# profile value; the old dict order reproduces the run failure (MPC_XY_CRUISE 0.25); the restore returns the baseline.
t a6_apply_order python3 -B -I $D/tests/a6_apply_order.py
# A7: the package camera launch accepts exactly this candidate, refuses others and a changed detector (ROS sourced, no node started)
t a7_vision_launch bash -c "set +u; source /opt/ros/jazzy/setup.bash; source /work/ws_sitl/install/setup.bash; set -u; python3 -B $D/tests/a7_vision_launch.py"
# A8: identity c8_4070, expectations = 4061 + EXPECT_4070 = airframe 4070, judge diff = one row, candidate/pins/product r2f
t a8_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a8_checks.py
# A8: c8_4070 on the rel3 kill run: as c8_4061 plus the EXPECT_4070 names (judge really reads the 4070 files)
t judge_c8_4070_effect bash -c "$J --identity c8_4070 --out $D/reviews/tests_$(basename $O)/kill_as_c8_4070.json >/dev/null; /work/analysis/layout/.venv/bin/python -B -I $D/tests/a8_judge_effect.py $D/reviews/tests_$(basename $O)/kill_as_c8_4061.json $D/reviews/tests_$(basename $O)/kill_as_c8_4070.json"
# A8: on a real 4061 run of A7: c8_4061 = A7 verdict; c8_4070 fails only on autostart + BAT1_SOURCE / SDLOG_MODE
t a8_judge_on_a7_run python3 -B -I $D/tests/a8_judge_on_a7_run.py $D/reviews/tests_$(basename $O)
echo "RESULT pass=$PASS fail=$FAIL (logs $O)"
[ "$FAIL" = 0 ]
