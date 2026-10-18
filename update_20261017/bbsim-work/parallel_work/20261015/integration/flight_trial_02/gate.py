#!/usr/bin/env python3
"""Real SDK/ROS on local Gazebo; bounded, recorded failure scenarios."""
import argparse
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
import shutil

p=argparse.ArgumentParser()
p.add_argument('--out',required=True)
p.add_argument('--scenario',choices=['land','kill','freeze','mavros_restart','pilot','cancel_before','cancel','ack_cancel','heartbeat'],required=True)
p.add_argument('--offset-ms',type=int,default=0)
a,_=p.parse_known_args();out=Path(a.out)
assert os.environ.get('ROS_DOMAIN_ID')=='83' and os.environ.get('ROS_LOCALHOST_ONLY')=='1'
assert os.environ.get('FASTDDS_BUILTIN_TRANSPORTS')=='UDPv4'
assert str(out).startswith('/work/sim/runs/')
assert not Path('/etc/bumblebee').exists() and not Path('/etc/bumblebee_version').exists()
assert 'udp://127.0.0.1:14640@127.0.0.1:14680' in Path(os.environ['SITL_MAVROS_PARAMS']).read_text()
if a.scenario=='mavros_restart':
    assert os.environ.get('SITL_MAVROS_RESPAWN')!='1', 'S4 requires autorespawn disabled before launch; use SITL_MAVROS_RESPAWN=0 only for this scenario'
sys.path.insert(0,str(out))
import drone
import flight_profile
drone._init()
drone.enable_safe_interrupt()
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy,qos_profile_sensor_data,qos_profile_system_default
from rclpy.service_introspection import ServiceIntrospectionState
from rclpy.clock import Clock as RclClock, ClockType
from mavros_msgs.msg import State
from mavros_msgs.srv import SetMode
from std_srvs.srv import Trigger
from geometry_msgs.msg import PoseStamped,PoseWithCovarianceStamped
from rosgraph_msgs.msg import Clock
from gz.transport13 import Node as GzNode
from gz.msgs10.pose_v_pb2 import Pose_V

n=rclpy.create_node('package1b_sitl_gate_monitor')
state=[None];state_rx=[0.];pose=[None];history=[];vision=[0];clock=[0.];truth=[];events=[];state_history=[]
start=time.monotonic();passed=False;sent=False;resumed=False;fault_pid=None
event_lock=threading.Lock();restarted_mavros=None;restart_log=None
acceptance_eligible=a.scenario!='heartbeat'
acceptance_limitation=('Gazebo heartbeat timing is diagnostic: C++ watchdog uses simulation time, but MAVROS sys_status conn_timeout defaults to 10 wall seconds. S9 requires a shared realtime clock or a separately declared simulator-only receiver timeout.' if not acceptance_eligible else None)
def event(kind,**kw):
    item={'wall':time.monotonic(),'elapsed':time.monotonic()-start,'sim':clock[0],'kind':kind,**kw}
    with event_lock:
        events.append(item);print(json.dumps(item),flush=True)
        temporary=out/'gate_events.tmp'
        temporary.write_text(json.dumps(events,indent=2)+'\n');temporary.replace(out/'gate_events.json')
    return item
def position(msg):
    pose[0]=msg;history.append((time.monotonic(),msg.pose.position.z))
    while history and time.monotonic()-history[0][0]>5:history.pop(0)
def state_message(m):
    state[0]=m;state_rx[0]=time.monotonic()
    state_history.append({'wall':state_rx[0],'sim':clock[0],'connected':bool(m.connected),
                          'armed':bool(m.armed),'mode':m.mode})
