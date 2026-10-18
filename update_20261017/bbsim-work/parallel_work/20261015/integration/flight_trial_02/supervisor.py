#!/usr/bin/env python3
"""One guarded simulator flight and independent restoration of all 19 values."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
os.environ['MAVLINK20']='1'
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--guard',type=Path,required=True);p.add_argument('--scenario',required=True);a=p.parse_args()
assert sys.platform=='linux' and str(a.out).startswith('/work/sim/runs/INT_flight_'),'simulator VM run directory required'
assert os.environ['ROS_DOMAIN_ID']=='83' and os.environ['ROS_LOCALHOST_ONLY']=='1','isolated ROS domain 83 on localhost required'
sys.path.insert(0,str(a.candidate))
import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy,qos_profile_sensor_data
from mavros_msgs.msg import Mavlink,State
from mavros_msgs.srv import SetMode
from std_srvs.srv import Trigger
from geometry_msgs.msg import PoseWithCovarianceStamped
from std_msgs.msg import Int32,Bool
from bumblebee.srv import SetParam
from ros_raw_bridge import RosRawBridge,PymavlinkCodec
from fresh_param_adapter import FreshParamAdapter
from sitl_profile_closure_candidate import closure_names,profile_values
from pymavlink import mavutil
from mavros import mavlink as convert

# Simulator speed guard (flight_trial_02). Every wall-clock wait below that expects
# simulator-paced messages (HEARTBEAT is 1 Hz SIM time, MAVROS conn.timeout is wall)
# only means something while the simulator keeps at least RTF_MIN. A slower run is
# classified as INVALID ENVIRONMENT (not a pass, not a product failure); no wait,
# timeout or acceptance criterion is relaxed. Value derived from the stack's wall
# limits before any trial (integration/flight_trial_02/RTF_MIN.md, audit wf_0300a691-d39:
# strict 0.15 = 3 HEARTBEATs within 20 s wall in verify_restored; 0.20 = recommended gate),
# not tuned on trial results.
RTF_MIN=0.20
RTF_WINDOW=5.0
RTF_GATE_WINDOW=10.0
CLOCK_JUMP_MAX=20.0  # guest realtime is not NTP-disciplined and creeps ~2 s after a host sleep; a real
                     # suspend is minutes. The host wrapper (host_run.sh) checks pmset Sleep events exactly.
class EnvironmentInvalid(Exception):
    pass
def clock_offset():
    # CLOCK_REALTIME - CLOCK_MONOTONIC. A guest/host suspend (e.g. the Mac idle-sleeping, run
    # INT_flight_preflight_04: 817 s) freezes the monotonic clock while realtime jumps on resume.
    return time.time()-time.monotonic()
report={'clock_offset_start':clock_offset(),'success':False,'scenario':a.scenario,'operations':[],
        'detector_gate_by_flight_state':True,'profile_restored':False,
        'flight_accepted':False,'started_wall':time.monotonic()}
sim_clock=[];children=[];logs=[];heartbeats=[];state=None;state_wall=None;pose_count=0;quality=[];rc_health={};bridge=None;wrapper=None;gate=None
def save():
    tmp=a.out/'flight_result.tmp';tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(a.out/'flight_result.json')
def event(kind,**kw):
    row={'kind':kind,'wall':time.monotonic(),**kw};report['operations'].append(row);save();print(json.dumps(row),flush=True)
def rtf_windows(start=None,end=None):
    # (wall_start, wall_end, rtf) over consecutive windows of >= RTF_WINDOW wall seconds,
    # from PX4 time_boot_ms (lockstep sim time) against this process's monotonic clock.
    rows=[r for r in list(sim_clock) if (start is None or r[0]>=start) and (end is None or r[0]<=end)]
    out=[];i=0
    while i<len(rows):
        j=i
        while j<len(rows) and rows[j][0]-rows[i][0]<RTF_WINDOW:j+=1
        if j>=len(rows):break
        out.append((rows[i][0],rows[j][0],(rows[j][1]-rows[i][1])/(rows[j][0]-rows[i][0])));i=j
    return out
def rtf_recent(seconds):
    rows=list(sim_clock)
    if len(rows)<2:return None
    end=rows[-1];first=next((r for r in rows if r[0]>=end[0]-seconds),None)
    if first is None or end[0]-first[0]<.8*seconds:return None
    return (end[1]-first[1])/(end[0]-first[0])
def rtf_sliding(start=None,end=None,width=RTF_GATE_WINDOW):
    # every window of `width` wall seconds starting at each sample (validity gate)
    rows=[r for r in list(sim_clock) if (start is None or r[0]>=start) and (end is None or r[0]<=end)]
    out=[];j=0
    for i in range(len(rows)):
        if j<i:j=i
        while j<len(rows) and rows[j][0]-rows[i][0]<width:j+=1
        if j>=len(rows):break
        out.append((rows[i][0],rows[j][0],(rows[j][1]-rows[i][1])/(rows[j][0]-rows[i][0])))
    return out
def px4_time():
    return sim_clock[-1][1] if sim_clock else None
def rtf_summary(start=None,end=None):
    w=rtf_windows(start,end);g=rtf_sliding(start,end)
    return {'min_required':RTF_MIN,'gate_window_wall_s':RTF_GATE_WINDOW,'gate_windows':len(g),
            'gate_min':min((x[2] for x in g),default=None),
            'gate_below_min':[{'wall_start':x[0],'wall_end':x[1],'rtf':x[2]} for x in g if x[2]<RTF_MIN][:50],
            'diag_window_wall_s':RTF_WINDOW,'diag_windows':[round(x[2],4) for x in w],
            'min':min((x[2] for x in w),default=None),'max':max((x[2] for x in w),default=None),
            'below_min':[{'wall_start':x[0],'wall_end':x[1],'rtf':x[2]} for x in w if x[2]<RTF_MIN][:50]}
def paced_wait(label,test,seconds,sim_needed):
    # A wall-clock wait for simulator-paced messages. If it fails while PX4 time advanced
    # less than the simulator time the condition needs, the simulator was too slow:
    # INVALID environment, not a product verdict. The wait itself is unchanged.
    t0=px4_time();n0=len(heartbeats);w0=time.monotonic()
    ok=wait(test,seconds)
    t1=px4_time();adv=None if t0 is None or t1 is None else t1-t0
    row={'label':label,'ok':ok,'wall_s':time.monotonic()-w0,'wall_limit':seconds,'px4_advance_s':adv,
         'px4_needed_s':sim_needed,'heartbeats':len(heartbeats)-n0}
    report.setdefault('paced_waits',[]).append(row)
    if ok:return True
    if adv is None or adv<sim_needed:
        raise EnvironmentInvalid(f'{label}: PX4 time advanced {adv} s in {seconds} s wall, needs {sim_needed} s; simulator too slow')
    raise AssertionError(label)
def require_rtf(label,seconds=10.0,timeout=30.0):
    # Precondition before any parameter access: the simulator must already run fast enough.
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=rtf_recent(seconds)
        if value is not None:
            event('rtf_check',label=label,rtf=value,seconds=seconds,min_required=RTF_MIN)
            if value<RTF_MIN:
                raise EnvironmentInvalid(f'{label}: simulator RTF {value:.3f} over {seconds:.0f} s wall is below {RTF_MIN}; '
                                         'wall-clock limits of this harness cannot be met, run is not a valid trial')
            return value
        time.sleep(.2)
    raise EnvironmentInvalid(f'{label}: no PX4 time_boot_ms stream to measure simulator speed within {timeout:.0f} s')
def check_clock_continuity():
    offset=clock_offset();report['clock_offset_end']=offset
    jump=offset-report['clock_offset_start'];report['clock_offset_jump_s']=jump
    if abs(jump)>CLOCK_JUMP_MAX:
        raise EnvironmentInvalid(f'realtime-monotonic offset moved {jump:.1f} s during the run: the VM/host was '
                                 'suspended or the guest clock stepped; run is not a valid trial')
def check_rtf_whole_run():
    check_clock_continuity()
    start=report.get('guarded_start_wall')
    report['rtf']=rtf_summary(start,None)
    if report['rtf']['gate_windows']==0:
        raise EnvironmentInvalid('no simulator speed measurement covers the guarded phase')
    if report['rtf']['gate_min']<RTF_MIN:
        raise EnvironmentInvalid(f"simulator RTF fell to {report['rtf']['gate_min']:.3f} (< {RTF_MIN}, {RTF_GATE_WINDOW:.0f} s windows) "
                                 'during the guarded phase; result cannot count as a pass')
def wait(test,seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if test():return True
        time.sleep(.02)
    return bool(test())
def spawn(cmd,name):
    log=(a.out/(name+'.log')).open('w');logs.append(log)
    child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    children.append(child);(a.out/(name+'.pid')).write_text(str(child.pid)+'\n');return child
def stop(child):
    if child.poll() is None:
        os.killpg(child.pid,signal.SIGINT)
        try:child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=5)

rclpy.init();node=Node('flight_profile_supervisor');executor=SingleThreadedExecutor();executor.add_node(node)
thread=threading.Thread(target=executor.spin,daemon=True);thread.start()
qos=QoSProfile(depth=1000,reliability=ReliabilityPolicy.BEST_EFFORT,durability=DurabilityPolicy.VOLATILE)
codec=PymavlinkCodec(mavutil,convert)
def observe(msg):
    if msg.framing_status!=1 or (msg.sysid,msg.compid)!=(1,1):return
    raw=codec.decode(msg)
    if raw is None:return
    kind=raw.get_type()
    boot=getattr(raw,'time_boot_ms',None)
    if boot is not None and kind in ('ATTITUDE','ATTITUDE_QUATERNION','SYSTEM_TIME','LOCAL_POSITION_NED','HIGHRES_IMU'):
        now=time.monotonic();sim=boot/1000.
        if not sim_clock or (sim>sim_clock[-1][1] and now-sim_clock[-1][0]>=.1):
            sim_clock.append((now,sim))
            if len(sim_clock)>200000:del sim_clock[:100000]
    if kind=='HEARTBEAT' and raw.autopilot==12:
        heartbeats.append({'endpoint':msg.header.frame_id,'armed':bool(raw.base_mode&128),'received':time.monotonic(),'custom_mode':raw.custom_mode})
    elif kind=='RC_CHANNELS':
        rc_health['pass_rc']=raw.chancount>=16;rc_health['channels_received']=time.monotonic()
    elif kind=='SYS_STATUS':
        rc_health['health_received']=time.monotonic()
        bit=mavutil.mavlink.MAV_SYS_STATUS_SENSOR_RC_RECEIVER
        rc_health['rc_receiver_healthy']=bool(raw.onboard_control_sensors_present&bit and raw.onboard_control_sensors_health&bit)
    elif kind=='STATUSTEXT':
        report.setdefault('statustext',[]).append({'wall':time.monotonic(),'severity':raw.severity,'text':raw.text})
def on_state(msg):
    global state,state_wall
    state=msg;state_wall=time.monotonic()
    report.setdefault('states',[]).append({'wall':state_wall,'armed':msg.armed,'connected':msg.connected,'mode':msg.mode})
def on_pose(msg):
    global pose_count
    pose_count+=1
def on_quality(kind,msg):quality.append({'wall':time.monotonic(),'kind':kind,'value':msg.data})
node.create_subscription(Mavlink,'/uas1/mavlink_source',observe,qos)
node.create_subscription(State,'/mavros/state',on_state,QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL))
node.create_subscription(PoseWithCovarianceStamped,'/aruco_map/pose',on_pose,qos_profile_sensor_data)
node.create_subscription(Int32,'/aruco_detect/markers_used',lambda m:on_quality('markers_used',m),qos_profile_sensor_data)
node.create_subscription(Bool,'/aruco_detect/yaw_locked',lambda m:on_quality('yaw_locked',m),qos_profile_sensor_data)
def call(kind,name,request,timeout=35):
    client=node.create_client(kind,name)
    try:
        assert client.wait_for_service(timeout_sec=20),name+' unavailable'
        start=time.monotonic();future=client.call_async(request)
        assert wait(future.done,timeout),name+' response timeout'
        result=future.result();event('service_reply',service=name,wall_seconds=time.monotonic()-start,
            success=getattr(result,'success',getattr(result,'mode_sent',False)),message=getattr(result,'message',''))
        return result
    finally:node.destroy_client(client)
def read_all():
    values={};deadline=time.monotonic()+30
    for name in closure_names(profile_values()):
        while True:
            try:
                sample=adapter.read_fresh(name,deadline)
                break
            except RuntimeError as error:
                # Read-only observer may await a fresh proxy status. No SET is
                # retried, no state window or total read deadline is enlarged.
                status=json.loads((a.guard/'status.json').read_text())
                age=time.monotonic()-status['received']
                if (str(error)!='proxy guard unavailable or conflicted' or
                        status.get('fault') is not None or
                        status.get('writer')!=[245,190] or age<0 or
                        (bridge.epoch is not None and status.get('epoch')!=bridge.epoch) or
                        time.monotonic()>=deadline):
                    raise
                event('observer_read_retry',name=name,status_age_wall=age,
                      deadline_wall=deadline,parameter_write_retried=False)
                time.sleep(min(.02,max(0,deadline-time.monotonic())))
        values[name]={'value':sample.value,'type':sample.mav_param_type,'received':sample.received,'source':[sample.sysid,sample.compid]}
    return values
def journal_restored():
    try:return json.loads((a.guard/'profile_journal.json').read_text()).get('status')=='restored'
    except (OSError,ValueError):return False
def verify_restored():
    report['independent_after']=read_all()
    report['mismatches']={n:{'before':v,'after':report['independent_after'][n]} for n,v in report['independent_before'].items()
        if abs(v['value']-report['independent_after'][n]['value'])>1e-6 or v['type']!=report['independent_after'][n]['type']}
    assert not report['mismatches'],report['mismatches']
    before=len(heartbeats);paced_wait('No stability HEARTBEATs',lambda:len(heartbeats)>=before+3,20,3.0)
    report['independent_stable']=read_all()
    for n,v in report['independent_before'].items():
        assert abs(v['value']-report['independent_stable'][n]['value'])<=1e-6 and v['type']==report['independent_stable'][n]['type'],n
    report['profile_restored']=True;event('all_19_restored',count=19)

try:
    paced_wait('No connected PX4',lambda:len(heartbeats)>=3 and state and state.connected,45,3.0)
    assert not any(h['armed'] for h in heartbeats),'PX4 already armed before the trial'
    endpoint=heartbeats[-1]['endpoint'];assert {h['endpoint'] for h in heartbeats}=={endpoint},'FCU HEARTBEATs from more than one endpoint'
    match=re.search(r'Requested to add endpoint: type: 0, url: udp://127\.0\.0\.1:14640@127\.0\.0\.1:14680.*?Endpoint link\[(\d+)\] created',(a.out/'mavros.log').read_text(),re.S)
    assert match and endpoint=='ep:'+match[1],'FCU endpoint is not the guarded proxy link'
    assert len(node.get_publishers_info_by_topic('/uas1/mavlink_source'))==1,'more than one /uas1/mavlink_source publisher'
    initial=require_rtf('before first parameter access')
    if initial<.5:
        event('rtf_warning',initial=initial,note='vision load roughly halved RTF in run 02; below 0.5 here may fall under the gate later')
    report['guarded_start_wall']=time.monotonic()
    audit={'sitl_4030':True,'sim_gz_en_1':True,'all_fcu_paths_guarded':True,'no_hardware':True,
        'raw_topics_verified':True,'exclusive_profile_writer':True,'fcu_endpoint':endpoint,
        'mavros_config':str(a.out/'mavros.yaml'),
        'source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in a.candidate.iterdir() if f.suffix in ('.py','.json')},
        'route_scope':'All active writers during guarded phase; setup process has exited. Not an OS security sandbox.',
        'identity_evidence':str(a.out/'rc_ready.json'),
        'processes':subprocess.check_output(['ps','-eo','pid,ppid,args'],text=True),
        'udp_sockets':subprocess.check_output(['ss','-unp'],text=True)}
    (a.out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    bridge=RosRawBridge(node,a.guard,endpoint);adapter=FreshParamAdapter(bridge)
    paced_wait('raw bridge saw no FCU HEARTBEAT within 15 s wall',lambda:bridge.heartbeat is not None,15,1.0)
    rc=spawn([sys.executable,str(a.out/'rc_emulator.py'),'--out',str(a.out),'--guard',str(a.guard)],'rc_emulator')
    report['independent_before']=read_all();save()
    subscriptions=len(node.get_subscriptions_info_by_topic('/uas1/mavlink_source'))
    wrapper=spawn([sys.executable,str(a.out/'vpe_diagnostic_entry.py'),'--sitl-opt-in','--audit',str(a.out/'audit.json'),
        '--guard-directory',str(a.guard),'--journal',str(a.guard/'profile_journal.json'),
        '--ros-args','-p','use_sim_time:=true'],'wrapper')
    assert wait(lambda:len(node.get_subscriptions_info_by_topic('/uas1/mavlink_source'))>subscriptions,20),'vpe_fix wrapper did not subscribe to /uas1/mavlink_source within 20 s wall'
    old=len(heartbeats);paced_wait('fewer than 2 new FCU HEARTBEATs within 15 s wall after the vpe_fix wrapper started',lambda:len(heartbeats)>=old+2,15,2.0)
    assert call(Trigger,'/vpe_fix/prepare_profile',Trigger.Request()).success,'prepare_profile refused'
    for name,value in profile_values().items():
        req=SetParam.Request();req.param_id=name;req.ptype=1;req.value=value;req.ttl_sec=0.;req.persistent=False
        assert call(SetParam,'/vpe_fix/set_param',req).success,'Apply failed '+name
    report['independent_applied']=read_all()
    for name,value in profile_values().items():assert abs(report['independent_applied'][name]['value']-value)<=1e-6,name
    assert call(Trigger,'/vpe_fix/allow_profile_flight',Trigger.Request()).success,'allow_profile_flight refused'
    prepared={'profile_applied':True,'profile_count':len(profile_values()),'allow_flight':True,'wall':time.monotonic()}
    (a.out/'flight_prepared.json').write_text(json.dumps(prepared)+'\n')
    assert wait(lambda:rc.poll() is None and rc_health.get('pass_rc') and rc_health.get('rc_receiver_healthy') and time.monotonic()-rc_health.get('channels_received',0)<3 and time.monotonic()-rc_health.get('health_received',0)<10,20),'Virtual RC not healthy'
    observed=json.loads((a.out/'rc_ready.json').read_text());observed.update(rc_health)
    observed['channels']=[1499,1500,1000,1497,1000,1000,1500,1000]+[1500]*8
    (a.out/'rc_observer.json').write_text(json.dumps(observed,indent=2)+'\n')
    pipeline=spawn(['/work/sim/ros_stack/.venv/bin/python','/work/sim/ros_stack/pipeline_probe.py',
        '--out',str(a.out/'pipeline.json'),'--sim-seconds','120','--wall-timeout','700',
        '--max-records','100000','--allow-armed-sitl'],'pipeline')
    request=SetMode.Request();request.custom_mode='OFFBOARD'
    before=time.monotonic();assert call(SetMode,'/mavros/set_mode',request,15).mode_sent,'SetMode OFFBOARD not sent'
    paced_wait('Disarmed OFFBOARD not observed',lambda:state_wall>before and state.connected and state.mode=='OFFBOARD' and not state.armed,20,1.0)
    paced_wait('Default detector did not start',lambda:pose_count>=20,45,1.12)
    paced_wait('No fresh yaw lock before ARM',lambda:any(row['kind']=='yaw_locked' and row['value'] is True and time.monotonic()-row['wall']<3. for row in quality[-100:]),45,3.25)
    event('default_detector_started',poses=pose_count,armed=state.armed,mode=state.mode,quality=quality[-10:])
    if a.scenario=='preflight':
        assert call(Trigger,'/vpe_fix/revert_all',Trigger.Request()).success,'revert_all refused'
        verify_restored();check_rtf_whole_run();report['success']=True
    else:
        gate=spawn(['/work/sim/ros_stack/.venv/bin/python',str(a.out/'gate.py'),'--out',str(a.out),
            '--scenario',a.scenario,'--offset-ms',os.environ.get('CANCEL_OFFSET_MS','500'),
            '--ros-args','-p','use_sim_time:=true'],'gate')
        deadline=time.monotonic()+560
        while gate.poll() is None:
            assert time.monotonic()<deadline,'Flight driver timeout'
            assert rc.poll() is None,'Independent RC process exited during flight'
            rc_report=json.loads((a.out/'rc_emulator.json').read_text())
            assert time.monotonic()-rc_report['last_wall']<3.,'Independent RC process stalled'
            time.sleep(.2)
        report['gate_returncode']=gate.returncode
        result=json.loads((a.out/'gate_result.json').read_text());report['gate_result']=result
        assert state and state.connected and not state.armed,'Gate ended without disarm'
        armed_seen=any(h['armed'] for h in heartbeats)
        report['automatic_restore_required']=armed_seen
        if armed_seen:
            assert wait(journal_restored,35),'Automatic all19 restore failed'
        else:
            assert call(Trigger,'/vpe_fix/revert_all',Trigger.Request()).success,'No-ARM restoration failed'
        verify_restored()
        assert report['gate_returncode']==0 and result['pass'],'Flight gate failed; see retained gate_result'
        check_rtf_whole_run();report['success']=True
    event('scenario_completed',success=report['success'],flight_acceptance='Independent scenario review pending')
except BaseException as error:
    report['error']=repr(error)
    report['failure_class']='environment_invalid' if isinstance(error,EnvironmentInvalid) else 'trial_failure'
    report['environment_valid']=not isinstance(error,EnvironmentInvalid)
    if report.get('guarded_start_wall') is not None and not isinstance(error,EnvironmentInvalid):
        # The speed gate applies whatever the outcome: a failure observed while the simulator ran
        # below RTF_MIN is kept as an observation, but the run is INVALID, not a product verdict.
        gate=rtf_summary(report['guarded_start_wall'],None)
        if gate['gate_min'] is not None and gate['gate_min']<RTF_MIN:
            report['failure_class']='environment_invalid';report['environment_valid']=False
            report['observed_failure_under_low_rtf']=repr(error);report['rtf']=gate
    report['rtf_at_failure']={'last_10s':rtf_recent(10.),'last_30s':rtf_recent(30.)}
    report['clock_offset_jump_s']=clock_offset()-report['clock_offset_start']
    if abs(report['clock_offset_jump_s'])>CLOCK_JUMP_MAX:
        report['failure_class']='environment_invalid';report['environment_valid']=False
    event('failure',message=repr(error),failure_class=report['failure_class'],rtf_at_failure=report['rtf_at_failure'])
finally:
    # Record failure before cleanup; cleanup cannot convert it to acceptance.
    report['success_before_cleanup']=report['success'];save()
    if gate and gate.poll() is None:
        try:stop(gate)
        except Exception as error:report['driver_stop_error']=repr(error)
    try:wait(lambda:state is not None and state.connected,20)  # bounded: MAVROS may be between heartbeats
    except Exception as error:report['cleanup_wait_error']=repr(error)
    if state and state.connected and state.armed:
        try:
            request=SetMode.Request();request.custom_mode='AUTO.LAND'
            call(SetMode,'/mavros/set_mode',request,15)
            wait(lambda:state and state.connected and not state.armed,120)
        except Exception as error:report['cleanup_land_error']=repr(error)
    if wrapper and wrapper.poll() is None and state and state.connected and not state.armed and not report['profile_restored']:
        try:
            result=call(Trigger,'/vpe_fix/revert_all',Trigger.Request())
            if result.success and 'independent_before' in report:verify_restored()
        except Exception as error:report['cleanup_restore_error']=repr(error)
    (a.out/'rc_stop').touch()
    # S4's transport stays until restoration, then only this recorded process is stopped.
    extra=a.out/'extra_processes.json'
    if extra.exists():
        for item in json.loads(extra.read_text()):
            try:
                pid=item['pid'];proc=Path(f'/proc/{pid}')
                def owned_live():
                    try:
                        stat=(proc/'stat').read_text().split(') ',1)[1].split()
                        return stat[0]!='Z' and int(stat[19])==item['start_ticks'] and (proc/'cmdline').read_bytes().split(b'\0')[0].decode()==item['executable']
                    except FileNotFoundError:return False
                if owned_live():
                    os.killpg(item['pgid'],signal.SIGINT)
                    if not wait(lambda:not owned_live(),5) and owned_live():
                        os.killpg(item['pgid'],signal.SIGTERM)
                        if not wait(lambda:not owned_live(),5):report.setdefault('cleanup_errors',[]).append('S4 MAVROS still alive')
            except ProcessLookupError:pass
            except Exception as error:report.setdefault('cleanup_errors',[]).append(repr(error))
    for child in reversed(children):
        try:stop(child)
        except Exception as error:report.setdefault('cleanup_errors',[]).append(repr(error))
    report['heartbeats']=heartbeats;report['quality']=quality;report['final_rc_health']=rc_health
    report.setdefault('rtf',rtf_summary(report.get('guarded_start_wall'),None))
    report['rtf_whole_process']=rtf_summary(None,None)
    report['clock_offset_final_jump_s']=clock_offset()-report['clock_offset_start']
    report['finished_wall']=time.monotonic();save()
    executor.shutdown(timeout_sec=3);thread.join(3);node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    for log in logs:log.close()
sys.exit(0 if report['success'] else 1)
