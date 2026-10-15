#!/usr/bin/env python3
"""Separate opt-in VPE executable. Never substitutes the original launch.
Requires controlled SITL proxy, audited route file and MAVLINK20=1.
"""
import argparse
import hashlib
import json
from pathlib import Path
import threading
from optin_control import OptInControl


def make_node_class(base):
    # Factory also allows verification against a plain Python base without ROS.
    class ProfileVpe(base):
        def __init__(self,bridge_factory,journal):
            self.profile_control=None
            self.profile_restore_pending=threading.Event()
            super().__init__()
            from fresh_param_adapter import FreshParamAdapter
            from profile_transaction import ProfileTransaction
            self.profile_bridge=bridge_factory(self)
            adapter=FreshParamAdapter(self.profile_bridge)
            self.profile_control=OptInControl(ProfileTransaction(adapter,journal),self.profile_bridge)
        def _initial_pull_tick(self):
            # Raw bridge owns parameter traffic in the separate opt-in mode.
            pass
        @staticmethod
        def _result(response,result):
            response.success=result['success']
            response.message=json.dumps(result,sort_keys=True)
            if hasattr(response,'original_value'): response.original_value=float('nan')
            return response
        def _handle_set_param(self,request,response):
            if self.profile_control is None:
                return self._result(response,dict(success=False,status='not_ready'))
            result=self.profile_control.call('apply',request)
            if result['success']:
                response.original_value=self.profile_control.tx.doc['baseline'][request.param_id]
                response.success=True; response.message=json.dumps(result)
                return response
            return self._result(response,result)
        def _handle_revert_all(self,request,response):
            return self._result(response,self.profile_control.call('restore') if self.profile_control
                else dict(success=False,status='not_ready'))
        def _revert_all_non_persistent(self,reason):
            # Parent state_callback retains its original VPE fields and _apply_gate.
            # Schedule IO on handler group; raw callbacks remain able to run.
            self.profile_restore_pending.set()
        def _revert_all(self,reason):
            self.profile_restore_pending.set()
        def _restore_one(self,*args,**kwargs):
            raise RuntimeError('single parameter restore unsupported in opt-in mode')
        def _arm_ttl(self,*args,**kwargs):
            raise RuntimeError('TTL unsupported in opt-in mode')
        def _param_set_once(self,*args,**kwargs):
            return False,'legacy writer disabled in opt-in mode'
        def profile_pending_tick(self):
            if self.profile_restore_pending.is_set() and self.profile_control is not None:
                self.profile_restore_pending.clear()
                result=self.profile_control.call('restore')
                self.get_logger().info('profile restore: '+json.dumps(result))
        def prepare_profile(self,request,response):
            return self._result(response,self.profile_control.call('prepare'))
        def allow_profile_flight(self,request,response):
            return self._result(response,self.profile_control.call('allow_flight'))
    return ProfileVpe


def shutdown_context(context, shutdown):
    """Idempotent cleanup after SIGINT; retain unexpected live-context errors."""
    if not context.ok():
        return False
    try:
        shutdown()
    except RuntimeError:
        # SIGINT may close the context between ok() and shutdown().
        if context.ok():
            raise
    return True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sitl-opt-in',action='store_true',required=True)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--guard-directory',type=Path,required=True)
    parser.add_argument('--journal',type=Path,required=True)
    args,ros_args=parser.parse_known_args()
    audit=json.loads(args.audit.read_text())
    # Explicit supervisor evidence. This does not discover hidden network paths.
    required=['sitl_4030','sim_gz_en_1','all_fcu_paths_guarded','no_hardware',
              'raw_topics_verified','exclusive_profile_writer']
    if not all(audit.get(n) is True for n in required):
        raise RuntimeError('SITL route audit incomplete')
    if any(Path(p).exists() for p in ('/etc/bumblebee','/etc/bumblebee_version')):
        raise RuntimeError('hardware marker')
    original=Path(__file__).with_name('vpe_fix.py')
    if hashlib.sha256(original.read_bytes()).hexdigest()!='c33a52bf1b10bc064ca102bdc720ed03afaa08c691d9c5c34b1d7fadf859b8b9':
        raise RuntimeError('pinned VPE changed')
    cfg=Path(audit['mavros_config']).read_text()
    if ('fcu_url: udp://127.0.0.1:14640@127.0.0.1:14680' not in cfg or
            "gcs_url: ''" not in cfg or '/dev/' in cfg):
        raise RuntimeError('MAVROS must use the existing guarded proxy route')
    if not audit.get('source_sha256'):
        raise RuntimeError('source manifest required')
    for name,sha in audit['source_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha:
            raise RuntimeError('audited source changed: '+name)
    import rclpy
    from rclpy.executors import MultiThreadedExecutor, ExternalShutdownException
    from std_srvs.srv import Trigger
    from ros_raw_bridge import RosRawBridge
    from vpe_fix import VpeFix
    rclpy.init(args=ros_args)
    NodeClass=make_node_class(VpeFix)
    node=NodeClass(lambda n:RosRawBridge(n,args.guard_directory,audit['fcu_endpoint'],
        callback_group=n._cb_grp_clients),args.journal)
    node.create_service(Trigger,'/vpe_fix/prepare_profile',node.prepare_profile,
        callback_group=node._cb_grp_handlers)
    node.create_service(Trigger,'/vpe_fix/allow_profile_flight',node.allow_profile_flight,
        callback_group=node._cb_grp_handlers)
    node.create_timer(.05,node.profile_pending_tick,callback_group=node._cb_grp_handlers)
    executor=MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # After executor stop fresh readback is unavailable: retain journal.
        context=node.context
        try:
            node.destroy_node()
        finally:
            shutdown_context(context,lambda:rclpy.shutdown(context=context))

if __name__=='__main__': main()