n.create_subscription(State,'/mavros/state',state_message,QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL))
n.create_subscription(PoseStamped,'/mavros/mavros/pose',position,qos_profile_sensor_data)
n.create_subscription(PoseWithCovarianceStamped,'/aruco_map/pose',lambda m:vision.__setitem__(0,vision[0]+1),qos_profile_sensor_data)
n.create_subscription(Clock,'/clock',lambda m:clock.__setitem__(0,m.clock.sec+m.clock.nanosec*1e-9),10)
def land_service_event(msg):
    info=msg.info
    if info.event_type not in (0,3):return
    client_wall=info.stamp.sec+info.stamp.nanosec*1e-9
    event('land_request_sent' if info.event_type==0 else 'land_reply_received',
          monitor_sim=clock[0],client_stamp_steady_wall=client_wall,
          client_gid=[int(value) for value in info.client_gid],sequence_number=int(info.sequence_number),
          event_type=int(info.event_type),
          wall_basis='observer callback receipt; exact client event uses client_stamp_steady_wall',
          sim_basis='approximate monitor clock at observer receipt, not client event time')
n.create_subscription(Trigger.Event,'/land/_service_event',land_service_event,qos_profile_system_default)
# Metadata observes the real client request/reply. It neither replaces the SDK
# client nor adds a relay to the command path. Any API error is before ARM.
assert bool(drone._node.get_parameter('use_sim_time').value), 'SDK flight stack must use the simulator clock'
# Retain this separate instrumentation clock for the entire client lifetime.
# Its Linux CLOCK_MONOTONIC epoch is checked against the Python/proxy clock.
land_introspection_clock=RclClock(clock_type=ClockType.STEADY_TIME)
clock_before=time.monotonic()
clock_read=land_introspection_clock.now().nanoseconds*1e-9
clock_after=time.monotonic()
clock_skew=max(abs(clock_read-clock_before),abs(clock_after-clock_read))
assert clock_skew < .01, f'LAND introspection steady clock does not match CLOCK_MONOTONIC: {clock_skew}'
drone._land_client.configure_introspection(land_introspection_clock,qos_profile_system_default,ServiceIntrospectionState.METADATA)
event('land_introspection_enabled',client_clock='RCL_STEADY_TIME / Linux CLOCK_MONOTONIC',
      mode='METADATA',command_path_unchanged=True,measured_max_clock_skew_wall_s=clock_skew,
      python_monotonic_before=clock_before,rcl_steady_time=clock_read,python_monotonic_after=clock_after)
def true_pose(msg):
    for v in msg.pose:
        if v.name=='bumblebee_0':
            truth.append({'wall':time.monotonic(),'sim':msg.header.stamp.sec+msg.header.stamp.nsec*1e-9,
                          'x':v.position.x,'y':v.position.y,'z':v.position.z})
gz=GzNode();assert gz.subscribe(Pose_V,'/world/default/dynamic_pose/info',true_pose)
mode=n.create_client(SetMode,'/mavros/set_mode')
revert=n.create_client(Trigger,'/vpe_fix/revert_all')
monitor=SingleThreadedExecutor();monitor.add_node(n)
monitor_thread=threading.Thread(target=monitor.spin,daemon=True);monitor_thread.start()
def wait(predicate,timeout):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:time.sleep(.02)
    return predicate()
def sim_wait(seconds,timeout=120):
    t=clock[0];assert wait(lambda:clock[0]-t>=seconds,timeout),'Simulation time stalled'
