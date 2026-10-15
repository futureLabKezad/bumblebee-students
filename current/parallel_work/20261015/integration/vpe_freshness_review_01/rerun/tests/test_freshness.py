"""Execute pinned original VPE methods against deterministic in-memory ROS stubs.
No ROS import/init, timers scheduled but never spun, no transport/parameter IO.
"""
import sys
sys.dont_write_bytecode = True
import ast,copy,hashlib,importlib.util,json,threading,types,unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace as NS
HERE=Path(__file__).resolve().parents[1]; VISION=Path('/Users/arsenij/Documents/Bumbl code/bbsim-work/parallel_work/20261015/vision'); ROOT=Path('/Users/arsenij/Documents/Bumbl code/bbsim-work')
PIN=VISION/'baseline/vpe_fix.py'; SOURCE=PIN.read_bytes()
assert hashlib.sha256(SOURCE).hexdigest()=='c33a52bf1b10bc064ca102bdc720ed03afaa08c691d9c5c34b1d7fadf859b8b9'
spec=importlib.util.spec_from_file_location('freshness_candidate',HERE/'candidate/vpe_freshness_optin.py');candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
NS_PER_S=1_000_000_000
class Time:
    def __init__(self,*,nanoseconds=0,clock_type='ROS_TIME'):
        self.nanoseconds=int(nanoseconds);self.clock_type=clock_type
    def __sub__(self,other):
        assert self.clock_type==other.clock_type
        return NS(nanoseconds=self.nanoseconds-other.nanoseconds)
    def to_msg(self):return NS(sec=self.nanoseconds//NS_PER_S,nanosec=self.nanoseconds%NS_PER_S)
class Clock:
    def __init__(self):self.ns=10*NS_PER_S;self.clock_type='ROS_TIME';self.hook=None
    def now(self):
        if self.hook:self.hook()
        return Time(nanoseconds=self.ns,clock_type=self.clock_type)
    def set(self,sec):self.ns=round(sec*NS_PER_S)
class Pose:
    def __init__(self,x=0.,y=0.,z=.2):self.position=NS(x=x,y=y,z=z);self.orientation=NS(x=0.,y=0.,z=0.,w=1.)
class Message:
    def __init__(self):self.header=NS(stamp=NS(sec=0,nanosec=0),frame_id='map');self.pose=NS(pose=Pose(),covariance=[0.]*36)
class Publisher:
    def __init__(self):self.messages=[]
    def publish(self,msg):self.messages.append(copy.deepcopy(msg))
class Node:
    def __init__(self,name):self.clock=Clock();self.logs=[];self.services=[];self.timers=[];self.subscriptions=[];self.clients=[]
    def get_clock(self):return self.clock
    def get_logger(self):return NS(info=lambda *a,**k:self.logs.append(('info',a)),warn=lambda *a,**k:self.logs.append(('warn',a)),error=lambda *a,**k:self.logs.append(('error',a)))
    def create_publisher(self,*a,**k):return Publisher()
    def create_client(self,*a,**k):self.clients.append((a,k));return NS()
    def create_service(self,*a,**k):self.services.append((a,k));return NS()
    def create_subscription(self,*a,**k):self.subscriptions.append((a,k));return NS()
    def create_timer(self,*a,**k):self.timers.append((a,k));return NS(cancel=lambda:None)
class QoS:
    def __init__(self,*a,**k):pass
# Entire original class body, exact methods and constants, no imports or main.
tree=ast.parse(SOURCE);body=[x for x in tree.body if isinstance(x,(ast.Assign,ast.ClassDef))]
ENV=dict(__name__='pinned_c33_fixture',Node=Node,threading=threading,deque=deque,PoseWithCovarianceStamped=Message,QoSProfile=QoS,MutuallyExclusiveCallbackGroup=lambda:NS(),ReentrantCallbackGroup=lambda:NS(),ReliabilityPolicy=NS(RELIABLE=1),DurabilityPolicy=NS(TRANSIENT_LOCAL=1))
for name in ('ParamSetV2','ParamPull','ParameterEvent','State','MarkerArray','Int32','Bool','SetParam','Trigger'):ENV[name]=type(name,(),{})
exec(compile(ast.Module(body=body,type_ignores=[]),str(PIN),'exec'),ENV);Base=ENV['VpeFix'];Fresh=candidate.make_node_class(Base,enabled=True)
def msg(stamp,x=0.,z=.2,cov=None):
    m=Message();m.header.stamp=Time(nanoseconds=round(stamp*NS_PER_S)).to_msg();m.pose.pose=Pose(x=x,z=z)
    if cov is not None:m.pose.covariance=list(cov)
    return m
def stamp(m):return m.header.stamp.sec*NS_PER_S+m.header.stamp.nanosec
def state(n):
    return dict(pose=None if n.last_pose is None else [n.last_pose.position.x,n.last_pose.position.z],time=None if n.last_pose_time is None else n.last_pose_time.nanoseconds,rejects=n._consec_rejects,candidates=len(n._reseed_candidates),published=n.published,output_stamps=[stamp(m) for m in n.vpe_pub.messages])
PAIRS={}
class Tests(unittest.TestCase):
    def test_stale_before_first_accumulation(self):
        a,b=Base(),Fresh()
        for n in (a,b):n.vpe_active=True;n.aruco_map_callback(msg(9.0));n.publish_timer()
        self.assertEqual(len(a.vpe_pub.messages),1);self.assertIsNone(b.last_pose);self.assertEqual(b._consec_rejects,0)
        PAIRS['stale_first']=dict(before=state(a),after=state(b))
    def test_future_zero_malformed_are_rejected(self):
        for change in (lambda m:setattr(m.header,'stamp',Time(nanoseconds=10*NS_PER_S+1).to_msg()),lambda m:setattr(m.header,'stamp',Time().to_msg()),lambda m:setattr(m.header.stamp,'nanosec',NS_PER_S),lambda m:setattr(m.header.stamp,'sec',-1),lambda m:setattr(m.header.stamp,'sec',9.5),lambda m:setattr(m.header.stamp,'sec',True),lambda m:delattr(m.header,'stamp')):
            n=Fresh();m=msg(9.9);change(m);n.aruco_map_callback(m);self.assertIsNone(n.last_pose);self.assertFalse(n._reseed_candidates)
    def test_preserve_stamp_covariance_and_pose(self):
        cov=[float(i)/100 for i in range(36)]
        a,b=Base(),Fresh()
        for n in (a,b):
            n.vpe_active=True;n.aruco_map_callback(msg(9.9,cov=cov));n.clock.set(10.1);n.publish_timer()
        self.assertEqual(stamp(a.vpe_pub.messages[-1]),10_100_000_000)
        self.assertEqual(stamp(b.vpe_pub.messages[-1]),9_900_000_000)
        self.assertEqual(a.vpe_pub.messages[-1].pose.covariance,b.vpe_pub.messages[-1].pose.covariance)
        self.assertEqual(a.vpe_pub.messages[-1].pose.pose.position.__dict__,b.vpe_pub.messages[-1].pose.pose.position.__dict__)
        PAIRS['fresh_stamp']=dict(before=state(a),after=state(b))
    def test_duplicate_and_reorder_do_not_refresh_or_reseed(self):
        a,b=Base(),Fresh()
        for n in (a,b):
            n.vpe_active=True;n.aruco_map_callback(msg(9.9));n.clock.set(10.1);n.aruco_map_callback(msg(9.9,x=1.));n.clock.set(10.2);n.aruco_map_callback(msg(9.8,x=1.));n.clock.set(10.41);n.publish_timer()
        self.assertEqual(b._consec_rejects,0);self.assertFalse(b._reseed_candidates);self.assertEqual(b.last_pose_time.nanoseconds,9_900_000_000);self.assertFalse(b.vpe_pub.messages)
        PAIRS['replayed_reseed_inputs']=dict(before=state(a),after=state(b))
    def test_stale_rejects_cannot_force_reseed(self):
        a,b=Base(),Fresh()
        for n in (a,b):
            n.vpe_active=True;n.aruco_map_callback(msg(9.9))
            for i in range(20):n.clock.set(10.6+i*.1);n.aruco_map_callback(msg(8.+i*.01,x=1.+i*.4))
            n.publish_timer()
        self.assertGreater(a.last_pose.position.x,0.);self.assertEqual(b.last_pose.position.x,0.);self.assertEqual(b._consec_rejects,0);self.assertFalse(b.vpe_pub.messages)
        PAIRS['stale_forced_reseed']=dict(before=state(a),after=state(b))
    def test_medoid_keeps_its_own_source_time(self):
        a,b=Base(),Fresh()
        for n in (a,b):
            n.clock.set(10.);n.vpe_active=True;n.aruco_map_callback(msg(10.))
            for i,x in enumerate((1.,1.01,1.02,1.03,1.04),1):
                n.clock.set(10.+i*.1+.05);n.aruco_map_callback(msg(10.+i*.1,x=x))
            self.assertAlmostEqual(n.last_pose.position.x,1.03)
        self.assertEqual(b.last_pose_time.nanoseconds,10_400_000_000)
        for n in (a,b):n.clock.set(10.91);n.publish_timer()
        self.assertTrue(a.vpe_pub.messages);self.assertFalse(b.vpe_pub.messages)
        PAIRS['medoid_time']=dict(before=state(a),after=state(b))
    def test_forced_reseed_preserves_selected_source(self):
        n=Fresh();n.aruco_map_callback(msg(10.))
        for i in range(1,16):n.clock.set(10.+i*.1+.01);n.aruco_map_callback(msg(10.+i*.1,x=i*.4+1.))
        self.assertAlmostEqual(n.last_pose.position.x,14*.4+1.);self.assertEqual(n.last_pose_time.nanoseconds,11_400_000_000);self.assertEqual(n._consec_rejects,0)
    def test_half_second_boundary_and_original_fallback_covariance(self):
        n=Fresh();n.vpe_active=True;n.aruco_map_callback(msg(9.5));n.publish_timer();self.assertEqual(len(n.vpe_pub.messages),1)
        cov=n.vpe_pub.messages[0].pose.covariance;self.assertEqual(cov[0],.3**2);self.assertEqual(cov[14],.3**2);self.assertEqual(cov[35],.05**2)
        n.clock.ns+=1;n.publish_timer();self.assertEqual(len(n.vpe_pub.messages),1)
    def test_output_repeats_keep_same_stamp(self):
        n=Fresh();n.vpe_active=True;n.aruco_map_callback(msg(9.9))
        for t in (10.,10.1,10.2):n.clock.set(t);n.publish_timer()
        self.assertEqual([stamp(m) for m in n.vpe_pub.messages],[9_900_000_000]*3)
    def test_speed_uses_measurement_intervals(self):
        a,b=Base(),Fresh()
        for n in (a,b):
            n.aruco_map_callback(msg(9.95));n.clock.set(10.2);n.aruco_map_callback(msg(10.,x=.1))
        self.assertAlmostEqual(a.last_pose.position.x,.1);self.assertEqual(b.last_pose.position.x,0.);self.assertEqual(b._consec_rejects,1)
        PAIRS['speed_same_threshold_source_dt']=dict(before=state(a),after=state(b))
    def test_floor_ceiling_jump_and_consistency_thresholds_unchanged(self):
        for z in (-.31,4.01):
            a,b=Base(),Fresh()
            for n in (a,b):n.aruco_map_callback(msg(9.9,z=z))
            self.assertIsNone(a.last_pose);self.assertIsNone(b.last_pose)
        for name in ('_maybe_reseed','_candidates_consistent','_medoid','_evaluate_gate','_single_marker_fresh','_multi_marker_fresh','markers_used_callback','yaw_locked_callback','state_callback'):
            self.assertIs(getattr(Fresh,name),getattr(Base,name))
        self.assertEqual(ENV['_MAX_VISION_SPEED'],1.5)
    def test_yaw_multi_and_first_armed_gate_unchanged(self):
        a,b=Base(),Fresh()
        for n in (a,b):
            n.aruco_map_callback(msg(9.9));n._apply_gate();n.yaw_locked_callback(NS(data=True));n.markers_used_callback(NS(data=0));n.state_callback(NS(armed=True,mode='OFFBOARD'))
        self.assertEqual(a._evaluate_gate(),b._evaluate_gate());self.assertFalse(b.vpe_active)
        for n in (a,b):n.markers_used_callback(NS(data=2));n._apply_gate()
        self.assertEqual(a._evaluate_gate(),b._evaluate_gate());self.assertTrue(b.vpe_active)
    def test_clock_rewind_latches_closed(self):
        n=Fresh();n.vpe_active=True;n.aruco_map_callback(msg(9.9));n.clock.set(9.8);n.publish_timer();n.clock.set(10.1);n.aruco_map_callback(msg(10.));n.publish_timer();self.assertFalse(n.vpe_pub.messages);self.assertTrue(n.freshness_diagnostics()['clock_fault'])
    def test_expiry_during_publication_never_increments_count(self):
        n=Fresh();n.vpe_active=True;n.aruco_map_callback(msg(9.9));n.clock.set(10.39);count=[0]
        def advance():
            count[0]+=1
            # wrapper age check, c33 age, c33 outgoing header, publisher check
            if count[0]>=4:n.clock.set(10.41)
        n.clock.hook=advance;n.publish_timer();self.assertFalse(n.vpe_pub.messages);self.assertEqual(n.published,0)
    def test_snapshot_and_bounded_metadata(self):
        n=Fresh();m=msg(9.9);n.aruco_map_callback(m);m.pose.pose.position.x=99.;m.header.stamp.sec=999;self.assertEqual(n.last_pose.position.x,0.)
        for i in range(100):n.clock.set(10.+i*.01);n.aruco_map_callback(msg(10.+i*.01))
        self.assertLessEqual(n.freshness_diagnostics()['retained_sources'],4);self.assertLessEqual(len(n.freshness_diagnostics()['events']),64)
    def test_clock_context_is_thread_local_and_reset(self):
        n=Fresh();point=Time(nanoseconds=NS_PER_S);token=n._freshness_context.set(point);result=[]
        t=threading.Thread(target=lambda:result.append(n.get_clock().now().nanoseconds));t.start();t.join();self.assertEqual(result,[10*NS_PER_S]);self.assertEqual(n.get_clock().now().nanoseconds,NS_PER_S);n._freshness_context.reset(token);self.assertEqual(n.get_clock().now().nanoseconds,10*NS_PER_S)
    def test_factory_pin_and_opt_in(self):
        with self.assertRaises(ValueError):candidate.make_node_class(Base)
        with self.assertRaises(ValueError):candidate.make_node_class(Fresh,enabled=True)
        with self.assertRaises(ValueError):candidate.make_node_class(Base,enabled=True,source_path=HERE/'candidate/vpe_freshness_optin.py')
        class Altered(Base):
            def _evaluate_gate(self):return True,'altered'
        with self.assertRaises(ValueError):candidate.make_node_class(Altered,enabled=True)
        ENV['_POSE_TIMEOUT']=9.
        try:
            with self.assertRaises(ValueError):candidate.make_node_class(Base,enabled=True)
        finally:ENV['_POSE_TIMEOUT']=.5
    def test_replay_of_physically_rejected_frame_cannot_accumulate(self):
        n=Fresh();n.aruco_map_callback(msg(9.9));n.clock.set(10.2);n.aruco_map_callback(msg(10.,x=1.))
        for i in range(20):n.aruco_map_callback(msg(10.,x=1.))
        self.assertEqual(n._consec_rejects,1);self.assertEqual(len(n._reseed_candidates),1);self.assertEqual(n.last_pose.position.x,0.)
    def test_mutated_loaded_method_is_rejected_even_if_file_pin_matches(self):
        original=Base.publish_timer;Base.publish_timer=lambda self:None
        try:
            with self.assertRaises(ValueError):candidate.make_node_class(Base,enabled=True)
        finally:Base.publish_timer=original
    def test_installer_is_explicit_and_in_memory_only(self):
        mod=NS(VpeFix=Base)
        with self.assertRaises(ValueError):candidate.install(mod)
        self.assertIs(mod.VpeFix,Base);cls=candidate.install(mod,enabled=True);self.assertTrue(issubclass(cls,candidate.FreshnessMixin));self.assertEqual(hashlib.sha256(PIN.read_bytes()).hexdigest(),candidate.PIN_C33)
    def test_composition_with_actual_parameter_factory(self):
        path=ROOT/'parallel_work/20261015/parameters/candidate/vpe_profile_optin.py';tree=ast.parse(path.read_bytes());factory=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='make_node_class')
        class Control:
            def __init__(self,tx,bridge):self.tx=tx;self.calls=[]
            def call(self,name,*args):self.calls.append(name);return {'success':True}
        env=dict(threading=threading,json=json,OptInControl=Control);exec(compile(ast.Module(body=[factory],type_ignores=[]),str(path),'exec'),env)
        modules={name:sys.modules.get(name) for name in ('fresh_param_adapter','profile_transaction')}
        sys.modules['fresh_param_adapter']=NS(FreshParamAdapter=lambda bridge:NS(bridge=bridge));sys.modules['profile_transaction']=NS(ProfileTransaction=lambda adapter,journal:NS(adapter=adapter,journal=journal))
        try:
            classes=[env['make_node_class'](Fresh),candidate.make_node_class(env['make_node_class'](Base),enabled=True)]
            for cls in classes:
                n=cls(lambda node:NS(node=node),'in_memory_journal');n.vpe_active=True;n.aruco_map_callback(msg(9.9));n.publish_timer();self.assertEqual(stamp(n.vpe_pub.messages[0]),9_900_000_000)
                n.state_callback(NS(armed=True,mode='OFFBOARD'));n.state_callback(NS(armed=False,mode='MANUAL'));self.assertTrue(n.profile_restore_pending.is_set());n.profile_pending_tick();self.assertEqual(n.profile_control.calls,['restore'])
                self.assertNotIn('_handle_set_param',Fresh.__dict__);self.assertEqual(n.profile_control.tx.journal,'in_memory_journal')
        finally:
            for name,previous in modules.items():
                if previous is None:del sys.modules[name]
                else:sys.modules[name]=previous

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests);result=unittest.TextTestRunner(verbosity=2).run(suite)
    report=dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),success=result.wasSuccessful(),scope='Exact c33 class/method AST compiled against deterministic in-memory Node/messages; no ROS transport. Parameter factory extracted unchanged, dependencies stubbed only for composition tests.',parameter_factory_sha256=hashlib.sha256((ROOT/'parallel_work/20261015/parameters/candidate/vpe_profile_optin.py').read_bytes()).hexdigest(),test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),pinned_source_sha256=hashlib.sha256(SOURCE).hexdigest(),candidate_sha256=hashlib.sha256((HERE/'candidate/vpe_freshness_optin.py').read_bytes()).hexdigest(),paired_results=PAIRS)
    (HERE/'logs/test_results.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
