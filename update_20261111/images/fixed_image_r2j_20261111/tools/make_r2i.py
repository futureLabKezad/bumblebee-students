#!/usr/bin/env python3
"""make_r2i.py - task T46 of chat 1 (11.11.2026): image r2i = the final r2h (/work/fixed_image_r2h_20261110, SHA256SUMS
890c698e; not edited) + three changes decided by the owner on 11.11:
  1. vpe_fix.py (owner: «Зрение при посадке»): the gate also publishes in AUTO.LAND, on the same vision condition as in
     OFFBOARD (B1/B2 of r2h unchanged); any AUTO.LAND (the script's own /land, a PX4 failsafe land). Other armed modes
     (STABILIZED, ALTCTL, POSCTL, other AUTO) stay silent. Pins round 4 (tests_r4) against a byte copy of r2h's vpe_fix.
  2. simple_offboard.cpp (owner: «+ S9»): the state watchdog measures the FCU link silence with state_link.h
     fcuLinkSilentNs() -- from when the link really went silent, as far as the 30 Hz local_position stream shows --
     instead of "now - last State" (State comes once per 1 Hz HEARTBEAT: a 3.5 s gap that swallowed 4 HEARTBEATs read
     5.0 s and stopped the flight, C8 A10 heartbeat_13). Threshold state_watchdog_timeout 4.5 s unchanged.
     The realtime launch test test_06 of test_simple_offboard_px4model_launch.py: its long gap (5.0 s from right after a
     HEARTBEAT = 4 HEARTBEATs lost) is what the Gazebo S9 short gap also produces (4 lost), so the two contracts could not
     both hold; its long gap becomes 6.0 s (5 lost, as the Gazebo S9 long gap) and the stop bound 5.45-5.8 s.
  3. examples/flight/flight_marker.py: takeoff height 0.7 -> 0.9 (owner: «поднимаем flight_marker.py - 0,9 м»: dist_bottom
     passes 1 m and PX4 learns the hover thrust, T41). flight.py stays 0.8.
  4. camera_fix.py stays the a45a264 file 4a15d699; its manifest row loses PENDING (owner: the new camera is measured on
     the Pi later), so C1 closes.
drone.py: r2h's bytes (wifi-manager, notify-manager and led-default take it from src).
EDITS below is the single table of changes; test/test_r2i_changes.py applies it backwards and must get r2h's bytes.
Usage: python3 -I make_r2i.py   (refuses to overwrite; then colcon, tools/test_all_r2i.sh, tools/finish_r2i.sh)
"""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORK = Path('/work')
R2H = WORK / 'fixed_image_r2h_20261110'
DST = WORK / 'fixed_image_r2i_20261111'
HERE = Path(__file__).resolve().parent
R2H_SUMS = '890c698efdb7317a82e4454cbefe46e0834196506972f1a60296e336c184bc7f'
R2H_VPE = '66d806baf5ef6884bdc7e1636289e90dd55964f8f69ed0ffa13be2e23f5e6958'
R2H_DRONE = 'fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c'
CAMERA_FIX = '4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310'
S = 'src/bumblebee/'
VPE = S + 'src/python/vpe_fix.py'
SO = S + 'src/cpp/simple_offboard.cpp'
H2 = S + 'test/vpe_fix_h2_r2/'

