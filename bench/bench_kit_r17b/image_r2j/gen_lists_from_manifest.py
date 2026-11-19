#!/usr/bin/env python3
# gen_lists_from_manifest.py (Claude, 11.11.2026, набор r4, поручение чата 1 T51).
# Генератор списков набора из манифеста образа (по умолчанию /work/fixed_image_r2j_20261111). Читает ТОЛЬКО файлы образа, ничего на дрон не отправляет, к сети не обращается.
# Образ ещё проходит независимую проверку: если его байты изменятся, чат 1 присылает новые суммы, и списки пересоздаются этим же скриптом:
#   python3 gen_lists_from_manifest.py --image /work/fixed_image_r2j_20261111 --out <папка image_r2j набора> --expect-sums <sha256 файла SHA256SUMS образа> --expect-manifest <sha256 image_manifest_r2.tsv>
# Что пишет в --out (прежние версии переносятся в --aside, ничего не удаляется):
#   CPP_SOURCES_<метка>.tsv   sha256 TAB путь TAB флаг: CMakeLists.txt, package.xml, все src/cpp/* (флаг R, если против дрона a45a264 файл changed или new) + 5 скриптов полёта examples/ (флаг «-»)
#   RUNTIME_PY_<метка>.tsv    sha256 TAB LAUNCH|FCU TAB путь: launch/*.py пакета bumblebee и scripts/fcu_detect.py (колонка образа в манифесте)
#   INSTALL_SHA256_<метка>.txt  байтовая копия INSTALL_SHA256.txt образа (python-узлы по sha256, бинарные узлы только по именам)
#   required_shas.txt     HOVER_R6 и CAMERA_VARIANT берутся из прежнего required_shas.txt (они вне манифеста образа), CAMERA_DEFAULT и FLIGHT_PY из манифеста
#   R2J_SOURCE.txt (<МЕТКА>_SOURCE.txt)  откуда взято и суммы
# Код выхода: 0 готово; 2 суммы образа не сошлись или список неполон (ничего не записано).
import argparse, hashlib, os, shutil, sys, time

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def die(msg):
    print('STOP: ' + msg, file=sys.stderr)
    sys.exit(2)

ap = argparse.ArgumentParser()
ap.add_argument('--image', default='/work/fixed_image_r2j_20261111')
ap.add_argument('--out', required=True)
ap.add_argument('--tag', default='r2j')
ap.add_argument('--provisional', default='')
ap.add_argument('--aside', default='')
ap.add_argument('--expect-sums', required=True)   # обязательны: без ожидаемых сумм список не создаётся
ap.add_argument('--expect-manifest', required=True)
ap.add_argument('--takeoff', default='', help='путь к takeoff.conf набора: обновляет SCRIPT_SHA256 (если скрипт flight.py) и DRONE_PY_SHA256 по манифесту')
a = ap.parse_args()
img, out, TAG = a.image, a.out, a.tag
man = os.path.join(img, 'image_manifest_r2.tsv')
sums = os.path.join(img, 'SHA256SUMS')
for p in (man, sums, os.path.join(img, 'INSTALL_SHA256.txt')):
    if not os.path.isfile(p):
        die('нет файла ' + p)
