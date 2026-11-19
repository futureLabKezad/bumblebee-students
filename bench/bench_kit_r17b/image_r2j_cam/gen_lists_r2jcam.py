#!/usr/bin/env python3
"""gen_lists_r2jcam.py (Claude, 12.11.2026, набор r6) - списки и полезная нагрузка варианта образа «r2j + камера полных строк» (r2jf).

Только читает образ r2jf и списки r2j набора; пишет НОВЫЕ файлы в папку варианта (существующие не перезаписывает: код 3).
Что проверяет до записи (иначе код 2, ничего не записано):
  - sha256 файла SHA256SUMS образа = --expect-sums (образ не тот или изменён);
  - camera_fix.py и bumblebee.launch.py образа (src и install, install/share) равны строкам его SHA256SUMS и между собой
    (src = install), а их sha256 = dabd5076... и 5f0954d8... (--expect-camera, --expect-launch);
  - r2jf = r2j во всём, что сверяют 09 и 15, КРОМЕ этих двух файлов: каждый python-узел из INSTALL_SHA256_r2j.txt лежит в install образа
    с той же суммой (кроме camera_fix.py), каждый launch-файл из RUNTIME_PY_r2j.tsv лежит в install/share образа с той же суммой
    (кроме launch/bumblebee.launch.py);
  - в каждом из двух новых списков отличается ровно одна строка против r2j.
Пишет: INSTALL_SHA256_r2jcam.txt, RUNTIME_PY_r2jcam.tsv (списки для 09c и 15c), VARIANT_FILES.tsv (4 места на Pi: путь от HOME, sha r2j, sha варианта),
       image_manifest.final.tsv (4 строки для image_install.sh), payload/... (4 копии двух файлов), R2JCAM_SOURCE.txt (откуда что взято).
Запуск (WSL): python3 -I gen_lists_r2jcam.py --kit <папка набора r6> --image /work/fixed_image_r2jf_20261112 --expect-sums <sha256 SHA256SUMS r2jf>
"""
import argparse
import datetime
import hashlib
import os
import shutil
import sys

