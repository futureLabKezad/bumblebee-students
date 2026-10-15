"""No ROS, no vehicle: verify the client's cancellation protocol."""
import unittest
import os
import signal
import subprocess
import sys
from types import SimpleNamespace
from test_drone_flight_guards import load_drone,FakeTime,FakeNode,NAVIGATE

class Client:
    srv_name='/navigate'
    def __init__(self):self.sent=0;self.removed=False;self.complete=False
    def wait_for_service(self,timeout_sec=None):return True
    def call_async(self,req):
        self.sent+=1
        return SimpleNamespace(done=lambda:self.complete,result=lambda:SimpleNamespace(success=False,message='cancelled'))
    def remove_pending_request(self,future):self.removed=True

class AutoArmInterrupt(unittest.TestCase):
    def setUp(self):
        self.d=load_drone();self.d.time=FakeTime();self.d._node=FakeNode();self.d.srv=SimpleNamespace(Navigate=NAVIGATE)
        self.c=Client();self.d._navigate_client=self.c;self.calls=[]
    def test_cancel_before_send(self):
        self.d.should_land=True
        self.assertFalse(self.d._call_auto_arm(NAVIGATE.Request()).success)
        self.assertEqual(self.c.sent,0)
    def test_cancel_pending(self):
        def land():
            self.calls.append('land');self.c.complete=True
            return SimpleNamespace(success=True,message='')
        self.d.land=land
        self.d.time.on_advance.append(lambda dt:setattr(self.d,'should_land',True))
        result=self.d._call_auto_arm(NAVIGATE.Request())
        self.assertFalse(result.success);self.assertEqual(self.calls,['land']);self.assertEqual(self.c.sent,1)
    def test_timeout_lands_before_remove(self):
        self.d.land=lambda:self.calls.append('land')
        with self.assertRaisesRegex(Exception,'timed out'):
            self.d._call_auto_arm(NAVIGATE.Request(),timeout=.1)
        self.assertEqual(self.calls,['land']);self.assertTrue(self.c.removed)
    def test_plain_keyboard_interrupt_lands(self):
        self.d.land=lambda:self.calls.append('land')
        def interrupt(dt):raise KeyboardInterrupt()
        self.d.time.on_advance.append(interrupt)
        with self.assertRaises(KeyboardInterrupt):self.d._call_auto_arm(NAVIGATE.Request())
        self.assertEqual(self.calls,['land']);self.assertTrue(self.c.removed)

    def test_actual_sigint_pending_request(self):
        # Real signal delivery in a separate process; there is no ROS or vehicle.
        script = '''
from test_auto_arm_interrupt import Client
from test_drone_flight_guards import load_drone, FakeNode, NAVIGATE
from types import SimpleNamespace
d=load_drone(); d._node=FakeNode(); d.srv=SimpleNamespace(Navigate=NAVIGATE)
c=Client(); d._navigate_client=c
def land():
    print('LAND',flush=True); c.complete=True
    return SimpleNamespace(success=True,message='')
d.land=land
d.enable_safe_interrupt()
print('READY',flush=True)
r=d._call_auto_arm(NAVIGATE.Request(),timeout=10)
assert not r.success and c.sent==1
print('CANCELLED',flush=True)
'''
        proc=subprocess.Popen([sys.executable,'-c',script],cwd=os.path.dirname(__file__),
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(),'READY')
            # Wait until the asynchronous request is pending, then deliver SIGINT.
            import time
            time.sleep(.2)
            os.kill(proc.pid,signal.SIGINT)
            out,err=proc.communicate(timeout=5)
            self.assertEqual(proc.returncode,0,err)
            self.assertEqual(out.splitlines(),['LAND','CANCELLED'])
        finally:
            if proc.poll() is None:
                proc.terminate();proc.communicate(timeout=5)

if __name__=='__main__':unittest.main()
