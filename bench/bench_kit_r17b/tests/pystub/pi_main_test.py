# Запуск main() из pi\vision_measure.sh с поддельным rclpy (tests\pystub). Печатает вывод main и итоговые данные поддельных издателей.
import os, sys, io, runpy, contextlib
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
code = sys.argv[1]
os.environ['BB_BENCH_MAIN'] = '0'
dur, label, mode, wake = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
sys.argv = ['x', dur, label, mode, wake]
ns = runpy.run_path(code, run_name='bbtest')
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = ns['main']()
sys.stdout.write(buf.getvalue())
import rclpy
n = rclpy._nodes[0] if rclpy._nodes else None
print('STUB_PUBLISHERS ' + (','.join(p.topic for p in n.pubs) if n and n.pubs else 'none'))
print('STUB_PUBLISHED_COUNT %d' % (len(n.published) if n else 0))
print('STUB_RC %s' % rc)