CAM = 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'
LAUNCH = '5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294'
CAM_R2J = '4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310'
LAUNCH_R2J = '62be01dbb13305bca321d538690252863dedadb8a376e65e54d9f6c15116bf15'
# место на Pi (от HOME=/home/lb) -> (файл образа, sha r2j, sha варианта, режим или '')
TARGETS = [
    ('ros2_ws/src/bumblebee/src/python/camera_fix.py', 'src/bumblebee/src/python/camera_fix.py', CAM_R2J, CAM, ''),
    ('ros2_ws/src/bumblebee/launch/bumblebee.launch.py', 'src/bumblebee/launch/bumblebee.launch.py', LAUNCH_R2J, LAUNCH, ''),
    ('bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py', 'install/bumblebee/lib/bumblebee/camera_fix.py', CAM_R2J, CAM, '755'),
    ('bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py', 'install/bumblebee/share/bumblebee/launch/bumblebee.launch.py', LAUNCH_R2J, LAUNCH, ''),
]


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def die(code, msg):
    print('STOP:', msg)
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kit', required=True)
    ap.add_argument('--image', default='/work/fixed_image_r2jf_20261112')
    ap.add_argument('--expect-sums', required=True)
    ap.add_argument('--expect-camera', default=CAM)
    ap.add_argument('--expect-launch', default=LAUNCH)
    a = ap.parse_args()
    if a.expect_camera != CAM or a.expect_launch != LAUNCH:
        die(2, 'ожидаемые суммы камеры и launch не те, что в этом генераторе (камера dabd5076, launch 5f0954d8)')
    kit = os.path.abspath(a.kit)
    img = os.path.abspath(a.image)
    out = os.path.join(kit, 'image_r2j_cam')
    r2j_inst = os.path.join(kit, 'image_r2j', 'INSTALL_SHA256_r2j.txt')
    r2j_rt = os.path.join(kit, 'image_r2j', 'RUNTIME_PY_r2j.tsv')
    sums_path = os.path.join(img, 'SHA256SUMS')
    if sha(sums_path) != a.expect_sums:
        die(2, 'sha256 SHA256SUMS образа %s = %s, а ждали %s' % (img, sha(sums_path), a.expect_sums))
    sums = {}
    for ln in open(sums_path, encoding='utf-8'):
        ln = ln.rstrip('\n')
        if len(ln) > 66 and ln[64:66] == '  ':
            p = ln[66:]
            if p.startswith('./'):
                p = p[2:]
            sums[p] = ln[:64]
    for dst, rel, s_r2j, s_cam, mode in TARGETS:
        p = os.path.join(img, rel)
        got = sha(p)
        if sums.get(rel) != got:
            die(2, 'файл образа %s не равен строке его SHA256SUMS (%s против %s)' % (rel, got, sums.get(rel)))
        if got != s_cam:
            die(2, 'файл образа %s = %s, а ждали %s' % (rel, got, s_cam))
    # r2jf = r2j во всём, что сверяют 09/15, кроме двух файлов
    inst_lines = [l.rstrip('\n') for l in open(r2j_inst, encoding='utf-8')]
    rt_lines = [l.rstrip('\n') for l in open(r2j_rt, encoding='utf-8')]
    new_inst, changed_inst = [], 0
    for l in inst_lines:
        if not l.strip() or l.startswith('#'):
            continue
        h, name = l.split()[0], l.split()[1]
        if name.endswith('.py'):
            p = os.path.join(img, 'install/bumblebee/lib/bumblebee', name)
            got = sha(p) if os.path.isfile(p) else 'missing'
            if name == 'camera_fix.py':
                if h != CAM_R2J:
                    die(2, 'в списке r2j camera_fix.py не 4a15d699')
                if got != CAM:
                    die(2, 'в install образа camera_fix.py не dabd5076')
                new_inst.append(CAM + '  ' + name)
                changed_inst += 1
                continue
            if got != h:
                die(2, 'python-узел %s в install образа (%s) не равен r2j (%s): образ отличается не только камерой' % (name, got, h))
        new_inst.append(l)
    new_rt, changed_rt = [], 0
    for l in rt_lines:
        if not l.strip() or l.startswith('#'):
            continue
        f = l.split('\t')
        h, kind, path = f[0], f[1], f[2]
        if kind == 'LAUNCH':
            p = os.path.join(img, 'install/bumblebee/share/bumblebee', path)
            got = sha(p) if os.path.isfile(p) else 'missing'
            if path == 'launch/bumblebee.launch.py':
                if h != LAUNCH_R2J:
                    die(2, 'в списке r2j bumblebee.launch.py не 62be01db')
                if got != LAUNCH:
                    die(2, 'в install/share образа bumblebee.launch.py не 5f0954d8')
                new_rt.append(LAUNCH + '\t' + kind + '\t' + path)
                changed_rt += 1
                continue
            if got != h:
                die(2, 'launch-файл %s в install/share образа (%s) не равен r2j (%s)' % (path, got, h))
        new_rt.append(l)
    if changed_inst != 1 or changed_rt != 1:
        die(2, 'в новых списках должно отличаться ровно по одной строке (INSTALL %d, RT %d)' % (changed_inst, changed_rt))
    # запись (без перезаписи)
    targets = ['INSTALL_SHA256_r2jcam.txt', 'RUNTIME_PY_r2jcam.tsv', 'VARIANT_FILES.tsv', 'image_manifest.final.tsv', 'R2JCAM_SOURCE.txt', 'payload']
    for t in targets:
        if os.path.exists(os.path.join(out, t)):
            die(3, 'уже есть %s, не перезаписываю' % os.path.join(out, t))
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    man_sha = sha(os.path.join(img, 'image_manifest_r2.tsv'))
    hdr_inst = ['# Список python-узлов install для сверок 09c и 15c варианта «r2j + камера полных строк» (создан gen_lists_r2jcam.py, %s).' % now,
                '# Это INSTALL_SHA256_r2j.txt (sha256 %s) с ОДНОЙ заменённой строкой: camera_fix.py 4a15d699 -> dabd5076 (образ r2jf %s).' % (sha(r2j_inst), img),
                '# Имена без .py - бинарные узлы: их суммы не сверяются (как в r2j), только «не старше изменённых исходников».']
    hdr_rt = ['# Launch-файлы и fcu_detect.py для сверок 09c и 15c варианта «r2j + камера полных строк» (создан gen_lists_r2jcam.py, %s).' % now,
              '# Это RUNTIME_PY_r2j.tsv (sha256 %s) с ОДНОЙ заменённой строкой: launch/bumblebee.launch.py 62be01db -> 5f0954d8 (full_rows: главная True, вторая False).' % sha(r2j_rt),
              '# Колонки: sha256 TAB вид TAB путь (LAUNCH: <install>/share/bumblebee/<путь>; FCU: путь от HOME, исправленный fcu_detect 5932a00a, как в r2j).']
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'INSTALL_SHA256_r2jcam.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(hdr_inst + new_inst) + '\n')
    with open(os.path.join(out, 'RUNTIME_PY_r2jcam.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(hdr_rt + new_rt) + '\n')
    with open(os.path.join(out, 'VARIANT_FILES.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Места на Pi, которые меняет вариант (путь от HOME=/home/lb) TAB sha256 r2j (до) TAB sha256 варианта (после). Создан gen_lists_r2jcam.py, %s.\n' % now)
        for dst, rel, s_r2j, s_cam, mode in TARGETS:
            f.write('%s\t%s\t%s\n' % (dst, s_r2j, s_cam))
    with open(os.path.join(out, 'image_manifest.final.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Вариант «r2j + камера полных строк» (r2jf): путь от DEST_ROOT=/home/lb TAB sha256 [TAB режим]. src - для будущих сборок, install оверлея r2j - то, что исполняется.\n')
        for dst, rel, s_r2j, s_cam, mode in TARGETS:
            f.write(dst + '\t' + s_cam + ('\t' + mode if mode else '') + '\n')
    for dst, rel, s_r2j, s_cam, mode in TARGETS:
        p = os.path.join(out, 'payload', dst)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copyfile(os.path.join(img, rel), p)
        if sha(p) != s_cam:
            die(2, 'копия %s не сошлась' % p)
    with open(os.path.join(out, 'R2JCAM_SOURCE.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Источник варианта «r2j + камера полных строк» (создан gen_lists_r2jcam.py, %s по часам ПК).\n' % now)
        f.write('образ: %s\n' % img)
        f.write('sha256 файла SHA256SUMS образа: %s (строк %d)\n' % (a.expect_sums, len(sums)))
        f.write('sha256 image_manifest_r2.tsv образа: %s\n' % man_sha)
        f.write('camera_fix.py (src и install образа): %s\n' % CAM)
        f.write('bumblebee.launch.py (src и install/share образа): %s\n' % LAUNCH)
        f.write('r2j: camera_fix.py %s, bumblebee.launch.py %s\n' % (CAM_R2J, LAUNCH_R2J))
        f.write('проверено: остальные python-узлы (%d) и launch-файлы (%d) install образа r2jf равны спискам r2j набора\n'
                % (sum(1 for l in new_inst if l.split()[1].endswith('.py')) - 1, sum(1 for l in new_rt if '\tLAUNCH\t' in l) - 1))
        f.write('INSTALL_SHA256_r2j.txt sha256 %s; RUNTIME_PY_r2j.tsv sha256 %s\n' % (sha(r2j_inst), sha(r2j_rt)))
        f.write('из образа взяты только два файла; его setup.sh и прочее install НЕ используются (проверка v14 R, П4: POSIX setup.sh r2jf указывает на install r2j)\n')
    print('OK: INSTALL строк %d, RT строк %d, мест на Pi %d' % (len(new_inst), len(new_rt), len(TARGETS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
