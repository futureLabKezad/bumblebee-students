"""S4 (mavros_restart) oracle: PX4's own failsafe AUTO.LAND, read from the proxy's source-identified HEARTBEAT rows.

Why: MAVROS 2.14 (bp02) builds the State mode text before it learns the autopilot type from the same HEARTBEAT
(src/plugins/sys_status.cpp handle_heartbeat: str_mode_v10() at line 905, update_heartbeat() at line 936), so the
first State of a restarted MAVROS reads 'CMODE(<custom_mode>)'. If PX4 disarms before the second HEARTBEAT reaches
the restarted MAVROS, the decoded text 'AUTO.LAND' never appears (INT_flight_pc_bp02cmd_mavros_restart_06). The
landing is PX4's, so the gate takes AUTO.LAND from PX4 and checks that every MAVROS report agrees with it: at least one
connected armed State before PX4's disarm heartbeat (the restarted MAVROS saw the landing, as the ft19 gate required),
the raw text only on the first connected State of the restarted MAVROS (the only one built before update_heartbeat;
the disconnection States carry mode '' and connected False, sys_status.cpp publish_disconnection), the decoded text on
every later armed State, and after the disarm the exact text MAVROS gives PX4's current custom_mode.

PX4 custom_mode (MAVROS include/mavros/px4_custom_mode.hpp, same layout as PX4 px4_custom_mode.h):
  union { struct { uint16_t reserved; uint8_t main_mode; uint8_t sub_mode; }; uint32_t data; }  (little endian)
  -> main_mode = bits 16..23, sub_mode = bits 24..31; MAIN_MODE_AUTO = 4, SUB_MODE_AUTO_LAND = 6, MAIN_MODE_OFFBOARD = 6.
Same decoding as the pinned legacy verifier (verify_package1b_gates.py freeze_setpoint_window:
(mode >> 16) & 255 == 4 and (mode >> 24) & 255 == 6); like MAVROS str_mode_px4() the reserved bits are ignored.

Limits (the pinned legacy verifier separates these through the ULog, unchanged): AUTO/LAND is also what PX4 reports
for NAVIGATION_STATE_DESCEND, and a LAND commanded through a link the proxy does not see cannot be told apart; the
gate records whether the LAND heartbeat came before the MAVROS respawn and refuses a mode command forwarded by the
proxy between the kill and the LAND.
"""
import math
import time

MAIN_AUTO = 4
SUB_AUTO_LAND = 6
MAIN_OFFBOARD = 6
AUTO_LAND = (SUB_AUTO_LAND << 24) | (MAIN_AUTO << 16)  # 100925440 = 0x06040000
OFFBOARD = MAIN_OFFBOARD << 16  # 393216 = 0x00060000
LAND_TEXT = 'AUTO.LAND'
RAW_LAND_TEXT = 'CMODE(%d)' % AUTO_LAND  # first State of a restarted MAVROS only (see above)
# MAVROS 2.14 uas_stringify.cpp px4_cmode_map (main modes MANUAL=1 ALTCTL POSCTL AUTO ACRO OFFBOARD STABILIZED RATTITUDE;
# AUTO sub modes READY=1 TAKEOFF LOITER MISSION RTL LAND RTGS FOLLOW_TARGET PRECLAND)
_MAIN = {1: 'MANUAL', 5: 'ACRO', 2: 'ALTCTL', 3: 'POSCTL', 6: 'OFFBOARD', 7: 'STABILIZED', 8: 'RATTITUDE'}
_AUTO = {4: 'AUTO.MISSION', 3: 'AUTO.LOITER', 5: 'AUTO.RTL', 6: 'AUTO.LAND', 7: 'AUTO.RTGS', 1: 'AUTO.READY',
         2: 'AUTO.TAKEOFF', 8: 'AUTO.FOLLOW_TARGET', 9: 'AUTO.PRECLAND'}
# COMMAND_LONG / COMMAND_INT that change PX4's mode towards a landing: DO_SET_MODE 176, NAV_RETURN_TO_LAUNCH 20,
# NAV_LAND 21, NAV_LAND_LOCAL 23, NAV_VTOL_LAND 85; SET_MODE is checked by its message type
MODE_COMMANDS = (176, 20, 21, 23, 85)


def main_mode(custom_mode):
    return (custom_mode >> 16) & 255


def sub_mode(custom_mode):
    return (custom_mode >> 24) & 255


def is_auto_land(custom_mode):
    return main_mode(custom_mode) == MAIN_AUTO and sub_mode(custom_mode) == SUB_AUTO_LAND


def mavros_text(custom_mode):
    """The State.mode text MAVROS 2.14 str_mode_px4() gives a PX4 custom_mode once it knows the autopilot is PX4:
    reserved bits cleared, sub_mode cleared for non-AUTO main modes, table lookup, else 'CMODE(<cleared value>)'."""
    main, sub = main_mode(custom_mode), sub_mode(custom_mode)
    if main == MAIN_AUTO:
        text = _AUTO.get(sub)
    else:
        text, sub = (_MAIN.get(main) if main else None), 0
    return text or 'CMODE(%d)' % ((sub << 24) | (main << 16))


def px4_heartbeat(row):
    """A HEARTBEAT the proxy received from PX4 itself (system 1, component 1, MAV_AUTOPILOT_PX4 = 12)."""
    wall = row.get('wall')
    return (row.get('kind') == 'heartbeat' and row.get('is_px4') is True
            and row.get('source_system') == 1 and row.get('source_component') == 1 and row.get('autopilot') == 12
            and type(row.get('armed')) is bool and type(row.get('custom_mode')) is int
            and type(wall) is float and math.isfinite(wall))


