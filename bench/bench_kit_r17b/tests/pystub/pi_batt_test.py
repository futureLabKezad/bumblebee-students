# Запуск main() из pi\battery_check.sh с поддельным rclpy (tests\pystub). Печатает вывод main и итоговые данные поддельных узлов.
import os, sys, io, runpy, contextlib
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
code = sys.argv[1]
os.environ['BB_BATT_MAIN'] = '0'
dur = sys.argv[2]
sys.argv = ['x', dur]
ns = runpy.run_path(code, run_name='bbtest')
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = ns['main']()
sys.stdout.write(buf.getvalue())
import rclpy
n = rclpy._nodes[0] if rclpy._nodes else None
print('STUB_PUBLISHERS ' + (','.join(p.topic for p in n.pubs) if n and n.pubs else 'none'))
print('STUB_SERVICE_CALLS %d' % (len(n.service_calls) if n else 0))
print('STUB_RC %s' % rc)
