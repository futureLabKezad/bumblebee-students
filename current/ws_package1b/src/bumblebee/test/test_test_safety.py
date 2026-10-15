import tempfile
import unittest
from pathlib import Path
from test_safety import validate_environment,topic

class GuardTests(unittest.TestCase):
    def test_drone_marker(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'bumblebee_version';f.touch()
            with self.assertRaises(RuntimeError):validate_environment(markers=[f])
    def test_vehicle_nodes(self):
        for name in ['mavros','simple_offboard']:
            with self.assertRaises(RuntimeError):validate_environment(markers=[],nodes=[(name,'/')])
    def test_state_publisher(self):
        with self.assertRaises(RuntimeError):validate_environment(markers=[],state_publishers=1)
    def test_private_namespace(self):
        validate_environment(markers=[],nodes=[('simple_offboard_tested','/tests')])
        self.assertTrue(topic('/mavros/state').startswith('/bb_test_'))
        self.assertNotEqual(topic('/mavros/state'),'/mavros/state')

if __name__=='__main__':unittest.main()
