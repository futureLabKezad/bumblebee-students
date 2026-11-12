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
p.add_argument('--scenario',choices=['land','kill','freeze','mavros_restart','pilot','cancel_before','cancel','ack_cancel','heartbeat','guard_hold','cleanup_hold'],required=True)
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
from cleanup_land import cleanup_land  # flight_trial_18
import s4_oracle  # S4 oracle: PX4's own AUTO.LAND from proxy HEARTBEAT rows
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
def event(kind,wall=None,**kw):
    # flight_trial_20: a caller may pass the wall it read immediately before its action (the cancel SIGINT)
    wall=time.monotonic() if wall is None else wall
    item={'wall':wall,'elapsed':wall-start,'sim':clock[0],'kind':kind,**kw}
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
land_srv=n.create_client(Trigger,'/land')  # cleanup only (flight_trial_18); the SDK keeps its own client
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
    assert argv[0].startswith(os.environ['C8_MAVROS_INSTALL'].rstrip('/')+'/') and argv[0].endswith('/mavros_node')  # c8: MAVROS parameter
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
class ProxyTail:
    """flight_trial_20 (cancel timing): incremental reader of mavlink_proxy.jsonl. read() returns only rows appended since
    the previous call whose line can be an arm_forwarded, COMMAND_ACK or heartbeat_forwarded row (byte prefilter; the exact
    selection is made on the decoded row by CancelTiming). A last line without its newline is kept until it is complete
    (same rule as packets()). Replaces the full re-read and parse of the whole file every 5 ms (1-3 ms GIL per poll).
    A file that shrank or was replaced after open raises (the proxy only appends): a declared trigger failure."""
    KEYS=(b'"arm_forwarded"',b'"COMMAND_ACK"',b'"heartbeat_forwarded"')
    def __init__(self,path):
        self.path=path;self.stream=open(path,'rb',buffering=0);self.partial=b''
    def read(self):
        data=self.stream.read()
        if not data:
            st=os.fstat(self.stream.fileno())
            if st.st_size<self.stream.tell() or os.stat(self.path).st_ino!=st.st_ino:
                raise RuntimeError('mavlink_proxy.jsonl shrank or was replaced while the cancel trigger read it')
            return []
        lines=(self.partial+data).split(b'\n');self.partial=lines.pop()
        return [json.loads(line) for line in lines if any(key in line for key in self.KEYS)]
    def close(self):
        self.stream.close()
class CancelTiming:
    """flight_trial_20: cancel trigger decision without ROS or gate globals (tests run it on recorded proxy files).
    Reference = legacy verifier cancel_offset_observed: the last ARM the proxy forwarded before the first ACCEPTED ARM ACK
    (packet px4_to_ros COMMAND_ACK command 400 result 0); target = reference wall + offset. The only precondition is the
    scenario's own: navigate(auto_arm) has not returned. armed = the first source-identified FCU HEARTBEAT (1/1,
    autopilot 12) reporting ARMED after the reference ARM, kept as context: simple_offboard still honours a cancel after
    PX4 reports ARMED until its next 10 Hz tick commits the takeoff, so a SIGINT then is judged as a product result."""
    def __init__(self,offset_ms):
        self.offset=offset_ms/1000.;self.last_arm=None;self.reference=None;self.accepted=None
        self.armed_since_arm=None;self.armed=None
    def feed(self,rows):
        for r in rows:
            kind=r.get('kind')
            if kind=='heartbeat_forwarded':
                if (r.get('armed') is True and r.get('source_system')==1 and r.get('source_component')==1
                        and r.get('autopilot')==12):
                    if self.accepted is None:
                        if self.last_arm is not None and self.armed_since_arm is None:self.armed_since_arm=r
                    elif self.armed is None:self.armed=r
            elif self.accepted is None:
                if kind=='arm_forwarded':self.last_arm=r;self.armed_since_arm=None
                elif (kind=='packet' and r.get('direction')=='px4_to_ros' and r.get('mavpackettype')=='COMMAND_ACK'
                      and r.get('command')==400 and r.get('result')==0):
                    self.accepted=r;self.reference=self.last_arm;self.armed=self.armed_since_arm
    def due(self):
        return self.reference['wall']+self.offset
    def closed(self,navigate_returned):
        """Scenario precondition 'SIGINT while navigate(auto_arm) runs': reasons it no longer holds (empty = holds)."""
        return ['navigate_returned'] if navigate_returned else []