def profile_restoration_complete():
    """Require post-disarm wire readback before invoking the cleanup service."""
    try:
        observed=json.loads((out/'rc_observer.json').read_text())
        names=set(flight_profile.INDOOR_ARUCO)
        manifest=observed['profile_manifest']
        baseline=observed['profile_baseline']
        restored=observed['profile_restore_parameters']
        disarm_wall=observed['actual_px4_arm_to_disarm_wall']
        completed=observed['profile_restore_completed_wall']
        baseline_start=observed['profile_baseline_started_wall']
        baseline_end=observed['profile_baseline_completed_wall']
        first_arm=min(row['wall'] for row in observed['states'] if row['armed'] is True)
        if not (len(names)==14 and manifest['count']==14 and set(manifest['names'])==names
                and manifest['source_sha256']==hashlib.sha256((out/'flight_profile.py').read_bytes()).hexdigest()
                and observed['profile_baseline_all_confirmed'] is True
                and observed['profile_restore_all_confirmed'] is True
                and observed['profile_restore_status']=='all_14_confirmed'
                and set(baseline)==names and set(restored)==names
                and observed['states'][-1]['armed'] is False
                and all(math.isfinite(value) for value in (disarm_wall,completed,baseline_start,baseline_end,first_arm))
                and baseline_start<=baseline_end<first_arm<disarm_wall<=completed):
            return False
        for name in names:
            item=restored[name];sample=item['last_sample'];before=baseline[name]
            if not (item['confirmed'] is True and item['baseline']==before
                    and sample['type']==before['type']==9
                    and sample['source_system']==sample['source_component']==1
                    and before['source_system']==before['source_component']==1
                    and all(math.isfinite(value) for value in (before['request_wall'],before['wall'],sample['request_wall'],sample['wall']))
                    and baseline_start<=before['request_wall']<=before['wall']<=baseline_end
                    and disarm_wall<sample['request_wall']<=sample['wall']<=completed
                    and math.isfinite(sample['value']) and math.isfinite(before['value'])
                    and abs(sample['value']-before['value'])<.001):
                return False
        return True
    except (OSError,ValueError,KeyError,TypeError,IndexError):
        return False
def direct_mode(value):
    assert mode.wait_for_service(timeout_sec=10)
    req=SetMode.Request();req.custom_mode=value;f=mode.call_async(req)
    assert wait(f.done,15) and f.result().mode_sent,'Mode command refused'
    event('external_mode_sent',mode=value)
def own_pid(name,prefix):
    log=(out/'ros.log').read_text()
    label='mavros_node' if name=='mavros' else name
    if name=='mavros':
        pid=int((out/'mavros.pid').read_text())
        assert prefix in Path(f'/proc/{pid}/cmdline').read_bytes().decode().replace('\0',' ')
        return pid
    matches=re.findall(r'\['+label+r'-\d+\]: process started with pid \[(\d+)\]',log)
    assert matches,'No recorded PID for '+name
    pid=int(matches[-1]);cmd=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[0].decode()
    assert cmd.startswith(prefix) and cmd.endswith('/'+('mavros_node' if name=='mavros' else name)),cmd
    parent=pid;launch=int((out/'ros.pid').read_text())
    for _ in range(15):
        if parent==launch:break
        parent=int(Path(f'/proc/{parent}/stat').read_text().split(') ',1)[1].split()[1])
    assert parent==launch,'PID belongs to another launch'
    return pid
def packets():
    text=(out/'mavlink_proxy.jsonl').read_text()
    lines=text.splitlines()
    if text and not text.endswith('\n'):lines=lines[:-1]
    return [json.loads(l) for l in lines if l]
def proxy_clock():
    value=json.loads((out/'proxy_clock.json').read_text())
    assert value['source_system']==1 and value['source_component']==1
    assert time.monotonic()-value['wall']<1, 'PX4 clock recorder is stale'
    return value
def proxy_directive(value):
    temporary=out/'proxy_fault.tmp'
    temporary.write_text(json.dumps(value));temporary.replace(out/'proxy_fault.json')
def capture_mavros(pid):
    """Preserve only this owned local process; never print its environment."""
    folder=Path(f'/proc/{pid}')
    argv=[os.fsdecode(x) for x in (folder/'cmdline').read_bytes().split(b'\0') if x]
    raw=(folder/'environ').read_bytes()
    env=dict(os.fsdecode(x).split('=',1) for x in raw.split(b'\0') if b'=' in x)
    assert env.get('ROS_DOMAIN_ID')=='83' and env.get('ROS_LOCALHOST_ONLY')=='1'
    assert argv[0].startswith('/work/ws_mavros214/install/') and argv[0].endswith('/mavros_node')
    saved=out/'mavros_restart.environ'
    fd=os.open(saved,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)
    original=list(argv);copied={}
    for i,arg in enumerate(argv[:-1]):
        if arg=='--params-file':
            source=Path(argv[i+1]);target=out/f'mavros_restart_params_{i}.yaml'
            shutil.copy2(source,target);argv[i+1]=str(target);copied[str(source)]=str(target)
    cwd=os.readlink(folder/'cwd')
    (out/'mavros_restart_argv.json').write_text(json.dumps({'original':original,'restart':argv,'cwd':cwd,'parameter_snapshots':copied},indent=2)+'\n')
    return argv,env,cwd
