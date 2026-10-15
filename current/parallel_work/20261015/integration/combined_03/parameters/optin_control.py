"""ROS-independent orchestration used by the opt-in VPE subclass."""
import time
from deadline_lock import locked, LockDeadline

class OptInControl:
    def __init__(self,transaction,bridge,clock=time.monotonic):
        self.tx,self.bridge,self.clock=transaction,bridge,clock
        self.generation=None
    def call(self,action,request=None,timeout=30.):
        try:
            deadline=self.clock()+min(30.,self.tx._timeout(timeout))
            with locked(self.tx.lock,deadline,self.clock):
                if action=='apply':
                    r=request
                    if (r is None or type(r.ptype) is not int or r.ptype!=1 or
                        type(r.value) is not float or r.param_id not in self.tx.profile or
                        r.value!=self.tx.profile[r.param_id] or r.ttl_sec!=0 or
                        type(r.ttl_sec) not in (int,float) or r.persistent is not False):
                        return dict(success=False,status='refused',error='unsupported_request')
                if action not in ('prepare','apply','restore','allow_flight'):
                    return dict(success=False,status='refused',error='unsupported_action')
                if action!='prepare' and self.generation is None:
                    return dict(success=False,status='refused',error='not_prepared')
                if action=='prepare' and self.tx.doc and self.tx.doc['status']!='restored':
                    return dict(success=False,status=self.tx.doc['status'],error='existing_transaction',
                        transaction_started=True,generation=self.tx.generation)
                if action=='restore' and self.tx.doc['status']=='restored':
                    return self.tx.restore(self.generation,timeout=deadline-self.clock())
                if action=='allow_flight':
                    doc=self.tx.doc
                    applied={h['name'] for h in doc['history']}
                    if (doc['status']!='active' or not set(self.tx.profile)<=applied or
                            doc['pending'] is not None):
                        return dict(success=False,status='refused',error='incomplete_profile')
                    self.tx._guard(deadline,self.generation)
                    actual=self.tx._scan(deadline,self.generation)
                    if not self.tx._same(actual,doc['expected']):
                        return self.tx._failure('external_change_before_flight')
                    self.bridge.set_mode('flight',deadline)
                    return dict(success=True,status='flight_permitted',generation=self.generation)
                if action=='prepare':
                    ready=self.tx.readiness(timeout=deadline-self.clock())
                    if not ready['success']: return ready
                self.bridge.set_mode('inhibit',deadline)
                # This acknowledgment is required before prepare or any write.
                if action=='prepare':
                    result=self.tx.prepare(timeout=deadline-self.clock())
                    if result['success']: self.generation=result['generation']
                    return result
                if action=='restore':
                    return self.tx.restore(self.generation,timeout=deadline-self.clock())
                return self.tx.apply(request.param_id,request.value,self.generation,
                    ttl_sec=request.ttl_sec,persistent=request.persistent,
                    timeout=deadline-self.clock())
        except LockDeadline as e:
            return dict(success=False,status='refused',error=str(e),transaction_started=False)
        except Exception as e:
            # A prepare precondition/handshake refusal is not an unknown write.
            if action=='prepare':
                return dict(success=False,status='not_ready',error='prepare_precondition_unavailable',
                    detail=str(e),exception_type=type(e).__name__,transaction_started=False)
            # A queue timeout must never change another caller's journal.
            return dict(success=False,status='refused',error=str(e))