cancel_state={'navigate_done_wall':None,'classification':None}
navigate_done=threading.Event()
# flight_trial_20 navigate slot (scenario cancel, offset >= SLOT_MIN_OFFSET_MS only): navigate goes out while PX4's last
# forwarded HEARTBEAT and the gate's last MAVROS State are both SLOT_MIN_S..SLOT_MAX_S old. simple_offboard sends its ARM
# at once only with a State <= 0.30 s old, before any setpoint reached PX4; PX4 rejects that ARM and the 2 s retry lands
# at a random HEARTBEAT phase. After a retry ARM PX4 reported ARMED >= 0.708 s later in 233 saved runs, so only offsets
# >= 600 ms can meet it. Offset 900, 4/14 failed runs, all after a retry ARM: in 3 navigate returned success at
# 0.82-0.83 s, before the SIGINT (now a declared HARNESS RACE); in c08_cancel_off900_13 the SIGINT came 2 ms after
# simple_offboard's estimated commit tick and 22 ms before the success reply (judged as a product result; the SDK's 50 ms
# poll in _call_auto_arm is the known Ctrl+C finding P2). Lower offsets keep the retry path in coverage. Age >= 0.304 s
# gave an accepted first ARM in 144/144 saved runs, and then PX4 reported ARMED >= 0.906 s after the ARM (commit at the
# +1.0 s tick); the upper bound keeps the next HEARTBEAT (period >= 0.999 s) out of reach of the first 10 Hz poll.
SLOT_MIN_S=.40;SLOT_MAX_S=.80;SLOT_MIN_OFFSET_MS=600
def last_px4_heartbeat_wall(rows):
    """flight_trial_20: wall of the last forwarded PX4 HEARTBEAT (1/1, autopilot 12) in proxy rows, or None."""
    beats=[r['wall'] for r in rows if r.get('kind')=='heartbeat_forwarded' and r.get('source_system')==1
           and r.get('source_component')==1 and r.get('autopilot')==12]
    return beats[-1] if beats else None
def navigate_slot_ok(heartbeat_age,state_age):
    """flight_trial_20: both ages (s) inside the navigate slot; a missing PX4 HEARTBEAT is never a slot."""
    return (heartbeat_age is not None and SLOT_MIN_S<=heartbeat_age<=SLOT_MAX_S
            and SLOT_MIN_S<=state_age<=SLOT_MAX_S)
def cancel_stimulus_verdict(events,reply_success,trigger_alive,navigate_done_wall):
    """flight_trial_20: the cancel stimulus is judged BEFORE the product asserts. Returns (harness_classification,
    message) when the run must fail as a declared harness problem, None when the product asserts judge it. Never a pass.
    - trigger still running after its join, or an exception in it: HARNESS FAILURE;
    - navigate returned success after PX4 reported ARMED and before the SIGINT (no SIGINT sent because navigate had
      returned, or a SIGINT that came after the return): HARNESS RACE - the takeoff was legitimately committed before the
      requested offset. A failure reply, or a success without an ARMED PX4 heartbeat before the return, is a product result;
    - SIGINT sent while navigate ran: HARNESS TIMING if |offset error| > 20 ms (the legacy verifier's cancel_offset_observed
      rule), else the product is judged (also when PX4 already reported ARMED: simple_offboard still honours the cancel
      until its next 10 Hz tick commits);
    - no SIGINT because of an accepted ARM ACK without a forwarded ARM before it, or no accepted ARM ACK recorded in 100 s
      while navigate later returned success: HARNESS FAILURE (recording problem);
    - navigate returned before an accepted ARM ACK, or a failure reply after the 100 s trigger timeout: product result.
    Known limit: navigate_done_wall is the SDK return, up to 50 ms after the reply reached it (drone.py polls every 50 ms)."""
    first=lambda kind:next((e for e in events if e['kind']==kind),None)
    if trigger_alive:
        return 'harness_cancel_trigger_running','HARNESS FAILURE (declared, not a product result): cancel trigger still running after navigate'
    broken=first('cancel_trigger_failure')
    if broken:
        return 'harness_cancel_trigger_failure','HARNESS FAILURE (declared, not a product result): cancel trigger: '+broken['message']
    def committed_first(armed):
        return reply_success and armed is not None and navigate_done_wall is not None and armed<=navigate_done_wall
    sig=first('sigint_during_arm')
    if sig:
        if navigate_done_wall is not None and sig['wall']>=navigate_done_wall and committed_first(sig['armed_heartbeat_wall']):
            return ('harness_race_sigint_after_return','HARNESS RACE (declared, not a product result): PX4 reported ARMED and '
                    'navigate returned success before the SIGINT')
        if abs(sig['offset_error_ms'])>20.:
            return ('harness_offset_error_over_20ms','HARNESS TIMING (declared, not a product result): SIGINT %.1f ms from '
                    'the requested offset (limit 20 ms); see sigint_during_arm'%sig['offset_error_ms'])
        return None
    closed=first('cancel_window_closed')
    if closed:
        if committed_first(closed['armed_heartbeat_wall']):
            return ('harness_race_cancel_window_closed','HARNESS RACE (declared, not a product result): PX4 reported ARMED and '
                    'navigate returned success before the requested cancel offset; no SIGINT was sent')
        return None
    stopped=first('cancel_trigger_stopped')
    if stopped and stopped['reason']=='accepted ARM ACK without a preceding forwarded ARM':
        return 'harness_cancel_trigger_stopped','HARNESS FAILURE (declared, not a product result): '+stopped['reason']+'; no SIGINT was sent'
    if first('cancel_trigger_timeout') and reply_success:
        return ('harness_cancel_trigger_timeout','HARNESS FAILURE (declared, not a product result): no accepted ARM ACK '
                'recorded in 100 s although navigate returned success; no SIGINT was sent')
    return None
