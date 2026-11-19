"""Cooperative dispatch only for the isolated ROS test harnesses.

The installed executor still owns callbacks, groups, timers and worker threads.
See README_RUNTIME.md for the controlled A/B evidence and the upstream source.
"""
import time

from rclpy.executors import MultiThreadedExecutor


class CooperativeExecutor(MultiThreadedExecutor):
    """Yield Python execution after each unchanged inherited dispatch."""

    def _spin_once_impl(self, *args, **kwargs):
        try:
            result = super()._spin_once_impl(*args, **kwargs)
        except BaseException:
            # Preserve the dispatch exception even if yielding also fails.
            try:
                time.sleep(0)
            except BaseException:
                pass
            raise
        time.sleep(0)
        return result