def process_start_ticks(pid):
    return int(Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19])
def stopped_or_zombie(pid):
    path=Path(f'/proc/{pid}/stat')
    return not path.exists() or path.read_text().split(') ',1)[1].split()[0]=='Z'
def heartbeat_phase(duration,phase):
    """PX4 simulation clock drives the blackout; wall-clock mismatch is explicit."""
    initial=proxy_clock();start_wall=time.monotonic();start_sim=initial['px4_sim']
    until=start_sim+duration
    assert abs(clock[0]-start_sim)<.15, 'Gazebo and PX4 simulator clocks are not aligned'
    proxy_directive({'phase':phase,'drop_heartbeat_until_px4_sim':until})
    event('drop_heartbeats',phase=phase,duration_sim=duration,start_px4_sim=start_sim,
          until_px4_sim=until,acceptance_eligible=False,actual_mavros_conn_timeout_wall=10.)
    assert wait(lambda:proxy_clock()['px4_sim']>=until,120),'PX4 clock stalled during heartbeat fault'
    end_clock=proxy_clock();restored_wall=time.monotonic();proxy_directive({'phase':phase+'_recovery'})
    assert wait(lambda:any(r['kind']=='heartbeat_forwarded' and r['wall']>restored_wall for r in packets()),60), 'No source-identified FCU heartbeat after recovery'
    assert wait(lambda:state_rx[0]>restored_wall and state[0] and state[0].connected,30),'No fresh connected MAVROS state after recovery'
    final_clock=proxy_clock()
    observed=[r for r in state_history if start_wall<=r['wall']<=time.monotonic()]
    event('after_heartbeat_gap',phase=phase,requested_duration_sim=duration,
          measured_drop_sim=end_clock['px4_sim']-start_sim,
          measured_drop_wall=restored_wall-start_wall,
          measured_recovery_sim=final_clock['px4_sim']-end_clock['px4_sim'],
          observed_states=observed,mode=state[0].mode,armed=state[0].armed,
          acceptance_eligible=False,acceptance_limitation=acceptance_limitation)
    return observed
def cancel_worker():
    deadline=time.monotonic()+100
    while time.monotonic()<deadline:
        rows=packets()
        accepted=next((r for r in rows if r['kind']=='packet' and r.get('direction')=='px4_to_ros'
                       and r.get('mavpackettype')=='COMMAND_ACK' and r.get('command')==400 and r.get('result')==0),None)
        before=[r for r in rows if r['kind']=='arm_forwarded' and accepted and r['wall']<=accepted['wall']]
        found=before[-1] if before else None
        if found:
            due=found['wall']+a.offset_ms/1000
            while time.monotonic()<due:time.sleep(.002)
            event('sigint_during_arm',offset_ms=a.offset_ms)
            os.kill(os.getpid(),signal.SIGINT)
            return
        time.sleep(.005)
    event('cancel_trigger_timeout')

