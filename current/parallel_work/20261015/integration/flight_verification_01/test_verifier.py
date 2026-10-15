#!/usr/bin/env python3
"""Adversarial report checks; no ROS, sockets, VM, or control commands."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode = True
import verify_flight as v


def fixture():
    baseline={name:float(i) for i,name in enumerate(sorted(v.NAMES))}
    def scan(start):
        return {name:dict(value=value,type=9,source=[1,1],received=start+i*.001)
                for i,(name,value) in enumerate(baseline.items())}
    flight=dict(profile_restored=True,started_wall=0.,finished_wall=50.,
        independent_before=scan(1.),independent_applied=scan(5.),
        independent_after=scan(30.),independent_stable=scan(40.),
        states=[dict(wall=10.,armed=True,connected=True),dict(wall=20.,armed=False,connected=True)])
    journal=dict(status='restored',pending=None,baseline=baseline,expected=baseline.copy(),final_readback=baseline.copy())
    packets=[dict(kind='heartbeat_forwarded',source_system=1,source_component=1,autopilot=12,armed=False,wall=t) for t in (31.,32.,33.)]
    return flight,journal,packets


class ProfileEvidenceTests(unittest.TestCase):
    def test_complete_distinct_exact19(self):
        self.assertEqual(v.profile_review(*fixture())['status'],'pass')

    def test_single_hidden_dependent_mismatch(self):
        f,j,p=fixture();f['independent_stable']['MPC_VEL_MANUAL']['value']+=.0000001
        self.assertEqual(v.profile_review(f,j,p)['status'],'failed')

    def test_missing_nineteenth_is_not_fourteen_success(self):
        f,j,p=fixture();del f['independent_after']['MPC_Z_V_AUTO_UP']
        self.assertEqual(v.profile_review(f,j,p)['status'],'failed')

    def test_wrong_source_and_type(self):
        for key,value in [('source',[1,2]),('type',6)]:
            f,j,p=fixture();f['independent_before']['MPC_XY_P'][key]=value
            self.assertEqual(v.profile_review(f,j,p)['status'],'failed')

    def test_after_before_disarm(self):
        f,j,p=fixture()
        for s in f['independent_after'].values():s['received']=15.
        self.assertEqual(v.profile_review(f,j,p)['status'],'failed')

    def test_stability_requires_three_fcu_heartbeats(self):
        f,j,p=fixture();p[-1]['source_component']=2
        self.assertEqual(v.profile_review(f,j,p)['status'],'failed')

    def test_rearmed_or_disconnected_stability_cannot_pass(self):
        for variant in ('rearm','disconnect'):
            f,j,p=fixture()
            if variant=='rearm':p[-1]['armed']=True
            else:f['states'][-1]['connected']=False
            self.assertEqual(v.profile_review(f,j,p)['status'],'failed')

    def test_pending_journal_cannot_be_restored(self):
        f,j,p=fixture();j['pending']={'name':'MPC_XY_P'}
        self.assertEqual(v.profile_review(f,j,p)['status'],'failed')

    def test_missing_scan_is_unknown(self):
        f,j,p=fixture();del f['independent_stable']
        self.assertEqual(v.profile_review(f,j,p)['status'],'unknown')

    def test_nonfinite_is_failed(self):
        f,j,p=fixture();f['independent_after']['MPC_XY_P']['value']=float('nan')
        self.assertEqual(v.profile_review(f,j,p)['status'],'failed')


class ScenarioTests(unittest.TestCase):
    def test_legacy_long_freeze_cannot_count_as_exact_two(self):
        events=[dict(kind='injected_signal',pid=4,signal='freeze',sim=10.,wall=20.),
                dict(kind='sigcont_before',pid=4,sim=13.732,wall=30.),
                dict(kind='sigcont',pid=4,sim=13.732,wall=30.001)]
        old={'checks':{'offboard_no_armed_reentry':v.item('pass')}}
        r=v.scenario_measurements('freeze',events,[],True,None,old,{})
        self.assertEqual(r['checks']['stop_two_sim_seconds']['status'],'failed')
        events[1]['sim']=events[2]['sim']=12.
        self.assertEqual(v.scenario_measurements('freeze',events,[],True,None,old,{})['status'],'pass')
        events[2]['sim']=12.5
        self.assertEqual(v.scenario_measurements('freeze',events,[],True,None,old,{})['status'],'failed')

    def test_late_target_in_posctl_is_failure(self):
        packets=[dict(kind='heartbeat_forwarded',source_system=1,source_component=1,autopilot=12,
                      armed=True,custom_mode=3<<16,wall=10.,px4_sim=5.),
                 dict(kind='setpoint_forwarded',wall=11.,px4_sim=5.2)]
        events=[dict(kind='pilot_command_refusal',success=False),dict(kind='external_mode_sent',mode='AUTO.LAND',wall=20.,sim=10.)]
        r=v.scenario_measurements('pilot',events,packets,True,None,{}, {})
        self.assertEqual(r['checks']['targets_stop_after_posctl_heartbeat']['status'],'failed')

    def test_heartbeat_never_becomes_s9_pass(self):
        self.assertEqual(v.scenario_measurements('heartbeat',[],[],True,None,{}, {})['status'],'unknown')

    def test_uncovered_s8_stays_unknown(self):
        old={'checks':{name:v.item('pass') for name in ('physical_takeoff','land_actual_disarm','landing_disarm_within_3s')}}
        self.assertEqual(v.scenario_measurements('land',[],[],True,None,old,{})['checks']['next_physical_takeoff']['status'],'unknown')

    def test_cleanup_and_core_cannot_promote_failed_flight(self):
        for raw,success in [(False,True),(True,False)]:
            with tempfile.TemporaryDirectory(dir=v.HERE) as tmp:
                run=Path(tmp)
                (run/'flight_result.json').write_text(json.dumps(dict(scenario='kill',success_before_cleanup=success,profile_restored=True)))
                (run/'gate_result.json').write_text(json.dumps(dict(scenario='kill',**{'pass':raw})))
                (run/'ulog_copy_status.json').write_text(json.dumps(dict(fresh_log_count=1,copied=True)))
                legacy=type('FakeReadOnlyVerifier',(),{'verify':staticmethod(lambda *_:{'independent_acceptance':{'status':'pass'}})})
                with patch.object(v,'load_legacy',return_value=legacy),patch.object(v,'read_packets',return_value=([],True)),patch.object(v,'profile_review',return_value={'status':'pass'}),patch.object(v,'provenance',return_value={'status':'pass'}):
                    r=v.verify(run,run/'unused',{})
                self.assertEqual(r['scenario_status'],'failed')
                self.assertEqual(r['existing_core']['status'],'pass')


class ProvenanceTests(unittest.TestCase):
    def test_mutated_run_copy_and_changed_accepted_manifest(self):
        with tempfile.TemporaryDirectory(dir=v.HERE) as tmp:
            base=Path(tmp);combined=base/'combined';combined.mkdir();run=base/'run';run.mkdir()
            (combined/'candidate.py').write_text('accepted\n')
            manifest=combined/'manifest.json'
            files={'candidate.py':v.digest(combined/'candidate.py')}
            manifest.write_text(json.dumps({'files':files}))
            (run/'combined_manifest.json').write_bytes(manifest.read_bytes())
            (run/'gate.py').write_text('frozen\n')
            (run/'flight_source.sha256').write_text(v.digest(run/'gate.py')+'  /work/sim/runs/test/gate.py\n')
            pins=dict(combined_manifest_sha256=v.digest(manifest),combined_files=files,
                repo_files={'combined/candidate.py':files['candidate.py']},run_files={'gate.py':v.digest(run/'gate.py')},
                ledger_files={'@run/gate.py':v.digest(run/'gate.py')})
            with patch.object(v,'ROOT',base):
                self.assertEqual(v.provenance(run,manifest,pins,[])['status'],'pass')
                (run/'gate.py').write_text('changed\n')
                self.assertEqual(v.provenance(run,manifest,pins,[])['status'],'failed')
                (run/'gate.py').write_text('frozen\n');manifest.write_text(json.dumps({'files':files,'new':True}))
                self.assertEqual(v.provenance(run,manifest,pins,[])['checks']['accepted_manifest']['status'],'failed')

    def test_missing_pin_does_not_pass(self):
        with tempfile.TemporaryDirectory(dir=v.HERE) as tmp:
            path=Path(tmp);manifest=path/'manifest.json';manifest.write_text('{}')
            self.assertEqual(v.provenance(path,manifest,{},[])['status'],'unknown')


if __name__=='__main__':
    unittest.main()
