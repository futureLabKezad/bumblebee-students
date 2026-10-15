"""Deadline-aware local lock acquisition. Never mutates transaction on timeout."""
from contextlib import contextmanager
import math

class LockDeadline(TimeoutError):
    pass

@contextmanager
def locked(lock, deadline, clock):
    remaining = deadline-clock()
    if not math.isfinite(remaining) or remaining <= 0 or not lock.acquire(timeout=remaining):
        raise LockDeadline('lock_deadline')
    try:
        if clock() >= deadline:
            raise LockDeadline('lock_deadline')
        yield
    finally:
        lock.release()


def transaction_call(method):
    """Compute deadline before queueing; refusal leaves another owner's doc intact."""
    from functools import wraps
    @wraps(method)
    def call(self, *args, timeout=30.0, **kwargs):
        try:
            deadline = self.clock()+min(30.0,self._timeout(timeout))
            with locked(self.lock,deadline,self.clock):
                return method(self,*args,_deadline=deadline,**kwargs)
        except (LockDeadline, ValueError) as error:
            return dict(success=False,status='refused',error=str(error))
    return call
