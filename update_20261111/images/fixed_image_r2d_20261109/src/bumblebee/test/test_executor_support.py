"""No ROS: protect inherited executor dispatch and exception propagation."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class ExecutorSupportTests(unittest.TestCase):
    def setUp(self):
        self.dispatch = Mock()
        delegate = self.dispatch

        class OriginalExecutor:
            def __init__(self, *args, **kwargs):
                self.initial_arguments = (args, kwargs)

            def _spin_once_impl(self, *args, **kwargs):
                return delegate(*args, **kwargs)

        executors = types.ModuleType('rclpy.executors')
        executors.MultiThreadedExecutor = OriginalExecutor
        ros = types.ModuleType('rclpy')
        ros.__path__ = []
        path = Path(__file__).with_name('executor_support.py')
        spec = importlib.util.spec_from_file_location('_executor_support_guard', path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'rclpy': ros, 'rclpy.executors': executors}):
            spec.loader.exec_module(self.module)
        self.yield_call = Mock()
        # Replace only this module's binding, never the process-wide time module.
        self.module.time = types.SimpleNamespace(sleep=self.yield_call)
        self.executor = self.module.CooperativeExecutor(num_threads=4)

    def test_original_dispatch_once_arguments_return_and_yield_order(self):
        result, condition = object(), object()
        order = []
        self.dispatch.side_effect = lambda *a, **kw: order.append('dispatch') or result
        self.yield_call.side_effect = lambda delay: order.append('yield')
        actual = self.executor._spin_once_impl(.25, condition=condition)
        self.assertIs(actual, result)
        self.dispatch.assert_called_once_with(.25, condition=condition)
        self.yield_call.assert_called_once_with(0)
        self.assertEqual(order, ['dispatch', 'yield'])
        self.assertEqual(self.executor.initial_arguments, ((), {'num_threads': 4}))

    def test_original_exception_preserved_and_yield_attempted_once(self):
        original = ValueError('original dispatch failed')
        self.dispatch.side_effect = original
        with self.assertRaises(ValueError) as caught:
            self.executor._spin_once_impl(timeout_sec=.1)
        self.assertIs(caught.exception, original)
        self.dispatch.assert_called_once_with(timeout_sec=.1)
        self.yield_call.assert_called_once_with(0)

    def test_yield_error_cannot_mask_original_dispatch_error(self):
        original = KeyboardInterrupt('original shutdown')
        self.dispatch.side_effect = original
        self.yield_call.side_effect = RuntimeError('secondary yield failure')
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.executor._spin_once_impl()
        self.assertIs(caught.exception, original)
        self.dispatch.assert_called_once_with()
        self.yield_call.assert_called_once_with(0)

    def test_yield_error_after_success_is_reported(self):
        failure = RuntimeError('yield failed')
        self.yield_call.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            self.executor._spin_once_impl(timeout_sec=0)
        self.assertIs(caught.exception, failure)
        self.dispatch.assert_called_once_with(timeout_sec=0)
        self.yield_call.assert_called_once_with(0)


if __name__ == '__main__':
    unittest.main()