# 1. суммы образа
for line in open(sums, encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    want, name = line.split(None, 1)
    got = sha(os.path.join(img, name.strip()))
    if got != want:
        die('SHA256SUMS образа не сходится для ' + name + ': ' + got + ' вместо ' + want)
sums_sha, man_sha = sha(sums), sha(man)
if sums_sha != a.expect_sums:
    die('sha256 SHA256SUMS образа ' + sums_sha + ' не равен ожидаемому ' + a.expect_sums)
if man_sha != a.expect_manifest:
    die('sha256 image_manifest_r2.tsv ' + man_sha + ' не равен ожидаемому ' + a.expect_manifest)
# 2. манифест
rows = {}
for line in open(man, encoding='utf-8'):
    line = line.rstrip('\n')
    if not line or line.startswith('#'):
        continue
    f = line.split('\t')
    if len(f) < 5:
        die('строка манифеста не из 5 колонок: ' + line[:120])
    rows[f[0]] = f
P = 'drone/ros2_ws/src/bumblebee/'
def srcfile(rel):
    return os.path.join(img, 'src', 'bumblebee', rel)
def need(rel):
    r = rows.get(P + rel)
    if r is None:
        die('в манифесте нет ' + P + rel)
    return r

def verify_in_src(rel, want):
    p = srcfile(rel)
    if not os.path.isfile(p):
        die('нет файла образа ' + p)
    if sha(p) != want:
        die('sha256 файла ' + p + ' не равен колонке образа в манифесте (' + want + ')')

cpp = []
for rel in ['CMakeLists.txt', 'package.xml'] + sorted(r[len(P):] for r in rows if r.startswith(P + 'src/cpp/') and '/' not in r[len(P + 'src/cpp/'):]):
    r = need(rel)
    verify_in_src(rel, r[2])
    flag = 'R' if (r[4].startswith('changed') or r[4].startswith('new')) else '-'
    cpp.append((r[2], 'ros2_ws/src/bumblebee/' + rel, flag))
for rel in ['examples/drone.py', 'examples/flight/flight.py', 'examples/flight/flight_marker.py', 'examples/flight/flight_marker_loop.py', 'examples/flight_profile.py']:
    r = need(rel)
    verify_in_src(rel, r[2])
    cpp.append((r[2], 'ros2_ws/src/bumblebee/' + rel, '-'))
rt = []
for rel in sorted(r[len(P):] for r in rows if r.startswith(P + 'launch/') and r.endswith('.py')):
    r = need(rel)
    verify_in_src(rel, r[2])
    rt.append((r[2], 'LAUNCH', rel))
fr = need('scripts/fcu_detect.py')   # sha образа 5932a00a… (исправление порта); в src образа может лежать прежний (известное расхождение), поэтому с src не сверяется
rt.append((fr[2], 'FCU', 'ros2_ws/src/bumblebee/scripts/fcu_detect.py'))
if len(cpp) < 10 or len(rt) < 3:
    die('списки неполные: cpp=%d rt=%d' % (len(cpp), len(rt)))
# 3. required_shas
prev = os.path.join(out, 'required_shas.txt')
if not os.path.isfile(prev):
    die('нет прежнего required_shas.txt (HOVER_R6 и CAMERA_VARIANT берутся из него): ' + prev)
pv = {}
head = []
for line in open(prev, encoding='utf-8'):
    line = line.rstrip('\n')
    if line.startswith('#'):
        head.append(line)
    elif '=' in line:
        k, v = line.split('=', 1)
        pv[k] = v
for k in ('HOVER_R6_SHA256', 'CAMERA_VARIANT_SHA256'):
    if len(pv.get(k, '')) != 64:
        die('в прежнем required_shas.txt нет ' + k)
cam = need('src/python/camera_fix.py')[2]
flight = need('examples/flight/flight.py')[2]
req = head + ['HOVER_R6_SHA256=' + pv['HOVER_R6_SHA256'], 'CAMERA_DEFAULT_SHA256=' + cam, 'CAMERA_VARIANT_SHA256=' + pv['CAMERA_VARIANT_SHA256'], 'FLIGHT_PY_SHA256=' + flight]
# 4. запись (прежние версии в --aside)
stamp = time.strftime('%Y%m%d_%H%M%S')
aside = a.aside or os.path.join(os.path.dirname(os.path.abspath(out)), '_gen_aside_' + stamp)
def put(name, text=None, copy_from=None):
    dst = os.path.join(out, name)
    if os.path.exists(dst):
        os.makedirs(aside, exist_ok=True)
        shutil.move(dst, os.path.join(aside, name))
    if copy_from:
        shutil.copyfile(copy_from, dst)
    else:
        with open(dst, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    return dst
hdr_cpp = ('# C++ исходники и файлы сборки пакета bumblebee из образа ' + TAG + ' (колонки: sha256_fixed_image, путь относительно DEST_ROOT=/home/lb, R = r2i меняет файл против образа на дроне a45a264: нужна пересборка пакета на Pi). '
           'Источник: ' + img + '/image_manifest_r2.tsv (sha256 файла манифеста: ' + man_sha + '). Создан генератором gen_lists_from_manifest.py. '
           'ПЛЮС скрипты полёта examples/ образа с флагом «-» (drone.py, flight.py, flight_marker.py, flight_marker_loop.py, flight_profile.py): их sha256 на Pi и в копии оверлея тоже обязаны совпасть, потому что скрипты полёта берут drone.py оттуда (sys.path.insert).\n')
put('CPP_SOURCES_' + TAG + '.tsv', hdr_cpp + ''.join('%s\t%s\t%s\n' % c for c in cpp))
hdr_rt = ('# Launch-файлы пакета bumblebee и scripts/fcu_detect.py образа ' + TAG + ' (создан генератором gen_lists_from_manifest.py из ' + img + '/image_manifest_r2.tsv, sha256 манифеста ' + man_sha + '). Колонки: sha256 TAB вид TAB путь.\n'
          '# LAUNCH = файл launch/<имя> в install пакета, который реально берёт «ros2 launch bumblebee bumblebee.launch.py» (<префикс>/share/bumblebee/<путь>; в 09 префикс от ros2 pkg prefix, в 15 префикс оверлея ' + TAG + ').\n'
          '# FCU = файл, который запускает start_bumblebee.sh до MAVROS по ПОЛНОМУ пути /home/lb/ros2_ws/src/bumblebee/scripts/fcu_detect.py (путь от HOME). Это ИСПРАВЛЕНИЕ ПОРТА fcu_detect_fix_01 (на дроне с 05.11 14:10, sha256 из колонки образа): в src образа лежит ПРЕЖНИЙ a45a264 (ee174fd1...), образом fcu_detect.py НЕ ставится (решение чата 1, 22:00). Ждём исправленный; прежний = DIFF = СТОП.\n')
put('RUNTIME_PY_' + TAG + '.tsv', hdr_rt + ''.join('%s\t%s\t%s\n' % c for c in rt))
put('INSTALL_SHA256_' + TAG + '.txt', copy_from=os.path.join(img, 'INSTALL_SHA256.txt'))
put('required_shas.txt', '\n'.join(req) + '\n')
src_txt = ['# Источник образа ' + TAG + ' для набора r4 (создан генератором gen_lists_from_manifest.py, ' + time.strftime('%Y-%m-%d %H:%M:%S') + ').',
           'образ: ' + img, 'sha256 файла SHA256SUMS образа: ' + sums_sha, 'sha256 image_manifest_r2.tsv: ' + man_sha,
           'sha256 INSTALL_SHA256.txt: ' + sha(os.path.join(img, 'INSTALL_SHA256.txt')),
           'строк в CPP_SOURCES_%s.tsv: %d (из них R: %d), в RUNTIME_PY_%s.tsv: %d (LAUNCH: %d, FCU: 1)' % (TAG, len(cpp), sum(1 for c in cpp if c[2] == 'R'), TAG, len(rt), len(rt) - 1)]
for c in cpp:
    src_txt.append('cpp %s %s %s' % c)
src_txt.append('camera_fix.py (по умолчанию) ' + cam)
src_txt.append('flight.py ' + flight)
if a.provisional:
    src_txt.insert(1, 'ВРЕМЕННО: ' + a.provisional)
src_txt.append('прежние версии списков перенесены в: ' + (aside if os.path.isdir(aside) else '(ничего не заменялось)'))
put('R2J_SOURCE.txt'.replace('R2J', TAG.upper()), '\n'.join(src_txt) + '\n')
# 5. takeoff.conf (по желанию): SCRIPT_SHA256 для flight.py и DRONE_PY_SHA256 из манифеста; прежний файл уносится в --aside
if a.takeoff:
    import re
    drone = need('examples/drone.py')[2]
    txt = open(a.takeoff, encoding='utf-8', newline='').read()
    m = re.search(r'(?m)^SCRIPT_REMOTE_PATH=(.*)$', txt)
    if not m:
        die('в takeoff.conf нет SCRIPT_REMOTE_PATH')
    new = txt
    note = ''
    if m.group(1).strip().endswith('/examples/flight/flight.py'):
        new, n1 = re.subn(r'(?m)^SCRIPT_SHA256=[0-9a-f]{64}$', 'SCRIPT_SHA256=' + flight, new)
        if n1 != 1:
            die('в takeoff.conf не одна строка SCRIPT_SHA256=<64 hex>')
    else:
        note = ' (скрипт не flight.py: SCRIPT_SHA256 не менялся)'
    new, n2 = re.subn(r'(?m)^DRONE_PY_SHA256=[0-9a-f]{64}$', 'DRONE_PY_SHA256=' + drone, new)
    if n2 != 1:
        die('в takeoff.conf не одна строка DRONE_PY_SHA256=<64 hex>')
    if new != txt:
        os.makedirs(aside, exist_ok=True)
        shutil.copyfile(a.takeoff, os.path.join(aside, 'takeoff.conf'))
        with open(a.takeoff, 'w', encoding='utf-8', newline='') as f:
            f.write(new)
    print('takeoff.conf: flight.py ' + flight + ', drone.py ' + drone + note)
print('OK: cpp=%d (R=%d) rt=%d; SHA256SUMS образа %s; манифест %s' % (len(cpp), sum(1 for c in cpp if c[2] == 'R'), len(rt), sums_sha, man_sha))
