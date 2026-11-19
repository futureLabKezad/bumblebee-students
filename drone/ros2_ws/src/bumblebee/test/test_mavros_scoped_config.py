"""Host checks of read-only MAVROS naming/config migration; no ROS connection."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1]/'launch/mavros_scoped_config.py'
spec = importlib.util.spec_from_file_location('mavros_scoped_config', HELPER)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def legacy():
    return {'mavros': {'ros__parameters': {'fcu_url': 'udp://127.0.0.1:14540@127.0.0.1:14580',
                'tgt_system': 1, 'plugin_allowlist': ['local_position','vision_pose','param','setpoint_position','setpoint_attitude']}},
            'mavros/mavros': {'ros__parameters': {'tf.send': True, 'tf.frame_id': 'map', 'tf.child_frame_id': 'base_link'}}}


class ScopedConfiguration(unittest.TestCase):
    def test_preserves_original_and_supplied_values(self):
        original = legacy(); before = copy.deepcopy(original)
        converted = m.scoped_config(original)
        self.assertEqual(original,before)
        self.assertEqual(converted['mavros'],original['mavros'])
        self.assertEqual(converted['mavros_node'],original['mavros'])
        self.assertEqual(converted['mavros/local_position'],original['mavros/mavros'])
        self.assertNotIn('setpoint_raw',converted['mavros']['ros__parameters']['plugin_allowlist'])
        self.assertNotIn('use_quaternion',str(converted))

    def test_rejects_missing_empty_or_unexpected_sections(self):
        for bad in (None, {}, {'mavros':{}}, {'mavros':{'ros__parameters':[]}},
                    {'mavros':{'ros__parameters':{}}}):
            with self.assertRaises(ValueError): m.scoped_config(bad)
        bad=legacy();bad['mavros/mavros']['ros__parameters']['unknown_plugin_option']=True
        with self.assertRaises(ValueError):m.scoped_config(bad)

    def test_conflicting_container_and_local_parameters_abort(self):
        for section, values in (('mavros_node',{'fcu_url':'/dev/other'}),
                                ('mavros/local_position',{'tf.send':False})):
            bad=legacy();bad[section]={'ros__parameters':values}
            with self.assertRaises(ValueError):m.scoped_config(bad)

    def test_explicit_sim_clock_and_transport_override_preserve_allowlist(self):
        original=legacy();converted=m.scoped_config(original,use_sim_time=True,fcu_url='udp://test',tgt_system=3)
        for section in converted.values():self.assertTrue(section['ros__parameters']['use_sim_time'])
        for section in ('mavros','mavros_node'):
            self.assertEqual(converted[section]['ros__parameters']['fcu_url'],'udp://test')
            self.assertEqual(converted[section]['ros__parameters']['tgt_system'],3)
        self.assertEqual(original,legacy())
        bad=legacy();bad['mavros']['ros__parameters']['use_sim_time']=False
        with self.assertRaises(ValueError):m.scoped_config(bad,use_sim_time=True)

    def test_only_param_identity_is_renamed_and_vision_has_no_local_output_alias(self):
        self.assertEqual(m.MAVROS_ARGUMENTS,['--ros-args','-r','param:__node:=mavros'])
        mapping=dict(m.MAVROS_REMAPPINGS)
        self.assertNotIn('/mavros/vision_pose/pose',mapping)
        self.assertNotIn('/mavros/local_position/pose_cov',mapping)
        self.assertNotEqual(mapping['/mavros/local_position/pose'],mapping['/mavros/vision_pose/pose_cov'])
        self.assertEqual(mapping['/mavros/vision_pose/pose_cov'],'/mavros/mavros/pose_cov')
        self.assertEqual(mapping['/mavros/cmd/arming'],'/mavros/mavros/arming')


if __name__=='__main__':unittest.main()