EDITS = [
    # 1. vpe_fix: vision in AUTO.LAND
    (VPE, "    - ARMED + OFFBOARD + (multi_marker_fresh OR single_marker_fresh).\n\n"
          "  Publish = False when:\n"
          "    - FCU state unknown, whatever the last known armed/mode.\n"
          "    - ARMED in non-OFFBOARD mode.\n"
          "    - ARMED + OFFBOARD + vision bad. Baro is secondary altitude source.\n",
          "    - ARMED + OFFBOARD + (multi_marker_fresh OR single_marker_fresh).\n"
          "    - ARMED + AUTO.LAND + the same vision condition (r2i, owner 11.11: vision while landing).\n\n"
          "  Publish = False when:\n"
          "    - FCU state unknown, whatever the last known armed/mode.\n"
          "    - ARMED in any other mode (pilot: STABILIZED, ALTCTL, POSCTL, ...; other AUTO modes).\n"
          "    - ARMED + OFFBOARD/AUTO.LAND + vision bad. Baro is secondary altitude source.\n",
     'module docstring: the gate'),
    (VPE, "        self.in_offboard = False\n        # FCU-state knowledge",
          "        self.in_offboard = False\n"
          "        # r2i (T46): the last reported mode was AUTO.LAND (vision publishes there too, owner 11.11)\n"
          "        self.in_auto_land = False\n        # FCU-state knowledge",
     '__init__: in_auto_land'),
    (VPE, "        if not self.in_offboard:\n"
          "            return False, 'armed in manual (no publish)'\n"
          "        if self._multi_marker_fresh() or self._single_marker_fresh():\n"
          "            self._last_vision_ok_time = self.get_clock().now()\n"
          "            return True, 'OFFBOARD + vision_ok'\n"
          "        if self._last_vision_ok_time is not None:\n"
          "            age = (self.get_clock().now() - self._last_vision_ok_time).nanoseconds / 1e9\n"
          "            if age < _GATE_HYSTERESIS:\n"
          "                return True, 'OFFBOARD + recent vision ok (coasting %.1fs)' % age\n"
          "        return False, 'OFFBOARD + vision_bad (publish suspended)'\n",
          "        if not (self.in_offboard or self.in_auto_land):\n"
          "            return False, 'armed in manual (no publish)'\n"
          "        # r2i (T46, owner 11.11 «Зрение при посадке»): AUTO.LAND -- the script's own /land or a PX4 failsafe\n"
          "        # land -- publishes on the same vision condition as OFFBOARD; every other armed mode stays silent.\n"
          "        mode = 'OFFBOARD' if self.in_offboard else 'AUTO.LAND'\n"
          "        if self._multi_marker_fresh() or self._single_marker_fresh():\n"
          "            self._last_vision_ok_time = self.get_clock().now()\n"
          "            return True, '%s + vision_ok' % mode\n"
          "        if self._last_vision_ok_time is not None:\n"
          "            age = (self.get_clock().now() - self._last_vision_ok_time).nanoseconds / 1e9\n"
          "            if age < _GATE_HYSTERESIS:\n"
          "                return True, '%s + recent vision ok (coasting %.1fs)' % (mode, age)\n"
          "        return False, '%s + vision_bad (publish suspended)' % mode\n",
     '_evaluate_gate: OFFBOARD or AUTO.LAND'),
    (VPE, "        was_offboard = self.in_offboard\n",
          "        was_offboard = self.in_offboard\n        was_auto_land = self.in_auto_land\n",
     'state_callback: previous AUTO.LAND'),
    (VPE, "        self.in_offboard = (msg.mode == 'OFFBOARD')\n",
          "        self.in_offboard = (msg.mode == 'OFFBOARD')\n        self.in_auto_land = (msg.mode == 'AUTO.LAND')\n",
     'state_callback: record AUTO.LAND'),
    (VPE, "        if (self.armed != was_armed or self.in_offboard != was_offboard\n                or not was_fresh):\n",
          "        if (self.armed != was_armed or self.in_offboard != was_offboard\n"
          "                or self.in_auto_land != was_auto_land or not was_fresh):\n",
     'state_callback: a change of AUTO.LAND re-evaluates the gate at once'),
    # 2. simple_offboard: link silence
    (SO, '#include "script_lease.h"\n', '#include "script_lease.h"\n#include "state_link.h"   // r2i (T46, S9)\n', 'include'),
    (SO, '        state_watchdog_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("state_watchdog_timeout", 4.5));\n',
         '        state_watchdog_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("state_watchdog_timeout", 4.5));\n'
         '        // r2i (T46, S9): the FCU HEARTBEAT period, by which the next State is due (state_link.h)\n'
         '        state_heartbeat_period_ = rclcpp::Duration::from_seconds(declare_parameter("state_heartbeat_period", 1.0));\n',
     'parameter state_heartbeat_period 1.0 s'),
    (SO, '    rclcpp::Duration state_watchdog_timeout_{0, 0};\n',
         '    rclcpp::Duration state_watchdog_timeout_{0, 0};\n    rclcpp::Duration state_heartbeat_period_{0, 0};\n', 'member'),
    (SO, '    int64_t state_rx_ns_ = 0;\n',
         '    int64_t state_rx_ns_ = 0;\n'
         '    // r2i (T46, S9): monotonicNs() of the last /mavros/local_position/pose (~30 Hz), mutex_ only: when the FCU\n'
         '    // link went silent, to the resolution of this stream (state_link.h)\n'
         '    int64_t pose_rx_ns_ = 0;\n', 'member pose_rx_ns_'),
    (SO, '            std::lock_guard<std::mutex> lock(mutex_);\n            local_position_ = pose;\n',
         '            std::lock_guard<std::mutex> lock(mutex_);\n            local_position_ = pose;\n'
         '            pose_rx_ns_ = monotonicNs();   // r2i (T46, S9)\n', 'handleLocalPosition: receipt time'),
    (SO, '        // passes the stream on.\n        int64_t silent_ns = monotonicNs() - state_rx_ns_;\n',
         '        // passes the stream on.\n'
         '        // r2i (T46, S9): State comes once per HEARTBEAT, so "now - last State" overstated a loss by up to one\n'
         '        // period (a 3.5 s HEARTBEAT gap that swallowed 4 heartbeats read 5.0 s and stopped the flight, C8 A10\n'
         '        // heartbeat_13). fcuLinkSilentNs() counts from when the link really went silent, as far as the\n'
         '        // local_position stream shows; the threshold stays state_watchdog_timeout (4.5 s). See state_link.h.\n'
         '        int64_t silent_ns = fcuLinkSilentNs(monotonicNs(), state_rx_ns_, pose_rx_ns_,\n'
         '                                            state_heartbeat_period_.nanoseconds());\n',
     'watchdog: fcuLinkSilentNs'),
    # 2b. the realtime S9 launch test: long gap 5.0 -> 6.0 s (see the module docstring)
    (S + 'test/test_simple_offboard_px4model_launch.py',
     "        configured at its production default 4.5 s, PX4 model stream loss at\n"
     "        1 s. Independent observer receipt times have a 50 ms DDS tolerance.\n",
     "        configured at its production default 4.5 s, PX4 model stream loss at\n"
     "        1 s. Independent observer receipt times have a 50 ms DDS tolerance.\n"
     "        r2i (T46): the watchdog counts a HEARTBEAT-only loss from when the next\n"
     "        HEARTBEAT was due (state_link.h). A 5.0 s gap from right after a\n"
     "        HEARTBEAT loses 4 of them, as the Gazebo S9 short gap can (C8 A10\n"
     "        heartbeat_13), so the long gap is 6.0 s (5 lost, as the Gazebo S9 long\n"
     "        gap) and the stop comes 5.5 s after the last HEARTBEAT.\n", 'test_06 docstring'),
    (S + 'test/test_simple_offboard_px4model_launch.py', "                   5.2, 'real C++ heartbeat watchdog stop')\n",
     "                   6.2, 'real C++ heartbeat watchdog stop')\n", 'test_06 wait'),
    (S + 'test/test_simple_offboard_px4model_launch.py',
     "        self.assertGreaterEqual(stopped - long_hb, 4.45)\n        self.assertLess(stopped - long_hb, 4.8)\n"
     "        self.wait_to(long_hb + 5.)\n",
     "        self.assertGreaterEqual(stopped - long_hb, 5.45)\n        self.assertLess(stopped - long_hb, 5.8)\n"
     "        self.wait_to(long_hb + 6.)\n", 'test_06 stop bound and gap length'),
    (S + 'test/test_simple_offboard_px4model_launch.py',
     "        self.assertGreaterEqual(long_restored - long_hb, 5.)\n        self.assertLess(long_restored - long_hb, 5.15)\n",
     "        self.assertGreaterEqual(long_restored - long_hb, 6.)\n        self.assertLess(long_restored - long_hb, 6.15)\n",
     'test_06 restore bound'),
    (S + 'test/test_simple_offboard_px4model_launch.py',
     "        self.assertLessEqual(stopped_sp[-1][0] - long_hb, 4.65)\n",
     "        self.assertLessEqual(stopped_sp[-1][0] - long_hb, 5.65)\n", 'test_06 last setpoint bound'),
    # 3. flight_marker: takeoff 0.9 m
    (S + 'examples/flight/flight_marker.py', "    drone.takeoff(height=0.7, speed=0.4)\n",
     "    drone.takeoff(height=0.9, speed=0.4)\n", 'takeoff 0.7 -> 0.9 m (owner 11.11)'),
    # pins: round 3 on the r2h copy, round 4 on r2i
    (S + 'CMakeLists.txt',
     "  ament_add_pytest_test(test_vpe_fix_pins_r3 test/vpe_fix_h2_r2/tests_r3/test_pins_r3.py TIMEOUT 60\n"
     "    ENV PIN_TARGET=${_VPE} PIN_R2G=${_H2R2}/ref/vpe_fix_r2g_3b8a93d4.py PIN_HARNESS=${_H2R2}/tests_existing/harness)\n",
     "  # r2i (T46): round 3 pins the r2h copy (ref/vpe_fix_r2h_66d806ba.py) against the r2g copy; round 4 pins\n"
     "  # src/python/vpe_fix.py (r2i: vision in AUTO.LAND) against the r2h copy.\n"
     "  ament_add_pytest_test(test_vpe_fix_pins_r3 test/vpe_fix_h2_r2/tests_r3/test_pins_r3.py TIMEOUT 60\n"
     "    ENV PIN_TARGET=${_H2R2}/ref/vpe_fix_r2h_66d806ba.py PIN_R2G=${_H2R2}/ref/vpe_fix_r2g_3b8a93d4.py\n"
     "        PIN_HARNESS=${_H2R2}/tests_existing/harness)\n"
     "  ament_add_pytest_test(test_vpe_fix_pins_r4 test/vpe_fix_h2_r2/tests_r4/test_pins_r4.py TIMEOUT 60\n"
     "    ENV PIN_TARGET=${_VPE} PIN_R2H=${_H2R2}/ref/vpe_fix_r2h_66d806ba.py PIN_HARNESS=${_H2R2}/tests_existing/harness)\n",
     'pins r3 -> r2h copy, r4 -> r2i'),
    (H2 + 'README.md', "Since r2h, CMake runs `test_pins_r2.py` on that r2g copy (the chain c33 -> P1 -> H2 -> r2g), not on `src/python/vpe_fix.py` |\n",
     "Since r2h, CMake runs `test_pins_r2.py` on that r2g copy (the chain c33 -> P1 -> H2 -> r2g), not on `src/python/vpe_fix.py` |\n"
     "| `tests_r4/test_pins_r4.py` (5) | r2i (T46, 11.11.2026): code pins round 4 -- `src/python/vpe_fix.py` against r2h's vpe_fix (`ref/vpe_fix_r2h_66d806ba.py`, byte copy): only `__init__`, `_evaluate_gate`, `state_callback` and three docstring lines differ (vision in AUTO.LAND), their content pinned. Since r2i, CMake runs `test_pins_r3.py` on that r2h copy |\n",
     'README: round 4 row'),
    # 4. camera_fix row: PENDING removed, the row says what src holds
    ('image_manifest_r2.tsv',
     "\tdabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83\tcamera_fullrow_01\tchanged (PENDING: Pi load check at the "
     "bench; owner decides 11.11 morning. r2h src keeps the a45a264 file 4a15d699 as r2g, the one Gazebo checks)\n",
     "\t%s\ta45a264\tsame (r2i: camera_fullrow_01 dabd5076 not taken; owner 11.11 «надо чтобы pi тянул причем с его остальной "
     "нагрузкой»: the new camera is measured on the Pi later)\n" % CAMERA_FIX, 'camera_fix row: same, no PENDING'),
]
NEW_FILES = {S + 'src/cpp/state_link.h': 'state_link.h',
             H2 + 'tests_r4/test_pins_r4.py': 'test_pins_r4.py',
             'test/test_state_link.cpp': 'test_state_link.cpp',
             'test/test_r2i_vpe.py': 'test_r2i_vpe.py',
             'test/test_r2i_changes.py': 'test_r2i_changes.py'}
