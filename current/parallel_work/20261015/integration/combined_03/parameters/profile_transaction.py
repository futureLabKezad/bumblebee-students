"""Bounded, transport-injected INDOOR_ARUCO transaction. No network or ROS.
Transport methods must obey the absolute monotonic deadline; see INTERFACE.md.
"""
import json
import math
import os
from pathlib import Path
import threading
import time
from deadline_lock import transaction_call
from sitl_profile_closure_candidate import (profile_values, closure_names,
    restore_order, validate_baseline, validate_samples, validate_constraints, Sample, KnownCapsModel)


class Refused(RuntimeError):
    pass


class ProfileTransaction:
    def __init__(self, transport, journal, clock=time.monotonic):
        self.io, self.path, self.clock = transport, Path(journal), clock
        self.lock = threading.RLock()
        self.profile = profile_values()
        self.names = closure_names(self.profile)
        self.generation = 0
        self.doc = None
        if self.path.exists():
            self.doc = json.loads(self.path.read_text())
            self.generation = self.doc['generation']
            # No blind resume after process death or an ambiguous write.
            if self.doc['status'] != 'restored':
                self.doc['status'] = 'recovery_required'
                self._save()

    def _save(self):
        # Same-directory atomic replacement plus durable file and directory.
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('w') as f:
            json.dump(self.doc, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _guard(self, deadline, generation):
        if self.clock() >= deadline:
            raise Refused('deadline')
        if generation != self.generation:
            raise Refused('generation_changed')
        state = self.io.state(deadline)
        if (state.armed is not False or state.connected is not True or
                state.sysid != 1 or state.compid != 1 or
                not math.isfinite(state.received) or
                not 0 <= self.clock()-state.received <= 1.0):
            raise Refused('armed_or_unknown_state')
        if self.clock() >= deadline:
            raise Refused('deadline')

    def _readiness(self, deadline):
        # A precondition check: no snapshot, generation or journal mutation.
        if self.clock()>=deadline:
            return dict(success=False,status='not_ready',error='deadline',transaction_started=False)
        try:
            state=self.io.state(deadline)
            if self.clock()>=deadline:
                reason='deadline'
            elif getattr(state,'armed',None) is None:
                reason='awaiting_first_heartbeat' if getattr(state,'reason',None)=='awaiting_first_heartbeat' else 'state_unknown'
            elif state.armed is True:
                reason='state_armed'
            elif state.armed is not False or getattr(state,'connected',None) is not True:
                reason='state_disconnected_or_unknown'
            elif getattr(state,'sysid',None)!=1 or getattr(state,'compid',None)!=1:
                reason='state_source_invalid'
            elif (type(getattr(state,'received',None)) not in (int,float) or
                    not math.isfinite(state.received) or not 0<=self.clock()-state.received<=1.):
                reason='state_stale_or_invalid_time'
            else:
                return dict(success=True,status='ready_for_prepare',transaction_started=False)
            return dict(success=False,status='not_ready',error=reason,transaction_started=False)
        except Exception as error:
            return dict(success=False,status='not_ready',error='state_unavailable',
                detail=str(error),exception_type=type(error).__name__,transaction_started=False)

    @transaction_call
    def readiness(self, _deadline=None):
        if self.doc and self.doc['status']!='restored':
            return dict(success=False,status=self.doc['status'],error='existing journal requires review',
                transaction_started=True,generation=self.generation)
        return self._readiness(_deadline)

    @staticmethod
    def _raw_scalar(value):
        if type(value) in (str,int,bool) or value is None:
            return value
        if type(value) is float and math.isfinite(value):
            return value
        return dict(python_type=type(value).__name__,representation=repr(value))

    def _scan(self, deadline, generation, permit_transient_caps=False, phase='stable'):
        result={}; wire={}
        entry=dict(phase=phase,generation=generation,started=self.clock(),
            deadline=deadline,complete=False,samples={})
        if self.doc and self.doc.get('pending'):
            entry['pending_write']={k:self.doc['pending'][k] for k in ('name','value')}
        try:
            for name in self.names:
                self._guard(deadline,generation)
                entered=self.clock()
                sample=self.io.read_fresh(name,deadline)
                now=self.clock()
                raw={field:self._raw_scalar(getattr(sample,field,None)) for field in
                     ('name','value','mav_param_type','sysid','compid','received')}
                raw['request_entered']=entered
                entry['samples'][name]=raw
                wire[name]=(sample,entered,now)
                result[name]=Sample(getattr(sample,'value',None),getattr(sample,'mav_param_type',None))
            entry['complete']=set(result)==set(self.names)
            self._guard(deadline,generation)
            # Type/completeness and wire provenance are separate from stable caps.
            values=validate_samples(result,self.names)
            for name,(sample,entered,now) in wire.items():
                if (sample.name!=name or sample.sysid!=1 or sample.compid!=1 or
                        type(sample.received) not in (float,int) or not math.isfinite(sample.received) or
                        not entered<=sample.received<=now or now>=deadline or sample.mav_param_type!=9):
                    raise Refused('invalid_wire_sample:'+name)
            return values if permit_transient_caps else validate_constraints(values)
        except BaseException as error:
            entry['error']=str(error)
            raise
        finally:
            entry['finished']=self.clock()
            self._last_scan=entry
            # Post-write journal always exists; retain even invalid/partial reads.
            if self.doc is not None and self.doc['status'] in ('prepared','active','unknown'):
                self.doc.setdefault('observations',[]).append(entry)
                self._save()

    def _settle(self, name, value, before, predicted, deadline, generation):
        changed={n for n in self.names if not self._same({n:before[n]},{n:predicted[n]})}
        descendants=set(closure_names([name]))-{name}
        if changed-{name}-descendants:
            raise Refused('predicted_changes_outside_known_dependencies')
        pending=self.doc['pending']
        pending.update(before=before.copy(),predicted=predicted.copy(),
            changed_names=sorted(changed),phase='awaiting_readback',stable_scans=0)
        self._save()
        final_seen=set(); stable=0; attempt=0
        while self.clock()<deadline:
            attempt+=1
            self._guard(deadline,generation)
            observed=self._scan(deadline,generation,permit_transient_caps=True,phase='post_write')
            self._guard(deadline,generation)
            log=self.doc['observations'][-1]
            log['classification']='rejected'
            # Only endpoints of our single known clamp operation are admissible.
            for n in self.names:
                at_target=self._same({n:observed[n]},{n:predicted[n]})
                if n==name or n not in changed:
                    if not at_target: raise Refused('external_or_unexpected_change:'+n)
                elif n not in descendants:
                    raise Refused('unmanaged_transition:'+n)
                elif not at_target:
                    if n in final_seen or not self._same({n:observed[n]},{n:before[n]}):
                        raise Refused('external_or_nonmonotonic_change:'+n)
                if at_target and n in changed: final_seen.add(n)
            cap_error=None
            try:
                validate_constraints(observed)
            except ValueError as error:
                cap_error=str(error)
            at_final=self._same(observed,predicted) and cap_error is None
            log['classification']='predicted' if at_final else 'permitted_transient'
            log['transient_cap_error']=cap_error
            stable=stable+1 if at_final else 0
            pending.update(attempts=attempt,stable_scans=stable,last_values=observed,
                transient_cap_error=cap_error,final_seen=sorted(final_seen))
            self._save()
            self._guard(deadline,generation)
            if stable>=2:
                return observed
            if self.clock()>=deadline: raise Refused('deadline')
            if not at_final:
                threading.Event().wait(min(.02,max(0.,deadline-self.clock())))
        raise Refused('deadline_without_stable_predicted_state')

    @staticmethod
    def _same(a, b):
        return set(a) == set(b) and all(math.isclose(a[n], b[n], rel_tol=1e-6,
            abs_tol=1e-6) for n in a)

    def _failure(self, error):
        if self.doc is not None and self.doc['status'] != 'restored':
            self.doc['status'] = 'unknown'
            self.doc['error'] = str(error)
            self._save()
        return {'success': False, 'status': 'unknown', 'error': str(error),
                'generation': self.generation, 'transaction_started': True}

    @transaction_call
    def prepare(self, _deadline=None):
        if self.doc and self.doc['status'] != 'restored':
            return {'success': False, 'status': self.doc['status'],
                    'error': 'existing journal requires review',
                    'transaction_started': True, 'generation': self.generation}
        deadline = _deadline
        ready=self._readiness(deadline)
        if not ready['success']:
            return ready
        self.generation += 1
        g = self.generation
        try:
            a = self._scan(deadline,g,phase='baseline_first')
            first_scan=self._last_scan
            b = self._scan(deadline,g,phase='baseline_second')
            second_scan=self._last_scan
            if not self._same(a, b):
                raise Refused('unstable_baseline')
            self.doc = dict(version=1, generation=g, status='prepared',
                baseline=b, expected=b.copy(), pending=None, history=[],
                observations=[first_scan,second_scan])
            self._save()  # durable full 19 before the first write
            self._guard(deadline,g)
            return dict(success=True, status='prepared', generation=g)
        except Exception as e:
            return self._failure(e)

    @staticmethod
    def _timeout(value):
        if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
            raise ValueError('invalid_timeout')
        return value

    @transaction_call
    def apply(self, name, value, generation, ttl_sec=0.0, persistent=False,
              _deadline=None):
        # Reject unsupported requests without poisoning an active journal.
        if (name not in self.profile or type(value) is not float or
                value != self.profile[name] or type(ttl_sec) not in (float,int) or
                ttl_sec != 0 or persistent is not False):
            return dict(success=False, status='refused', error='unsupported_request')
        return self._operate([(name, value)], generation, _deadline, False)

    @transaction_call
    def restore(self, generation, _deadline=None):
        if self.doc and self.doc['status'] == 'restored' and generation == self.generation:
            return dict(success=True, status='restored', generation=generation)
        pairs = [] if not self.doc else [(n, self.doc['baseline'][n])
            for n in restore_order(self.names)]
        return self._operate(pairs, generation, _deadline, True)

    def _operate(self, pairs, generation, deadline, restoring):
        if generation != self.generation:
            return dict(success=False, status='refused', error='generation_changed')
        if not self.doc or self.doc['status'] not in ('prepared','active'):
            return dict(success=False, status='refused', error='not_ready')
        try:
            actual = self._scan(deadline, generation)
            if not self._same(actual, self.doc['expected']):
                raise Refused('external_change')
            for name, value in pairs:
                self._guard(deadline, generation)
                predicted = KnownCapsModel(actual)
                predicted.write(name, value)
                self.doc['pending'] = dict(name=name,value=value,before=actual.copy(),
                    predicted=predicted.values.copy(),phase='before_write')
                self._save()  # intent survives interruption before or during write
                self._guard(deadline, generation)
                if self.io.write(name, value, deadline) is not True:
                    raise Refused('write_failed:'+name)
                observed = self._settle(name,value,actual,predicted.values,deadline,generation)
                actual = observed
                self.doc['expected'] = observed
                self.doc['history'].append(dict(name=name, value=value,
                    readback_scans=self.doc['pending']['attempts'],
                    stable_scans=self.doc['pending']['stable_scans']))
                self.doc['pending'] = None
                self.doc['status'] = 'active'
                self._save()
            # Last post-write scan plus a second final scan for restore.
            a = actual
            b = self._scan(deadline, generation) if restoring else actual
            target = self.doc['baseline'] if restoring else self.doc['expected']
            if not self._same(a, target) or not self._same(b, target):
                raise Refused('unstable_final_readback')
            self.doc['status'] = 'restored' if restoring else 'active'
            self.doc['final_readback'] = b
            self._save()  # retained even on success for independent review
            if self.clock()>=deadline:
                self.doc['status']='unknown'
                raise Refused('deadline_after_journal_sync')
            return dict(success=True, status=self.doc['status'], generation=generation)
        except BaseException as e:
            result = self._failure(e)
            if not isinstance(e, Exception):
                raise
            return result
