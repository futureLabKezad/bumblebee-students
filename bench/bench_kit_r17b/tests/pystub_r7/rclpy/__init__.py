# pystub_r7/rclpy (Claude, 13.11.2026, набор r7) - ТОЛЬКО ДЛЯ ТЕСТОВ pi/r7_marker_ids.sh в WSL: настоящий ROS не нужен и не трогается.
# Сценарий - переменная BB_R7_SCN: asleep | awake_ok | awake_false | armed | noconn | nostate | armed_during | awake_nomsg.
# Журнал вызовов - файл BB_R7_STUBLOG: SUB <тема>, PUB <тема>, INIT, SHUTDOWN.
import os, time
from .node import Node


def _log(s):
    p = os.environ.get('BB_R7_STUBLOG')
    if p:
        with open(p, 'a') as f:
            f.write(s + '\n')


_log('STUB rclpy imported')


def init(args=None):
    _log('INIT')


def shutdown():
    _log('SHUTDOWN')


def create_node(name):
    _log('NODE ' + name)
    return Node(name, _log)


def spin_once(node, timeout_sec=None):
    node._spin(timeout_sec or 0.0)