R2H_ONLY_TESTS = ['test/test_r2h_final.py', 'test/test_pins_r2h.py']   # about r2h itself: moved to test/r2h_only/


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if sha(R2H / 'SHA256SUMS') != R2H_SUMS:
        sys.exit('STOP: r2h is not the accepted one')
    for f in ('SHA256SUMS', 'MANIFEST_SHA256.txt'):
        subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=R2H, check=True)
    if sha(R2H / VPE) != R2H_VPE or sha(R2H / S / 'examples/drone.py') != R2H_DRONE or sha(R2H / S / 'src/python/camera_fix.py') != CAMERA_FIX:
        sys.exit('STOP: r2h files')
    for rel, old, new, why in EDITS:
        t = (R2H / rel).read_text()
        if t.count(old) != 1 or t.count(new) != 0:
            sys.exit('STOP: %s anchor %r: %d matches' % (rel, old[:60], t.count(old)))
    DST.mkdir()
    for d in ('src', 'test', 'tools', 'notes'):
        shutil.copytree(R2H / d, DST / d, symlinks=True)
    shutil.copy2(R2H / 'image_manifest_r2.tsv', DST / 'image_manifest_r2.tsv')
    prev = DST / 'notes/prev_r2h_final'
    prev.mkdir()
    for f in ('README.md', 'PROGRESS.md', 'SHA256SUMS', 'MANIFEST_SHA256.txt', 'INSTALL_SHA256.txt', 'DIFF_vs_r1.txt'):
        shutil.copy2(R2H / f, prev / f)
    shutil.copytree(R2H / 'reviews', prev / 'reviews')
    shutil.move(str(DST / 'notes/test_logs'), str(prev / 'test_logs'))
    (DST / 'test/r2h_only').mkdir()
    for t in R2H_ONLY_TESTS:
        shutil.move(str(DST / t), str(DST / 'test/r2h_only' / Path(t).name))
    log = []
    for rel, old, new, why in EDITS:
        p = DST / rel
        p.write_text(p.read_text().replace(old, new))
        log.append('%s: %s' % (rel, why))
    shutil.copy2(R2H / VPE, DST / H2 / 'ref/vpe_fix_r2h_66d806ba.py')
    log.append(H2 + 'ref/vpe_fix_r2h_66d806ba.py: byte copy of r2h vpe_fix')
    (DST / H2 / 'tests_r4').mkdir()
    for rel, src in NEW_FILES.items():
        shutil.copy2(HERE / src, DST / rel)
        log.append(rel + ': new')
    # folder names in the carried r2h tests
    for rel in ('test/test_r2h.py', 'test/test_r2h_vpe.py'):
        p = DST / rel
        t = p.read_text()
        if t.count('fixed_image_r2h_20261110') != 1:
            sys.exit('STOP: folder anchor in ' + rel)
        p.write_text(t.replace('fixed_image_r2h_20261110', 'fixed_image_r2i_20261111'))
        log.append(rel + ': folder -> r2i')
    # round-4 digests of the built vpe_fix (the same parts() as the test)
    os.environ.update(PIN_TARGET=str(DST / VPE), PIN_R2H=str(DST / H2 / 'ref/vpe_fix_r2h_66d806ba.py'),
                      PIN_HARNESS=str(DST / H2 / 'tests_existing/harness'))
    import importlib.util
    spec = importlib.util.spec_from_file_location('pins_r4_build', DST / H2 / 'tests_r4/test_pins_r4.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    p = m.parts(m.tree(str(DST / VPE)))
    dig = {k: hashlib.sha256(p[k].encode()).hexdigest() for k in sorted(m.CHANGED)}
    t4 = DST / H2 / 'tests_r4/test_pins_r4.py'
    txt = t4.read_text()
    assert txt.count('DIGESTS = {}   # filled by tools/make_r2i.py from the built file\n') == 1
    t4.write_text(txt.replace('DIGESTS = {}   # filled by tools/make_r2i.py from the built file\n',
                              'DIGESTS = {\n' + ''.join('    %r: %r,\n' % kv for kv in dig.items()) + '}\n'))
    log.append('tests_r4/test_pins_r4.py: DIGESTS of the built r2i parts')
    for f in ('make_r2i.py', 'test_all_r2i.sh', 'finish_r2i.sh'):
        shutil.copy2(HERE / f, DST / 'tools' / f)
    (DST / 'notes/build_edits_r2i.txt').write_text('\n'.join(log) + '\n')
    print('\n'.join(log))
    print('vpe_fix', sha(DST / VPE), 'simple_offboard', sha(DST / SO))


if __name__ == '__main__':
    main()
