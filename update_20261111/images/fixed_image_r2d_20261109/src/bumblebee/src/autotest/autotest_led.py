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


import time
import threading
import rclpy
from rclpy.node import Node
from bumblebee.srv import SetLEDEffect
from led_msgs.srv import SetLEDs
from led_msgs.msg import LEDStateArray, LEDState
from util import handle_response

rclpy.init()
node = Node('autotest_led')
_executor = rclpy.executors.MultiThreadedExecutor()
_executor.add_node(node)
threading.Thread(target=_executor.spin, daemon=True).start()


def _call(client, req, timeout=5.0):
    future = client.call_async(req)
    deadline = time.time() + timeout
    while not future.done() and time.time() < deadline:
        time.sleep(0.01)
    if not future.done():
        raise Exception('Service call timed out')
    return future.result()


def _make_caller(client, req_type):
    def caller(**kwargs):
        req = req_type()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(client, req)
    return handle_response(caller)


set_leds_client   = node.create_client(SetLEDs,      'led/set_leds')
set_effect_client = node.create_client(SetLEDEffect, 'led/set_effect')

set_leds   = _make_caller(set_leds_client,   SetLEDs.Request)
set_effect = _make_caller(set_effect_client, SetLEDEffect.Request)


def wait_for_message(msg_type, topic, timeout=10.0):
    e = threading.Event()
    result = [None]
    def cb(msg):
        result[0] = msg
        e.set()
    sub = node.create_subscription(msg_type, topic, cb, 1)
    e.wait(timeout=timeout)
    node.destroy_subscription(sub)
    if result[0] is None:
        raise Exception('Timeout waiting for ' + topic)
    return result[0]


led_count = len(wait_for_message(LEDStateArray, 'led/state').leds)
print('LED count =', led_count)

print('== Testing effects ==')

input('Fill red [enter] ')
set_effect(r=255, g=0, b=0)

input('Fill green [enter] ')
set_effect(r=0, g=100, b=0)

input('Blink white [enter] ')
set_effect(effect='blink', r=255, g=255, b=255)
time.sleep(3)

input('Blink fast violet [enter] ')
set_effect(effect='blink_fast', r=220, g=20, b=250)
time.sleep(3)

input('Fade to blue [enter] ')
set_effect(effect='fade', r=0, g=0, b=255)

input('Wipe to yellow [enter] ')
set_effect(effect='wipe', r=255, g=255, b=40)

input('Flash red [enter] ')
set_effect(effect='flash', r=255, g=0, b=0)
time.sleep(1)

input('Rainbow [enter] ')
set_effect(effect='rainbow')
time.sleep(4)

input('Rainbow fill [enter] ')
set_effect(effect='rainbow_fill')
time.sleep(4)

input('Turn off [enter] ')
set_effect()

print('== Testing low-level control ==')

input('Fill orange [enter] ')
set_leds(leds=[LEDState(index=i, r=245, g=155, b=0) for i in range(led_count)])

input('Fill blue gradient [enter] ')
set_leds(leds=[LEDState(index=i, r=0, g=20, b=int(255 * i / led_count)) for i in range(led_count)])

input('Animate green dot [enter] ')
set_effect()
for i in range(led_count):
    if i > 0:
        set_leds(leds=[LEDState(index=i - 1, r=0, g=0, b=0)])
    set_leds(leds=[LEDState(index=i, r=0, g=255, b=0)])
    time.sleep(0.05)

input('Turn off [enter] ')
set_effect()
