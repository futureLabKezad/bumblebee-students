"""Absolute RPC latency with a five-second telemetry wait, in an isolated subprocess."""
import os,sys,time,json,threading,subprocess,math,tempfile,unittest
from pathlib import Path
try:
    import rclpy
    from rclpy.executors import MultiThreadedExecutor,SingleThreadedExecutor
    from bumblebee import srv
    from std_srvs.srv import Trigger
    from ament_index_python.packages import get_package_prefix
except ImportError as e:raise unittest.SkipTest(str(e))
from fake_mavros import FakeMavros
from test_safety import TEST_NS,topic,guard_graph
from executor_support import CooperativeExecutor as MultiThreadedExecutor

def test_rpc_latency():
    env=dict(os.environ,ROS_DOMAIN_ID='89',ROS_LOCALHOST_ONLY='1',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',FASTDDS_BUILTIN_TRANSPORTS='UDPv4')
    result=subprocess.run([sys.executable,__file__,'--worker'],env=env,capture_output=True,text=True,timeout=110)
    assert result.returncode==0,result.stdout+result.stderr
    print(result.stdout)

if __name__=='__main__':
    assert '--worker' in sys.argv
    assert os.environ.get('ROS_LOCALHOST_ONLY')=='1' and os.environ.get('ROS_DOMAIN_ID')=='89'
    guard_graph();rclpy.init();fake=FakeMavros(armed=True,mode='OFFBOARD',pose=(0.,0.,1.))
    binary=str(Path(get_package_prefix('bumblebee'))/'lib/bumblebee/simple_offboard')
    args=[binary,'--ros-args','-r','__ns:='+TEST_NS,'-r','__node:=simple_offboard_tested','-r','/tf:='+topic('/tf'),'-r','/tf_static:='+topic('/tf_static'),'-r',topic('/mavros/local_position/pose')+':='+topic('/mavros/mavros/pose'),'-r',topic('/mavros/setpoint_position/local')+':='+topic('/mavros/mavros/local')]
    import tempfile
    log=tempfile.TemporaryFile(mode='w+')
    proc=subprocess.Popen(args+['-p','telemetry_transform_timeout:=5.0'],stdout=log,stderr=subprocess.STDOUT)
    node=rclpy.create_node('latency_client');clients={name:node.create_client(typ,topic(name)) for name,typ in [('navigate',srv.Navigate),('get_telemetry',srv.GetTelemetry),('release',Trigger)]}
    ef=MultiThreadedExecutor(num_threads=4);ef.add_node(fake);ec=SingleThreadedExecutor();ec.add_node(node)
    threads=[threading.Thread(target=e.spin,daemon=True) for e in [ef,ec]]
    for t in threads:t.start()
    def await_future(f):
     end=time.monotonic()+10
     while not f.done() and time.monotonic()<end:time.sleep(.001)
     assert f.done();return f.result()
    try:
     for c in clients.values():assert c.wait_for_service(timeout_sec=20)
     time.sleep(1)
     rows=[]
     for i in range(8):
      req=srv.Navigate.Request();req.x=2.;req.y=0.;req.z=1.;req.yaw=math.nan;req.speed=.5;req.frame_id='map';req.auto_arm=False
      start=time.monotonic();reply=await_future(clients['navigate'].call_async(req));assert reply.success,reply.message
      baseline=time.monotonic()-start
      tr=srv.GetTelemetry.Request();tr.frame_id='no_such_frame';f=clients['get_telemetry'].call_async(tr);time.sleep(.05)
      start=time.monotonic();reply=await_future(clients['navigate'].call_async(req));assert reply.success,reply.message
      rows.append({'baseline':baseline,'with_telemetry':time.monotonic()-start,'telemetry_done':f.done()})
      await_future(f);await_future(clients['release'].call_async(Trigger.Request()));time.sleep(.5)
     assert len(rows)==8 and max(r['with_telemetry'] for r in rows)<.3,rows
     assert all(not r['telemetry_done'] for r in rows),rows
     print(json.dumps(rows))
    finally:
     proc.send_signal(__import__('signal').SIGINT);proc.wait(timeout=10);log.seek(0);print(log.read());log.close()
     ef.shutdown();ec.shutdown()
     for t in threads:t.join(timeout=5)
     fake.destroy_node();node.destroy_node();rclpy.shutdown()