def cancel_worker():
    """flight_trial_20. Unchanged: reference and target (see CancelTiming), os.kill(SIGINT) of this process, 100 s deadline.
    Changed: incremental proxy tail (0.2 ms polls for 0.1 s after each forwarded ARM, else 2 ms); the last 4 ms before the
    target in 0.1 ms steps; the event wall is read immediately before os.kill and the event file I/O follows the signal;
    no SIGINT once navigate has returned (event cancel_window_closed). The worker only records; the gate judges the
    stimulus with cancel_stimulus_verdict before the product asserts."""
    timing=CancelTiming(a.offset_ms);tail=None
    try:
        tail=ProxyTail(out/'mavlink_proxy.jsonl');deadline=time.monotonic()+100
        while True:
            timing.feed(tail.read())
            if timing.accepted is not None:break
            if navigate_done.is_set():
                timing.feed(tail.read())  # the accepted ACK row may have been written since the read above
                if timing.accepted is not None:break
                event('cancel_trigger_stopped',reason='navigate returned before an accepted ARM ACK');return
            if time.monotonic()>deadline:
                event('cancel_trigger_timeout');return
            recent=timing.last_arm is not None and time.monotonic()-timing.last_arm['wall']<.1
            time.sleep(.0002 if recent else .002)
        detected=time.monotonic()
        if timing.reference is None:
            event('cancel_trigger_stopped',reason='accepted ARM ACK without a preceding forwarded ARM');return
        due=timing.due()
        while True:
            timing.feed(tail.read())
            reasons=timing.closed(navigate_done.is_set())
            now=time.monotonic()
            if reasons or now>=due:break
            time.sleep(.002 if due-now>.004 else .0001)
        reference=timing.reference['wall'];accepted=timing.accepted['wall']
        armed=timing.armed['wall'] if timing.armed else None
        if reasons:
            event('cancel_window_closed',offset_ms=a.offset_ms,reasons=reasons,target_wall=due,
                  reference_arm_forwarded_wall=reference,accepted_ack_wall=accepted,armed_heartbeat_wall=armed,
                  navigate_done_wall=cancel_state['navigate_done_wall'])
            return
        wall=time.monotonic()
        os.kill(os.getpid(),signal.SIGINT)
        returned=time.monotonic()
        error=(wall-reference)*1000-a.offset_ms
        event('sigint_during_arm',wall=wall,offset_ms=a.offset_ms,target_wall=due,
              reference_arm_forwarded_wall=reference,accepted_ack_wall=accepted,ack_detected_wall=detected,
              ack_latency_ms=(accepted-reference)*1000,observed_offset_ms=(wall-reference)*1000,offset_error_ms=error,
              armed_heartbeat_wall=armed,px4_reported_armed_before_sigint=armed is not None,
              kill_returned_wall=returned,wall_basis='CLOCK_MONOTONIC read immediately before os.kill; event I/O after it')
    except Exception as e:
        event('cancel_trigger_failure',message=str(e),type=type(e).__name__)
    finally:
        if tail is not None:tail.close()

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
    slot_checked=None
    if a.scenario=='cancel' and a.offset_ms>=SLOT_MIN_OFFSET_MS:
        # flight_trial_20: stimulus timing only (see SLOT_MIN_S); the ages are read once per check, the slot is checked
        # again after the event I/O and those ages go into navigate_sent; the first ARM result is recorded either way
        def slot_ages():
            beat=last_px4_heartbeat_wall(packets());now=time.monotonic()
            return (now-beat if beat is not None else None),now-state_rx[0]
        slot_end=time.monotonic()+5
        while True:
            ages=slot_ages()
            if navigate_slot_ok(*ages):
                event('navigate_phase',heartbeat_age_s=ages[0],state_age_s=ages[1])
                ages=slot_ages()
                if navigate_slot_ok(*ages):
                    slot_checked=list(ages);break
            if time.monotonic()>slot_end:
                cancel_state['classification']='harness_no_navigate_slot'
                raise AssertionError('HARNESS (declared, not a product result): no navigate slot (PX4 HEARTBEAT and State '
                                     '0.40-0.80 s old) in 5 s')
            time.sleep(.02)
    if a.scenario in ('cancel','ack_cancel'):
        trigger=threading.Thread(target=cancel_worker,daemon=True);trigger.start()
    sent=True
    nav_sent=event('navigate_sent',initial_z=initial,target_z=initial+.5,slot_ages_s=slot_checked)
    try:
        reply=drone.navigate(x=math.nan,y=math.nan,z=initial+.5,yaw=math.nan,speed=.2,frame_id='map',auto_arm=True)
    finally:
        cancel_state['navigate_done_wall']=time.monotonic();navigate_done.set()  # flight_trial_20: before any event I/O
    event('navigate_reply',success=reply.success,message=reply.message)
    if a.scenario=='cancel':
        acks=[r for r in packets() if r.get('kind')=='packet' and r.get('direction')=='px4_to_ros'
              and r.get('mavpackettype')=='COMMAND_ACK' and r.get('command')==400 and r['wall']>=nav_sent['wall']]
        event('first_arm_result',result=acks[0].get('result') if acks else None,ack_wall=acks[0]['wall'] if acks else None)
    if a.scenario in ('cancel_before','cancel','ack_cancel'):
        if a.scenario!='cancel_before':
            trigger.join(timeout=5)
            verdict=cancel_stimulus_verdict(list(events),reply.success,trigger.is_alive(),cancel_state['navigate_done_wall'])
            if verdict:
                cancel_state['classification']=verdict[0]
                raise AssertionError(verdict[1])
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
        if a.scenario!='cancel_before':
            # flight_trial_20: a run without the stimulus is never a pass, whatever the reply says
            assert any(e['kind']=='sigint_during_arm' for e in events),'No SIGINT during auto_arm in this run (no stimulus; never a pass)'
    elif a.scenario in ('guard_hold','cleanup_hold'):
        # flight_trial_18 (s7fix-07): an SDK guard, or the cleanup after a failure, acts while simple_offboard still holds
        # the vehicle on the ground (1.5 s after the arm). Both must stop the motors through /land, never AUTO.LAND.
        assert reply.success,reply.message
        if a.scenario=='cleanup_hold':
            # the cleanup acts only on an armed state of the gate's own copy (separate delivery from the SDK reply)
            assert wait(lambda:state[0] and state[0].armed,1),'Gate state not armed within 1 s of the takeoff reply'
            event('deliberate_failure_in_ground_hold')
            raise AssertionError('Deliberate failure in the ground hold: the cleanup must stop the motors')
        def sdk_offboard():
            s=drone.get_fcu_status();return s['ok'] and s['connected'] and s['armed'] and s['mode']=='OFFBOARD'
        assert wait(sdk_offboard,.5),'SDK state not armed in OFFBOARD within 0.5 s of the takeoff reply'
        guard_wall=event('guard_action_called',function='drone._land_if_offboard')['wall']
        drone._land_if_offboard()
        event('guard_action_returned',armed=bool(state[0].armed),mode=state[0].mode)
        assert wait(lambda:state[0] and state_rx[0]>guard_wall and not state[0].armed,10),'No disarm within 10 s of the guard action'
        first=next((r for r in state_history if r['wall']>guard_wall and not r['armed']),None)
        land_states=[r for r in state_history if r['wall']>=guard_wall and r['armed'] and r['mode']=='AUTO.LAND']
        rise=max(v['z'] for v in truth)-ground_truth
        event('guard_hold_verified',true_rise=rise,disarm_after_s=(first['wall'] if first else state_rx[0])-guard_wall,
              armed_auto_land_states=len(land_states))
        assert rise<.05,'Rise exceeds 5 cm'
        assert not land_states,'Armed AUTO.LAND seen: the guard did not take the ground-hold path'
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
            fault_pid=own_pid('simple_offboard',os.environ['C8_PRODUCT_INSTALL'].rstrip('/')+'/')  # c8: product parameter
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
            fault_pid=own_pid('mavros',os.environ['C8_MAVROS_INSTALL'].rstrip('/')+'/')  # c8: MAVROS parameter
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
            # S4 oracle: the failsafe AUTO.LAND is PX4's own mode, from the proxy's source-identified PX4 HEARTBEAT rows
            # (custom_mode main 4 AUTO, sub 6 LAND). A restarted MAVROS prints its first HEARTBEAT as CMODE(100925440)
            # and PX4 can disarm before its second one (INT_flight_pc_bp02cmd_mavros_restart_06), so the decoded text
            # alone can miss a real landing. Every MAVROS report must still agree with PX4: s4_oracle.judge on the full
            # record decides; the waits below only let the record complete.
            fault_wall=injected['wall']
            land=s4_oracle.poll(packets,lambda rows:s4_oracle.first_land(rows,fault_wall),90)
            assert land,'No PX4 failsafe AUTO.LAND heartbeat after the MAVROS kill'
            event('px4_failsafe_land',source='proxy heartbeat, PX4 1/1 autopilot 12',heartbeat_wall=land['wall'],
                  px4_sim_at_receipt=land['px4_sim'],custom_mode=land['custom_mode'],main_mode=s4_oracle.main_mode(land['custom_mode']),
                  sub_mode=s4_oracle.sub_mode(land['custom_mode']),before_respawn=land['wall']<restarted['wall'])
            end=time.monotonic()+150
            while state[0].armed and time.monotonic()<end:
                time.sleep(.05)
                current=state[0]
                assert not (current.armed and current.mode=='OFFBOARD'),'Armed OFFBOARD returned after MAVROS restart'
            assert not state[0].armed
            disarm=s4_oracle.poll(packets,lambda rows:s4_oracle.first_disarm(rows,fault_wall),30)
            assert disarm,'No PX4 disarmed heartbeat after the failsafe AUTO.LAND'
            decoded=s4_oracle.poll(lambda:(packets(),list(state_history)),
                                   lambda record:s4_oracle.decoded_after(record[0],record[1],disarm['wall']),10)
            reports=[dict(r) for r in list(state_history) if r['wall']>restarted['wall']]
            problem=s4_oracle.judge(packets(),reports,fault_wall,restarted['wall'])
            event('px4_failsafe_disarm',heartbeat_wall=disarm['wall'],px4_sim_at_receipt=disarm['px4_sim'],
                  custom_mode=disarm['custom_mode'],restarted_states=reports,decoded_state=decoded,
                  mavros_decoded_auto_land=any(r['armed'] and r['mode']=='AUTO.LAND' for r in reports),problem=problem)
            assert problem is None,problem
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
                cleanup_wall=event('explicit_cleanup_land')['wall']
                # flight_trial_18: /land first (cleanup_land.py: a DISARM in the ground hold, AUTO.LAND in flight)
                def call_land():
                    assert land_srv.wait_for_service(timeout_sec=3),'/land unavailable'
                    f=land_srv.call_async(Trigger.Request())
                    assert wait(f.done,10),'/land response timeout'
                    return f.result().success,f.result().message
                final=cleanup_land(lambda:state[0] and (state[0].connected,state[0].armed,state[0].mode),call_land,
                                   lambda:direct_mode('AUTO.LAND'),wait,event,direct=a.scenario=='pilot')
                event('cleanup_done',armed=bool(final and final[1]),mode=final and final[2],
                      after_s=time.monotonic()-cleanup_wall)
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
        'acceptance_limitation':acceptance_limitation,'harness_classification':cancel_state['classification'],
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