try:
    assert wait(lambda:state[0] and state[0].connected and pose[0] and truth,35),'No connected simulator'
    assert not state[0].armed
    def settled():
        return vision[0]>=10 and len(history)>=20 and history[-1][0]-history[0][0]>4 and max(z for _,z in history)-min(z for _,z in history)<.03
    assert wait(settled,90),'Ground vision did not settle'
    event('ground_ready',z=pose[0].pose.position.z,vision=vision[0],truth_z=truth[-1]['z'])
    assert wait(lambda:(out/'rc_observer.json').exists(),10)
    rc=json.loads((out/'rc_observer.json').read_text())
    assert rc['pass_rc'] and rc['rc_receiver_healthy'],'Independent RC not healthy'
    assert rc['parameters']['COM_OBL_RC_ACT']['after']==4,'Requires landing candidate action 4'
    event('rc_confirmed',channels=rc['channels'])
    prepared=json.loads((out/'flight_prepared.json').read_text())
    assert prepared['profile_applied'] and prepared['allow_flight']
    count=prepared['profile_count']
    assert count==len(flight_profile.INDOOR_ARUCO),'Flight profile only partially applied'
    event('profile_applied',count=count)
    initial=pose[0].pose.position.z;ground_truth=truth[-1]['z']
    if a.scenario=='cancel_before':
        event('sigint_before_navigate');os.kill(os.getpid(),signal.SIGINT)
    if a.scenario in ('cancel','ack_cancel'):
        trigger=threading.Thread(target=cancel_worker,daemon=True);trigger.start()
    sent=True
    event('navigate_sent',initial_z=initial,target_z=initial+.5)
    reply=drone.navigate(x=math.nan,y=math.nan,z=initial+.5,yaw=math.nan,speed=.2,frame_id='map',auto_arm=True)
    event('navigate_reply',success=reply.success,message=reply.message)
    if a.scenario in ('cancel_before','cancel','ack_cancel'):
        if a.scenario!='cancel_before':trigger.join(timeout=5)
        assert not reply.success and 'cancel' in reply.message.lower(),'Cancellation not acknowledged'
        reply_wall=time.monotonic()
        assert wait(lambda:state[0] and state_rx[0]>reply_wall and not state[0].armed,20),'Fresh disarm after cancel unconfirmed'
        if a.scenario=='cancel_before':
            assert not any(r['kind']=='arm_forwarded' for r in packets()),'ARM reached PX4 before cancellation'
        else:
            assert 'disarmed on the ground' in reply.message.lower(),'Non-forced ground DISARM not confirmed'
        rise=max(v['z'] for v in truth)-ground_truth
        event('cancel_verified',true_rise=rise)
        assert rise<.05,'Rise exceeds 5 cm'
        if a.scenario=='ack_cancel':
            holds=[r for r in packets() if r['kind']=='held_arm_ack' and r['result']==0]
            assert holds and holds[0]['delay']==4,'Accepted ARM ACK not delayed 4 s'
            assert any(r['kind']=='released_arm_ack' for r in packets()),'Delayed ACK was not released'
    else:
        assert reply.success,reply.message
        climb_reply_wall=time.monotonic()
        def physically_airborne():
            if state_rx[0]>climb_reply_wall:
                assert state[0].armed and state[0].mode=='OFFBOARD', 'Flight ended or left OFFBOARD before physical fault condition'
            return (state[0].armed and state[0].mode=='OFFBOARD'
                    and pose[0].pose.position.z>initial+.35 and truth
                    and time.monotonic()-truth[-1]['wall']<1 and truth[-1]['z']>ground_truth+.35)
        assert wait(physically_airborne,130),'No physical climb confirmed by Gazebo truth'
        event('airborne',estimated_z=pose[0].pose.position.z,truth_z=truth[-1]['z'])
        sim_wait(2)
        assert state[0].armed and state[0].mode=='OFFBOARD'
        assert truth[-1]['z']>ground_truth+.35,'Physical airborne condition lost'
        if a.scenario=='land':
            ok=drone.safe_land(timeout=120)
            event('safe_land_return',success=ok)
            assert ok is True
        elif a.scenario in ('kill','freeze'):
            fault_pid=own_pid('simple_offboard','/work/ws_package1b/install/')
            injection=event('injected_signal',pid=fault_pid,signal=a.scenario)
            os.kill(fault_pid,signal.SIGKILL if a.scenario=='kill' else signal.SIGSTOP)
            if a.scenario=='freeze':
                assert wait(lambda:clock[0]>=injection['sim']+2.,60),'Clock stalled during SIGSTOP'
                event('sigcont_before',pid=fault_pid)
                os.kill(fault_pid,signal.SIGCONT)
                resumed=True
                event('sigcont',pid=fault_pid,measured_pause_sim=clock[0]-injection['sim'])
            assert wait(lambda:state[0].mode=='AUTO.LAND',60),'No automatic LAND after offboard loss'
            # State is checked until disarm; no automatic return to OFFBOARD may occur while armed.
            end=time.monotonic()+150
            while state[0].armed and time.monotonic()<end:
                time.sleep(.05)
                current=state[0]
                assert not (current.armed and current.mode=='OFFBOARD'),'Unexpected armed OFFBOARD return'
            assert not state[0].armed
        elif a.scenario=='mavros_restart':
            fault_pid=own_pid('mavros','/work/ws_mavros214/install/')
            argv,env,cwd=capture_mavros(fault_pid)
            injected=event('injected_signal',pid=fault_pid,signal='kill_mavros',
                           restart_delay_sim=5.,autorespawn=False)
            os.kill(fault_pid,signal.SIGKILL)
            assert wait(lambda:stopped_or_zombie(fault_pid),10),'Recorded MAVROS PID did not stop'
            event('mavros_stopped',pid=fault_pid)
            assert wait(lambda:clock[0]>=injected['sim']+5.,120),'Clock stalled before timed MAVROS restart'
            assert not any('mavros_node' in p.read_bytes().decode(errors='replace') for p in Path('/proc').glob('[0-9]*/cmdline') if p.exists() and p.parent.name != str(fault_pid)), 'Unexpected automatic MAVROS respawn; refusing a second process'
            restart_log=(out/'mavros_restart.log').open('a')
            restarted_mavros=subprocess.Popen(argv,env=env,cwd=cwd,stdout=restart_log,
                                              stderr=subprocess.STDOUT,start_new_session=True)
            meta={'pid':restarted_mavros.pid,'pgid':restarted_mavros.pid,
                  'start_ticks':process_start_ticks(restarted_mavros.pid),'executable':argv[0]}
            (out/'mavros_restart.pid').write_text(str(restarted_mavros.pid)+'\n')
            (out/'extra_processes.json').write_text(json.dumps([meta],indent=2)+'\n')
            restarted=event('mavros_respawn',**meta,requested_delay_sim=5.,
                            measured_delay_sim=clock[0]-injected['sim'],
                            measured_delay_wall=time.monotonic()-injected['wall'])
            assert wait(lambda:state[0] and state[0].connected and state_rx[0]>restarted['wall'],45),'Restarted MAVROS did not reconnect'
            assert restarted_mavros.poll() is None,'Restarted MAVROS exited'
            assert wait(lambda:state[0].mode=='AUTO.LAND',90),'No failsafe LAND after MAVROS restart'
            end=time.monotonic()+150
            while state[0].armed and time.monotonic()<end:
                time.sleep(.05)
                current=state[0]
                assert not (current.armed and current.mode=='OFFBOARD'),'Armed OFFBOARD returned after MAVROS restart'
            assert not state[0].armed
        elif a.scenario=='pilot':
            direct_mode('POSCTL')
            assert wait(lambda:state[0].mode=='POSCTL',20)
            sim_wait(3)
            reply=drone.navigate(z=initial+.5,frame_id='map',auto_arm=False)
            event('pilot_command_refusal',success=reply.success,message=reply.message)
            assert not reply.success
            sim_wait(2);assert state[0].mode=='POSCTL'
            # Explicit cleanup is separate from the no-takeover assertion.
            direct_mode('AUTO.LAND');assert wait(lambda:not state[0].armed,150)
        elif a.scenario=='heartbeat':
            event('acceptance_excluded',reason=acceptance_limitation,
                  actual_mavros_conn_timeout_wall=10.,cpp_state_watchdog_sim=4.5)
            short=heartbeat_phase(3.5,'short')
            assert short and all(r['connected'] and r['armed'] and r['mode']=='OFFBOARD' for r in short), 'Short 3.5 sim-second heartbeat gap interrupted OFFBOARD; see wall/simulation timeout mismatch'
            sim_wait(2.)
            long=heartbeat_phase(5.,'long')
            first_land=next((r for r in long if r['armed'] and r['mode']=='AUTO.LAND'),None)
            if first_land is None:
                assert wait(lambda:state[0] and state[0].connected and state[0].armed and state[0].mode=='AUTO.LAND',60),'Long heartbeat gap did not result in AUTO.LAND'
                first_land={'wall':state_rx[0]}
            event('heartbeat_failsafe_land',phase='long',first_land_wall=first_land['wall'])
            end=time.monotonic()+150
            while time.monotonic()<end:
                after_land=[r for r in state_history if r['wall']>=first_land['wall']]
                assert not any(r['armed'] and r['mode']=='OFFBOARD' for r in after_land), 'Armed OFFBOARD returned after heartbeat failsafe'
                current=state[0]
                if current and current.connected and not current.armed:break
                time.sleep(.05)
            assert state[0] and state[0].connected and not state[0].armed, 'Long heartbeat failsafe did not disarm'
            event('heartbeat_sequence_completed',acceptance_eligible=False,
                  reason=acceptance_limitation)
    assert wait(lambda:state[0] and not state[0].armed,30)
    sim_wait(2,30)
    event('disarmed',mode=state[0].mode,truth_z=truth[-1]['z'])
    if False:  # Parent independently verifies all 19 after this driver exits.
        event('profile_readback_wait',count=14,cleanup_service_not_called=True)
        assert wait(profile_restoration_complete,35),'All 14 profile values were not independently restored before cleanup'
        observed=json.loads((out/'rc_observer.json').read_text())
        event('profile_readback_verified',count=14,
              observer_completed_wall=observed['profile_restore_completed_wall'],
              cleanup_service_not_called=True)
    passed=True
