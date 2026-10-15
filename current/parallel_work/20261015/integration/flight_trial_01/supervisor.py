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
assert sys.platform=='linux' and str(a.out).startswith('/work/sim/runs/INT_flight_')
assert os.environ['ROS_DOMAIN_ID']=='83' and os.environ['ROS_LOCALHOST_ONLY']=='1'
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

report={'success':False,'scenario':a.scenario,'operations':[],
        'detector_gate_by_flight_state':True,'profile_restored':False,
        'flight_accepted':False,'started_wall':time.monotonic()}
children=[];logs=[];heartbeats=[];state=None;state_wall=None;pose_count=0;quality=[];rc_health={};bridge=None;wrapper=None;gate=None
def save():
    tmp=a.out/'flight_result.tmp';tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(a.out/'flight_result.json')
def event(kind,**kw):
    row={'kind':kind,'wall':time.monotonic(),**kw};report['operations'].append(row);save();print(json.dumps(row),flush=True)
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
    before=len(heartbeats);assert wait(lambda:len(heartbeats)>=before+3,20),'No stability HEARTBEATs'
    report['independent_stable']=read_all()
    for n,v in report['independent_before'].items():
        assert abs(v['value']-report['independent_stable'][n]['value'])<=1e-6 and v['type']==report['independent_stable'][n]['type'],n
    report['profile_restored']=True;event('all_19_restored',count=19)

try:
    assert wait(lambda:len(heartbeats)>=3 and state and state.connected,45),'No connected PX4'
    assert not any(h['armed'] for h in heartbeats)
    endpoint=heartbeats[-1]['endpoint'];assert {h['endpoint'] for h in heartbeats}=={endpoint}
    match=re.search(r'Requested to add endpoint: type: 0, url: udp://127\.0\.0\.1:14640@127\.0\.0\.1:14680.*?Endpoint link\[(\d+)\] created',(a.out/'mavros.log').read_text(),re.S)
    assert match and endpoint=='ep:'+match[1]
    assert len(node.get_publishers_info_by_topic('/uas1/mavlink_source'))==1
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
    assert wait(lambda:bridge.heartbeat is not None,15)
    rc=spawn([sys.executable,str(a.out/'rc_emulator.py'),'--out',str(a.out),'--guard',str(a.guard)],'rc_emulator')
    report['independent_before']=read_all();save()
    subscriptions=len(node.get_subscriptions_info_by_topic('/uas1/mavlink_source'))
    wrapper=spawn([sys.executable,str(a.out/'vpe_diagnostic_entry.py'),'--sitl-opt-in','--audit',str(a.out/'audit.json'),
        '--guard-directory',str(a.guard),'--journal',str(a.guard/'profile_journal.json'),
        '--ros-args','-p','use_sim_time:=true'],'wrapper')
    assert wait(lambda:len(node.get_subscriptions_info_by_topic('/uas1/mavlink_source'))>subscriptions,20)
    old=len(heartbeats);assert wait(lambda:len(heartbeats)>=old+2,15)
    assert call(Trigger,'/vpe_fix/prepare_profile',Trigger.Request()).success
    for name,value in profile_values().items():
        req=SetParam.Request();req.param_id=name;req.ptype=1;req.value=value;req.ttl_sec=0.;req.persistent=False
        assert call(SetParam,'/vpe_fix/set_param',req).success,'Apply failed '+name
    report['independent_applied']=read_all()
    for name,value in profile_values().items():assert abs(report['independent_applied'][name]['value']-value)<=1e-6,name
    assert call(Trigger,'/vpe_fix/allow_profile_flight',Trigger.Request()).success
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
    before=time.monotonic();assert call(SetMode,'/mavros/set_mode',request,15).mode_sent
    assert wait(lambda:state_wall>before and state.connected and state.mode=='OFFBOARD' and not state.armed,20),'Disarmed OFFBOARD not observed'
    assert wait(lambda:pose_count>=20,45),'Default detector did not start'
    assert wait(lambda:any(row['kind']=='yaw_locked' and row['value'] is True and time.monotonic()-row['wall']<3. for row in quality[-100:]),45),'No fresh yaw lock before ARM'
    event('default_detector_started',poses=pose_count,armed=state.armed,mode=state.mode,quality=quality[-10:])
    if a.scenario=='preflight':
        assert call(Trigger,'/vpe_fix/revert_all',Trigger.Request()).success
        verify_restored();report['success']=True
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
        report['success']=True
    event('scenario_completed',success=report['success'],flight_acceptance='Independent scenario review pending')
except BaseException as error:
    report['error']=repr(error);event('failure',message=repr(error))
finally:
    # Record failure before cleanup; cleanup cannot convert it to acceptance.
    report['success_before_cleanup']=report['success'];save()
    if gate and gate.poll() is None:
        try:stop(gate)
        except Exception as error:report['driver_stop_error']=repr(error)
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
    report['finished_wall']=time.monotonic();save()
    executor.shutdown(timeout_sec=3);thread.join(3);node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    for log in logs:log.close()
sys.exit(0 if report['success'] else 1)
