"""Even land_only_in_offboard=false cannot take over an armed pilot mode."""
import os,sys,time,threading,unittest
try:
    import launch, launch_ros.actions, launch_testing, launch_testing.actions, launch_testing.asserts, pytest, rclpy
    from rclpy.executors import MultiThreadedExecutor
    from std_srvs.srv import Trigger
except ImportError as e:raise unittest.SkipTest(str(e))
sys.path.insert(0,os.path.dirname(__file__))
from test_safety import TEST_NS,topic,guard_graph
from fake_mavros import FakeMavros
from executor_support import CooperativeExecutor as MultiThreadedExecutor
LAUNCHED=False
@pytest.mark.launch_test
def generate_test_description():
    global LAUNCHED
    guard_graph();LAUNCHED=True
    node=launch_ros.actions.Node(package='bumblebee',executable='simple_offboard',
        name='simple_offboard_tested',namespace=TEST_NS,output='screen',
        parameters=[{'land_only_in_offboard':False}],
        remappings=[('/tf',topic('/tf')),('/tf_static',topic('/tf_static')),
                    (topic('/mavros/local_position/pose'),topic('/mavros/mavros/pose'))])
    return launch.LaunchDescription([node,launch_testing.actions.ReadyToTest()]),{'simple_offboard':node}
class TestPilot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not LAUNCHED:raise unittest.SkipTest('launch_test required')
        rclpy.init();cls.fake=FakeMavros();cls.node=rclpy.create_node('land_pilot_test')
        cls.client=cls.node.create_client(Trigger,topic('land'))
        cls.executor=MultiThreadedExecutor(num_threads=4)
        cls.executor.add_node(cls.fake);cls.executor.add_node(cls.node)
        cls.thread=threading.Thread(target=cls.executor.spin,daemon=True);cls.thread.start()
        assert cls.client.wait_for_service(timeout_sec=20)
    @classmethod
    def tearDownClass(cls):
        cls.executor.shutdown();cls.thread.join(timeout=5)
        cls.fake.destroy_node();cls.node.destroy_node();rclpy.shutdown()
    def land(self):
        f=self.client.call_async(Trigger.Request());end=time.monotonic()+12
        while not f.done() and time.monotonic()<end:time.sleep(.01)
        self.assertTrue(f.done());return f.result()
    def test_pilot_modes_are_protected(self):
        for mode in ['POSCTL','ALTCTL','AUTO.LOITER','AUTO.RTL','AUTO.LAND']:
            with self.subTest(mode=mode):
                self.fake.reset(armed=True,mode=mode);self.fake.publish_state();time.sleep(.4)
                reply=self.land();self.assertFalse(reply.success)
                self.assertEqual(self.fake.snapshot('mode_requests'),[])
                self.assertEqual(self.fake.snapshot('arming_requests'),[])
    def test_offboard_and_disarmed_paths(self):
        for armed,mode in [(True,'OFFBOARD'),(False,'POSCTL')]:
            with self.subTest(armed=armed):
                self.fake.reset(armed=armed,mode=mode);self.fake.publish_state();time.sleep(.4)
                reply=self.land();self.assertTrue(reply.success,reply.message)
                self.assertEqual(self.fake.snapshot('mode_requests'),['AUTO.LAND'])
                self.assertEqual(self.fake.snapshot('arming_requests'),[])
@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):
    def test_exit_code(self,proc_info):launch_testing.asserts.assertExitCodes(proc_info)