def _beats(rows, since_wall):
    return sorted((r for r in rows if px4_heartbeat(r) and r['wall'] > since_wall), key=lambda r: r['wall'])


def first_land(rows, fault_wall):
    """The first armed AUTO.LAND PX4 heartbeat after the fault, or None."""
    return next((r for r in _beats(rows, fault_wall) if r['armed'] and is_auto_land(r['custom_mode'])), None)


def first_disarm(rows, fault_wall):
    """The first disarmed PX4 heartbeat after the first armed AUTO.LAND, or None."""
    land = first_land(rows, fault_wall)
    if land is None:
        return None
    return next((r for r in _beats(rows, land['wall']) if not r['armed']), None)


def left_land(rows, fault_wall):
    """Armed PX4 heartbeats between the first armed AUTO.LAND and the first disarmed one (or the end of the record)
    whose mode is not AUTO.LAND: PX4 left the failsafe landing while armed."""
    land = first_land(rows, fault_wall)
    if land is None:
        return []
    disarm = first_disarm(rows, fault_wall)
    return [r for r in _beats(rows, land['wall']) if (disarm is None or r['wall'] < disarm['wall'])
            and r['armed'] and not is_auto_land(r['custom_mode'])]


def failsafe_land(rows, fault_wall):
    """(first_land, first_disarm, left_land) - kept for callers that want the three at once."""
    return first_land(rows, fault_wall), first_disarm(rows, fault_wall), left_land(rows, fault_wall)


def commanded_modes(rows, since_wall, until_wall):
    """Mode commands the proxy forwarded to PX4 in (since_wall, until_wall]: SET_MODE, or COMMAND_LONG/COMMAND_INT
    MAV_CMD_DO_SET_MODE. Any entry means the LAND may not be PX4's own failsafe."""
    return [r for r in rows if r.get('kind') == 'packet' and r.get('direction') == 'ros_to_px4'
            and since_wall < r.get('wall', -math.inf) <= until_wall
            and (r.get('mavpackettype') == 'SET_MODE'
                 or (r.get('mavpackettype') in ('COMMAND_LONG', 'COMMAND_INT') and r.get('command') in MODE_COMMANDS))]


def armed_reports_before(states, since_wall, until_wall):
    """Connected armed States received after since_wall and before until_wall (the PX4 disarm heartbeat)."""
    return [s for s in states if since_wall < s['wall'] < until_wall and s.get('connected') and s['armed']]


def unexpected_armed_reports(states, since_wall):
    """Armed States received after since_wall whose mode text is not PX4 AUTO.LAND. The raw text is accepted only on
    the first connected State after since_wall (the one MAVROS builds before it knows the autopilot type)."""
    after = [s for s in states if s['wall'] > since_wall]
    first = next((s for s in after if s.get('connected')), None)
    return [s for s in after if s['armed'] and not (s['mode'] == LAND_TEXT or (s is first and s['mode'] == RAW_LAND_TEXT))]


def decoded_after(rows, states, since_wall):
    """The first connected, disarmed State after since_wall whose mode is exactly the MAVROS text of PX4's latest
    heartbeat custom_mode received before that State, or None."""
    beats = _beats(rows, -math.inf)
    for s in states:
        if s['wall'] <= since_wall or not s.get('connected') or s['armed']:
            continue
        last = None
        for r in beats:
            if r['wall'] > s['wall']:
                break
            last = r
        if last is not None and s['mode'] == mavros_text(last['custom_mode']):
            return s
    return None


def judge(rows, states, fault_wall, respawn_wall):
    """The S4 decision on a complete record (gate and tests use the same code): the first failure message, or None.
    rows: mavlink_proxy.jsonl rows; states: MAVROS States {wall, connected, armed, mode} received after respawn_wall."""
    land = first_land(rows, fault_wall)
    if land is None:
        return 'No PX4 failsafe AUTO.LAND heartbeat after the MAVROS kill'
    commanded = commanded_modes(rows, fault_wall, land['wall'])
    if commanded:
        return 'Mode command forwarded to PX4 between the MAVROS kill and AUTO.LAND: %r' % commanded[:3]
    disarm = first_disarm(rows, fault_wall)
    if disarm is None:
        return 'No PX4 disarmed heartbeat after the failsafe AUTO.LAND'
    left = left_land(rows, fault_wall)
    if left:
        return 'PX4 left AUTO.LAND while armed after the MAVROS kill: %r' % left[:3]
    wrong = unexpected_armed_reports(states, respawn_wall)
    if wrong:
        return 'Restarted MAVROS reported an armed mode other than PX4 AUTO.LAND: %r' % wrong[:3]
    if not armed_reports_before(states, respawn_wall, disarm['wall']):
        # as the ft19 gate (a decoded AUTO.LAND State could only come from an armed LAND heartbeat): the restarted MAVROS
        # must have reported PX4's armed landing; connecting only after the disarm is not an S4 run
        return 'Restarted MAVROS reported no armed State before the PX4 disarm (it did not see the failsafe landing)'
    if decoded_after(rows, states, disarm['wall']) is None:
        return 'Restarted MAVROS did not decode the PX4 mode after the disarm'
    return None


def poll(read, pick, timeout, period=.25):
    """pick(read()) until it is not None or timeout wall seconds passed; returns the last pick."""
    end = time.monotonic() + timeout
    while True:
        value = pick(read())
        if value is not None or time.monotonic() >= end:
            return value
        time.sleep(period)
