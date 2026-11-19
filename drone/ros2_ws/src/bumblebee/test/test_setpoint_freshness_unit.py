"""Stamp and resume policy checks without ROS or a vehicle."""
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

NODE = Path(__file__).resolve().parents[1] / 'src/python/setpoint_freshness.py'
spec = importlib.util.spec_from_file_location('filter_policy', NODE)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
S = 1000000000


class CommandAge(unittest.TestCase):
    def test_age_exact_limit_and_over(self):
        self.assertIsNone(m.command_rejection(10*S, 10*S-500000000))
        self.assertEqual(m.command_rejection(10*S, 10*S-500000001), 'stale')

    def test_future_exact_limit_and_over(self):
        self.assertIsNone(m.command_rejection(10*S, 10*S+100000000))
        self.assertEqual(m.command_rejection(10*S, 10*S+100000001), 'future')

    def test_unknown_and_invalid_stamps(self):
        self.assertEqual(m.command_rejection(0, 10*S), 'clock_unknown')
        for stamp in (0, -1, None):
            self.assertEqual(m.command_rejection(10*S, stamp), 'stamp_unknown')
        self.assertIsNone(m.stamp_ns(SimpleNamespace(sec=1, nanosec=S)))
        self.assertEqual(m.stamp_ns(SimpleNamespace(sec=1, nanosec=1)), S+1)

    def test_clock_reset_drops_old_future_message(self):
        self.assertEqual(m.command_rejection(8*S, 10*S), 'future')

    def test_resume_watermark_drops_queue_even_inside_sim_age_limit(self):
        self.assertEqual(m.command_rejection(10240000000, 10*S, 10240000000), 'queued_before_filter_resume')
        self.assertEqual(m.command_rejection(10240000000, 10240000000, 10240000000), 'queued_before_filter_resume')
        self.assertIsNone(m.command_rejection(10250000000, 10250000000, 10240000000))

    def test_jazzy_dictionary_message_info_and_unknown_metadata(self):
        self.assertEqual(m.dds_source_timestamp({'source_timestamp': 123}), 123)
        self.assertEqual(m.dds_source_timestamp(SimpleNamespace(source_timestamp=456)), 456)
        for info in ({}, {'source_timestamp': None}, {'source_timestamp': float('nan')}, None):
            self.assertEqual(m.dds_source_timestamp(info), 0)

    def test_all_six_routes_are_explicit_and_no_command_clients(self):
        self.assertEqual(len(m.CHANNELS), 6)
        self.assertEqual(len({x[0] for x in m.CHANNELS}), 6)
        self.assertEqual(len({x[3] for x in m.CHANNELS}), 6)
        self.assertEqual({x[1] for x in m.CHANNELS}, {'PoseStamped','PositionTarget','AttitudeTarget','TwistStamped','Thrust'})
        self.assertNotIn('create_client', NODE.read_text())


class ResumeClock(unittest.TestCase):
    def test_live_wall_timer_with_paused_ros_clock_keeps_control(self):
        g = m.ClockResumeGuard()
        for i in range(100):
            self.assertIsNone(g.observe(i*50000000, 10*S, True))
        self.assertFalse(g.need_clock)

    def test_short_pause_does_not_create_resume_gate(self):
        g = m.ClockResumeGuard()
        g.observe(10*S, 10*S, True)
        self.assertIsNone(g.observe(10100000000, 10020000000, True))
        self.assertFalse(g.need_clock)

    def test_wall_gap_requires_new_live_clock_before_forwarding(self):
        g = m.ClockResumeGuard()
        g.observe(10*S, 10*S, True, 10*S)
        self.assertEqual(g.observe(11200000000, 10*S, True, 11200000000), 'clock_after_resume_required')
        self.assertFalse(g.receive_clock(12*S, 11*S, 12*S, 12*S))
        self.assertFalse(g.receive_clock(12*S, 12*S, 0, 12*S))
        self.assertFalse(g.receive_clock(12*S, 12*S, 10*S, 12*S))
        self.assertFalse(g.receive_clock(12*S, 12*S, 13*S, 12*S))
        self.assertTrue(g.receive_clock(12*S, 12*S, 12*S, 12*S))
        self.assertEqual(g.observe(12*S, 10*S, True), 'clock_after_resume_required')
        self.assertIsNone(g.observe(12050000000, 12*S, True))
        self.assertEqual(g.resume_floor_ns, 12*S)

    def test_system_clock_does_not_need_sim_clock_delivery(self):
        g = m.ClockResumeGuard()
        g.observe(10*S, 10*S, False)
        self.assertIsNone(g.observe(12*S, 12*S, False))
        self.assertFalse(g.need_clock)

    def test_clock_unknown_never_unblocks_resume(self):
        g = m.ClockResumeGuard()
        g.observe(10*S, 10*S, True)
        g.observe(12*S, 10*S, True, 12*S)
        self.assertFalse(g.receive_clock(0, 12*S, 12*S, 12*S))
        self.assertEqual(g.observe(12050000000, 10*S, True), 'clock_after_resume_required')

    def test_recent_queued_clock_before_resume_cannot_unblock_later_queued_command(self):
        g = m.ClockResumeGuard()
        g.observe(10*S, 10*S, True, 100*S)
        # At low RTF a command queued late during the pause is newer than a
        # recently queued /clock; DDS age alone would previously accept it.
        g.observe(11200000000, 10*S, True, 101200000000)
        self.assertFalse(g.receive_clock(10220000000, 11200000000,
                                         101190000000, 101200000000))
        self.assertEqual(g.observe(11250000000, 10220000000, True, 101250000000),
                         'clock_after_resume_required')
        self.assertTrue(g.receive_clock(10250000000, 11250000000,
                                        101250000000, 101250000000))
        self.assertIsNone(g.observe(11300000000, 10250000000, True, 101300000000))
        self.assertEqual(m.command_rejection(10250000000, 10230000000, g.resume_floor_ns),
                         'queued_before_filter_resume')

    def test_unknown_system_wall_time_fails_closed_after_pause(self):
        g = m.ClockResumeGuard()
        g.observe(10*S, 10*S, True)
        g.observe(12*S, 10*S, True)
        self.assertFalse(g.receive_clock(12*S, 12*S, 12*S, 12*S))


if __name__ == '__main__':
    unittest.main()
