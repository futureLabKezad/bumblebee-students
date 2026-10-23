#!/usr/bin/env python3
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for check_watch_only.py: it passes today's apps and catches real violations.

    python3 gcs/tools/test_check_watch_only.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_watch_only as cw  # noqa: E402


def problems(text, name='X.swift'):
    return cw.check_text(name, text)


class Rosbridge(unittest.TestCase):
    def test_subscribe_is_allowed(self):
        self.assertEqual(problems('var msg: [String: Any] = ["op": "subscribe", "topic": t]'), [])
        self.assertEqual(problems('Serialize(new { op = "unsubscribe", topic = t })', 'A.cs'), [])

    def test_reading_incoming_publish_is_allowed(self):
        self.assertEqual(problems('(obj["op"] as? String) == "publish",'), [])
        self.assertEqual(problems('if (op.GetString() != "publish") return;', 'A.cs'), [])

    def test_sending_other_ops_fails(self):
        self.assertTrue(problems('let m: [String: Any] = ["op": "call_service", "service": s]'))
        self.assertTrue(problems('Serialize(new { op = "publish", topic = t })', 'A.cs'))
        self.assertTrue(problems('send("{\\"op\\":\\"advertise\\",\\"topic\\":\\"/x\\"}")'))


class FlightNames(unittest.TestCase):
    def test_flight_services_fail(self):
        for line in ['let s = "/mavros/mavros/cmd/arming"',
                     'let s = "/mavros/param/set"',
                     'Topic = "/mavros/setpoint_position/local"',
                     'let t = "mavros_msgs/srv/CommandBool"',
                     'client.call("/navigate", args)',
                     'let port = 14550']:
            self.assertTrue(problems(line), line)

    def test_comments_and_allow_marker_pass(self):
        self.assertEqual(problems('// never call /mavros/cmd/arming from the app'), [])
        self.assertEqual(problems('/* setpoint_raw is not used\n   CommandBool either */\nlet x = 1'), [])
        self.assertEqual(problems('Text("PX4 uses /mavros/param") // watch-only: allow help text'), [])

    def test_ui_words_are_not_flagged(self):
        self.assertEqual(problems('("arming", "MFT180L8O4G4O5C4", "QBASIC"),'), [])
        self.assertEqual(problems('@Published var mode = "OFFBOARD"'), [])
        self.assertEqual(problems('try await api.wifiSetMode(m)'), [])


class RestPaths(unittest.TestCase):
    def test_known_paths_pass(self):
        self.assertEqual(problems('try await ok("POST", "/api/wifi/mode", json: j)'), [])

    def test_unknown_or_dynamic_paths_fail(self):
        self.assertTrue(problems('try await ok("POST", "/api/fcu/arm")'))
        self.assertTrue(problems('try await ok("GET", "/api/wifi/\\(name)")'))
        self.assertTrue(problems('RequestAsync(Get, $"/api/led/{x}")', 'A.cs'))

    def test_doc_comment_paths_are_ignored(self):
        self.assertEqual(problems('/// `/api/wifi/*` backend'), [])

    def test_star_in_a_doc_comment_does_not_hide_the_rest(self):
        # "/api/*" holds "/*": it once opened a block comment that never closed,
        # so nothing after it in DroneAPI.swift was checked.
        text = '/// HTTP client for the drone\'s `/api/*` endpoints\ntry await ok("POST", "/api/fcu/arm")'
        self.assertTrue(problems(text))


class WholeTree(unittest.TestCase):
    def test_current_apps_pass(self):
        self.assertEqual(cw.main(['check', cw.ROOT]), 0)

    def test_a_planted_violation_is_found(self):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, 'gcs', 'windows', 'src')
            os.makedirs(d)
            with open(os.path.join(d, 'Bad.cs'), 'w') as f:
                f.write('var m = new { op = "call_service", service = "/mavros/cmd/arming" };\n')
            self.assertEqual(cw.main(['check', root]), 1)

    def test_missing_sources_is_an_error(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(cw.main(['check', root]), 2)


if __name__ == '__main__':
    unittest.main()
