#!/usr/bin/env python3
"""Read-only check of the camera buffer layout (the premise of the full-row fix). Subscribes only; publishes nothing.

Takes --n messages of /main_camera/image_raw_yuv and for each reports height, width, step, encoding, data length,
the candidate's own full_row_layout() verdict (pitch 1600, row_period 5) and the smallest line pitch P > 2*width
(step 16 bytes) whose padding bytes are all zero. Saves the first message (raw_frame_0.bin + meta.json) and the
legacy and full-row mono8 images of it (PNG), so the layout can be re-checked offline on the PC.
Prints 'RAW CHECK ГОТОВО: ...' only when every frame has step 1280, 614400 bytes and zero padding at pitch 1600.
Usage: python3 raw_layout_check.py --out DIR --candidate /path/camera_fix.py [--n 5]
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


def smallest_zero_pitch(raw, width):
    w2 = 2 * width
    for P in range(w2 + 16, 4 * width + 1, 16):
        n_pad = raw.size // P
        if n_pad < 2:
            break
        pad = np.lib.stride_tricks.as_strided(raw[w2:], shape=(n_pad, P - w2), strides=(P, 1), writeable=False)
        if not pad.any():
            return P
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--candidate', required=True)
    ap.add_argument('--topic', default='/main_camera/image_raw_yuv')
    ap.add_argument('--n', type=int, default=5)
    ap.add_argument('--timeout', type=float, default=20.0)
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        print('СТОП: %s уже есть (не перезаписываю)' % out)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location('cf_cand', a.candidate)
    cand = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cand)
    rclpy.init()
    node = Node('camera_fullrow_raw_check')
    msgs = []
    node.create_subscription(Image, a.topic, lambda m: msgs.append(m) if len(msgs) < a.n else None,
                             qos_profile_sensor_data)
    t_end = node.get_clock().now().nanoseconds * 1e-9 + a.timeout
    while len(msgs) < a.n and node.get_clock().now().nanoseconds * 1e-9 < t_end:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()
    if not msgs:
        print('СТОП: за %.0f с нет ни одного кадра на %s' % (a.timeout, a.topic))
        sys.exit(1)
    out.mkdir(parents=True)
    rows, ok = [], True
    for i, m in enumerate(msgs):
        raw = np.frombuffer(bytes(m.data), np.uint8)
        n_rows, why = cand.full_row_layout(raw, m.height, m.width, m.step, 1600, 5)
        r = dict(i=i, height=m.height, width=m.width, step=m.step, encoding=m.encoding, length=int(raw.size),
                 full_row_layout_rows=int(n_rows), reason=why, smallest_zero_pitch=smallest_zero_pitch(raw, m.width),
                 zero_byte_share=round(float((raw == 0).mean()), 4))
        rows.append(r)
        good = (m.encoding == 'yuv422_yuy2' and m.width == 640 and m.height == 480 and m.step == 1280
                and raw.size == 614400 and n_rows == 384 and r['smallest_zero_pitch'] == 1600)
        ok = ok and good
        print(json.dumps(r))
        if i == 0:
            (out / 'raw_frame_0.bin').write_bytes(raw.tobytes())
            if raw.size == m.height * m.step:
                legacy = np.repeat(raw.reshape(m.height, m.step)[0::5].reshape(-1, m.width, 2)[..., 0], 5, axis=0)[:m.height]
                cv2.imwrite(str(out / 'frame0_legacy.png'), np.ascontiguousarray(legacy))
            if n_rows:
                plan = cand.full_row_plan(m.height, m.width, 1600, 5, n_rows)
                cv2.imwrite(str(out / 'frame0_fullrow.png'), cand.full_row_gray(raw, m.height, m.width, 1600, n_rows, plan))
    (out / 'meta.json').write_text(json.dumps(dict(topic=a.topic, frames=rows, ok=ok), indent=1) + '\n')
    if ok:
        print('RAW CHECK ГОТОВО: %d/%d кадров: step 1280, 614400 байт, нули в заполнении при шаге 1600 (%s)'
              % (len(rows), len(rows), out))
    else:
        print('СТОП: раскладка кадра не та, что ожидалась (см. %s/meta.json) — прислать Claude' % out)
        sys.exit(1)


if __name__ == '__main__':
    main()
