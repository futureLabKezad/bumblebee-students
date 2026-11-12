"""flight_trial_18 (s7fix-07): the failure cleanup of gate.py and supervisor.py, one tested function.

A direct AUTO.LAND before PX4 detected a takeoff (simple_offboard's ground hold) idles the motors until COM_DISARM_PRFLT (30 s),
so the cleanup calls /land first: it disarms in the hold and switches to AUTO.LAND in flight. A direct AUTO.LAND follows only when
the vehicle is still armed outside AUTO.LAND after /land (refused or failed: pilot mode, simple_offboard missing or stuck). S5
(pilot) keeps the old direct AUTO.LAND: verify_flight.py ends its POSCTL window at that external_mode_sent event, and /land is
refused in POSCTL anyway. The cleanup never turns a failure into a pass: it runs after the failure is recorded."""


def cleanup_land(state, call_land, set_auto_land, wait, event, direct=False, disarm_wait=5.0, final_wait=120.0):
    """Stop the motors after a failed scenario; returns the last state.

    state()          -> (connected, armed, mode), or None when unknown
    call_land()      -> (success, message) of /land; raises when unavailable or timed out
    set_auto_land()  sends AUTO.LAND directly (raises when refused)
    wait(pred, s)    -> pred() became true within s seconds
    event(kind, **)  records what happened
    """
    def disarmed():
        s = state()
        return bool(s and s[0] and not s[1])
    if direct:
        set_auto_land()
    else:
        disarmed_by_land = False
        try:
            success, message = call_land()
            event('cleanup_land_reply', success=bool(success), message=message)
            # simple_offboard confirmed the DISARM itself: no AUTO.LAND even if this state copy lags (1 Hz heartbeat
            # on the sim clock, ~5 s wall at RTF 0.2)
            disarmed_by_land = bool(success) and 'disarmed' in str(message).lower()
        except Exception as error:
            event('cleanup_land_service_failure', message=str(error))
        if not disarmed_by_land and not wait(disarmed, disarm_wait):
            s = state()
            if s and s[0] and s[1] and s[2] != 'AUTO.LAND':
                event('cleanup_direct_auto_land', mode=s[2])
                set_auto_land()
    wait(disarmed, final_wait)
    return state()