except BaseException as e:
    event('failure',message=str(e),type=type(e).__name__)
finally:
    proxy_directive({})
    if fault_pid and a.scenario=='freeze' and not resumed:
        try:os.kill(fault_pid,signal.SIGCONT)
        except ProcessLookupError:pass
    if sent and not passed:
        try:
            if wait(lambda:state[0] and state[0].connected,15) and state[0].armed:
                event('explicit_cleanup_land');direct_mode('AUTO.LAND')
                wait(lambda:not state[0].armed,120)
        except Exception as e:event('cleanup_failure',message=str(e))
    # Keep MAVROS alive while the parameter gate restores its journal. This is
    # test teardown, not a replacement for the independently observed disarm edge.
    if False:  # Parent retains transport until journal + independent 19-value proof.
        try:
            if revert.wait_for_service(timeout_sec=3):
                f=revert.call_async(Trigger.Request())
                assert wait(f.done,20),'Parameter-gate cleanup timed out'
                event('parameter_cleanup_reply',success=f.result().success,message=f.result().message)
        except Exception as e:event('parameter_cleanup_failure',message=str(e))
    rows=packets()
    (out/'gate_result.json').write_text(json.dumps({'pass':passed,'scenario':a.scenario,'offset_ms':a.offset_ms,
        'diagnostic_start':True,'acceptance_eligible':acceptance_eligible,
        'acceptance_limitation':acceptance_limitation,
        'events':events,'arm_forwarded_count':sum(r['kind']=='arm_forwarded' for r in rows)},indent=2)+'\n')
    (out/'groundtruth.json').write_text(json.dumps(truth)+'\n')
    monitor.shutdown();monitor_thread.join(timeout=3);n.destroy_node();drone._shutdown()
    if False:  # Parent owns restarted MAVROS until all-19 verification completes.
        # This exact process belongs to the timed S4 restart and has its own SID.
        # Never stop another launch or an unrecorded PID.
        os.kill(restarted_mavros.pid,signal.SIGINT)
        try:restarted_mavros.wait(timeout=10)
        except subprocess.TimeoutExpired:
            restarted_mavros.terminate()
            try:restarted_mavros.wait(timeout=5)
            except subprocess.TimeoutExpired:
                restarted_mavros.kill();restarted_mavros.wait(timeout=5)
        (out/'mavros_restart_stopped.json').write_text(json.dumps({'pid':restarted_mavros.pid,'returncode':restarted_mavros.returncode})+'\n')
    if restart_log is not None:restart_log.close()
if not passed:raise SystemExit(1)
