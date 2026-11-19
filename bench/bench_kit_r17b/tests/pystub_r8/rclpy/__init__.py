# pystub_r8/rclpy (Claude, 13.11.2026, набор r8) - ТОЛЬКО ДЛЯ ТЕСТОВ pi/r8_marker_wake.sh в WSL: настоящий ROS не нужен и не трогается.
# Сценарий - переменная BB_R8_SCN: r2j_ok | rc3 | armed | noconn | nostate | armed_during | false5 | false38.
# Журнал вызовов - файл BB_R8_STUBLOG: SUB <тема>, PUB <тема>, PUBLISH <тема> data=..., TIMER, DESTROY_TIMER, INIT, SHUTDOWN.
import os
from .node import Node


def _log(s):
    p = os.environ.get('BB_R8_STUBLOG')
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
