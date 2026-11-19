#!/usr/bin/env python3
"""make_payload_r2j.py (Claude, 13.11.2026, набор r7; по образцу /work/saved_r2h_20261111/tools/make_saved_r2h.py, переделан под r2j).

ТОЛЬКО ЧИТАЕТ источники; пишет только в папку image_r2j набора r7 (новые файлы, ничего не перезаписывает); к дрону и в сеть не обращается.
Что делает:
  1) проверяет источники: образ /work/fixed_image_r2j_20261111 (sha256 SHA256SUMS = 14fbcf74..., все строки SHA256SUMS и MANIFEST_SHA256.txt,
     image_manifest_r2.tsv = 0c02e391...), скрипт висения hover r6 (/work/c6_hover_script_r6_20261110, его SHA256SUMS.txt и a11b195c...),
     5 исходников MAVROS bp02 (/work/ws_mavros214_bp02/src/mavros-source, sha256_bp02 из mavros_bp02_sources.tsv набора);
  2) payload/ и image_manifest.final.tsv (пути от DEST_ROOT=/home/lb), как для r2h:
       - строки image_manifest_r2.tsv под drone/ros2_ws/src/, которые r2j меняет (changed) или добавляет (new) против образа на дроне a45a264,
         байты из src/ образа (sha каждого = колонке sha256_fixed_image);
       - НЕ scripts/fcu_detect.py (правило набора, решение чата 1 10.11 22:00: на дроне остаётся исправленный 5932a00a...);
       - НЕ строки, равные на дроне и в r2j, и НЕ строки вне drone/ros2_ws/src/ (их рабочие места на дроне не DEST_ROOT/путь);
       - плюс camera_fix.py по умолчанию 4a15d699 явно (в r2j он равен файлу на дроне; состав образа набора требует камеру по умолчанию);
       - плюс hover r6 -> ros2_ws/src/bumblebee/examples/hover_marker0.py (берёт drone.py из этого каталога);
       - плюс 5 исходников MAVROS bp02 (тег backport-02, d63a236) справочной копией -> image_r2j_ref/mavros_bp02_d63a236/...
         (вне ~/bench_ws: шаги сборки 11 и 13 требуют, чтобы их каталогов не было).
  3) сверка со списками набора: required_shas.txt, CPP_SOURCES_r2j.tsv, RUNTIME_PY_r2j.tsv, INSTALL_SHA256_r2j.txt (python-узлы), mavros_bp02_sources.tsv.
Запуск (WSL, низкий приоритет): nice -n 19 ionice -c3 python3 -I make_payload_r2j.py <папка image_r2j набора r7>
Код выхода: 0 готово (последняя строка BUILD_OK); 2 СТОП (причина в строке STOP: ..., если до записи - ничего не записано).
"""
import hashlib
import os
import shutil
import sys

IMG = '/work/fixed_image_r2j_20261111'
IMG_SUMS_SHA = '14fbcf74d847605c927181245f23e5c598c551a24249991070770ea49bf26094'
IMG_MAN_SHA = '0c02e391c6763ec24aba026512a4caf89e348f3a3507a637423c0d665a345c33'
HOVER_DIR = '/work/c6_hover_script_r6_20261110'
HOVER_SHA = 'a11b195ce1507607967ff6a7402726d9eef7b4f12850a9e864f5ae27d1f513f7'
HOVER_DEST = 'ros2_ws/src/bumblebee/examples/hover_marker0.py'
MAV_SRC = '/work/ws_mavros214_bp02/src/mavros-source'
MAV_DEST = 'image_r2j_ref/mavros_bp02_d63a236/'
CAM_DEFAULT = '4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310'
CAM_VARIANT = 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'
CAM_DEST = 'ros2_ws/src/bumblebee/src/python/camera_fix.py'
FLIGHT_SHA = 'b69cc5e72509bbe2f141e48844b999e3a046ac6a78d28484239536b426c807b3'
FLIGHT_DEST = 'ros2_ws/src/bumblebee/examples/flight/flight.py'
FCU_FIXED = '5932a00afc79e421a7bb26a7e84564cf106afdcbc009642c7e872ab86b839bf5'
P = 'drone/'
WS = 'drone/ros2_ws/src/'


def die(msg):
    print('STOP: ' + msg)
    sys.exit(2)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def check_sums(folder, sums_name):
    """Как «sha256sum -c»: каждая строка «sha  путь» (путь от folder). Возвращает число проверенных строк."""
    n = 0
    with open(os.path.join(folder, sums_name), encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line.strip():
                continue
            want, name = line.split(None, 1)
            name = name.strip().lstrip('*')
            if name.startswith('./'):
                name = name[2:]
            got = sha(os.path.join(folder, name))
            if got != want:
                die('%s/%s: %s не сходится (%s вместо %s)' % (folder, sums_name, name, got, want))
            n += 1
    return n


def read_tsv(path):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if not line.strip() or line.startswith('#'):
                continue
            rows.append(line.split('\t'))
    return rows


def safe_dest(d):
    if d.startswith('/') or d.endswith('/') or '\\' in d or ' ' in d or '\t' in d:
        return False
    segs = d.split('/')
    return all(s not in ('', '.', '..') for s in segs)


def main():
    if len(sys.argv) != 2:
        die('usage: make_payload_r2j.py <папка image_r2j набора r7>')
    kit = os.path.abspath(sys.argv[1])
    pay = os.path.join(kit, 'payload')
    man_out = os.path.join(kit, 'image_manifest.final.tsv')
    extra_out = [os.path.join(kit, n) for n in ('PAYLOAD_SOURCES_r2j.tsv', 'NOT_IN_PAYLOAD_r2j.txt', 'BUILD_LOG_payload_r2j.txt')]
    for p in [man_out] + extra_out:
        if os.path.exists(p):
            die('уже есть ' + p + ', ничего не перезаписываю')
    if not os.path.isdir(pay):
        die('нет папки ' + pay)
    have = sorted(os.path.relpath(os.path.join(dp, n), pay) for dp, _dn, fn in os.walk(pay) for n in fn)
    if have != ['README.md']:
        die('в payload уже что-то есть кроме README.md: %s' % have[:5])
    log = []

    # 1. источники
    if sha(IMG + '/SHA256SUMS') != IMG_SUMS_SHA:
        die('SHA256SUMS образа не 14fbcf74...')
    n1 = check_sums(IMG, 'SHA256SUMS')
    n2 = check_sums(IMG, 'MANIFEST_SHA256.txt')
    if sha(IMG + '/image_manifest_r2.tsv') != IMG_MAN_SHA:
        die('image_manifest_r2.tsv образа не 0c02e391...')
    n3 = check_sums(HOVER_DIR, 'SHA256SUMS.txt')
    if sha(HOVER_DIR + '/hover_marker0.py') != HOVER_SHA:
        die('hover r6 не a11b195c...')
    log.append('источники OK: образ r2j SHA256SUMS 14fbcf74 (строк %d сходятся), MANIFEST_SHA256.txt (строк %d сходятся), '
               'image_manifest_r2.tsv 0c02e391; hover r6 a11b195c (его SHA256SUMS.txt, строк %d сходятся)' % (n1, n2, n3))

    # 2. выбор файлов
    rows = read_tsv(IMG + '/image_manifest_r2.tsv')
    sel, why = [], {}
    n_same, outside, fcu = 0, [], []
    for f in rows:
        if len(f) != 5:
            die('строка манифеста образа не из 5 колонок: %r' % (f,))
        path, on_drone, fixed = f[0], f[1], f[2]
        if not path.startswith(P):
            die('строка без drone/: ' + path)
        if not path.startswith(WS):
            outside.append(path)
            continue
        if os.path.basename(path).lower() == 'fcu_detect.py':
            if fixed != FCU_FIXED:
                die('строка fcu_detect не исправленный 5932a00a: ' + fixed)
            fcu.append(path)
            continue
        dest = path[len(P):]
        if on_drone != '-' and on_drone == fixed:
            if dest == CAM_DEST and fixed == CAM_DEFAULT:
                pass   # камера по умолчанию: берём явно (ниже)
            else:
                n_same += 1
                continue
        if fixed == '-' or len(fixed) != 64:
            die('строка без sha образа (удалённый файл?): ' + path)
        src = IMG + '/src/' + path[len(WS):]
        if not os.path.isfile(src):
            die('нет файла в src образа для ' + path)
        s = sha(src)
        if s != fixed:
            die('sha %s (%s) не равен колонке образа %s' % (src, s, fixed))
        if dest == CAM_DEST:
            if not (s == CAM_DEFAULT and on_drone == CAM_DEFAULT):
                die('camera_fix в r2j не равен камере по умолчанию 4a15d699 или на дроне другая')
            kind = 'camera default 4a15d699 (равен файлу на дроне a45a264; берётся явно, как в r2h)'
        else:
            kind = 'new' if on_drone == '-' else 'changed'
        sel.append((dest, s, src))
        why[dest] = kind
    if any(r[0] == P + HOVER_DEST for r in rows) or any(d == HOVER_DEST for d, _, _ in sel):
        die('путь hover r6 уже есть в манифесте образа')
    sel.append((HOVER_DEST, HOVER_SHA, HOVER_DIR + '/hover_marker0.py'))
    why[HOVER_DEST] = 'hover r6 (скрипт C6; /work/c6_hover_script_r6_20261110)'
    mav = read_tsv(os.path.join(kit, 'mavros_bp02_sources.tsv'))
    if len(mav) != 5:
        die('в mavros_bp02_sources.tsv должно быть 5 строк')
    for mrow in mav:
        if len(mrow) != 3:
            die('строка mavros_bp02_sources.tsv не из 3 колонок: %r' % (mrow,))
        mpath, _base, bp02 = mrow
        src = MAV_SRC + '/' + mpath
        if sha(src) != bp02:
            die('исходник MAVROS %s не sha256_bp02' % src)
        d = MAV_DEST + mpath
        sel.append((d, bp02, src))
        why[d] = 'MAVROS bp02 source, справочная копия (тег backport-02 d63a236)'

    # 3. проверки по правилам и спискам набора
    dests = [d for d, _, _ in sel]
    if len(dests) != len(set(dests)):
        die('один путь дважды')
    for d in dests:
        if not safe_dest(d):
            die('небезопасный путь ' + d)
        if os.path.basename(d).lower() == 'fcu_detect.py':
            die('fcu_detect.py в payload')
    by = {d: s for d, s, _ in sel}
    if by.get(FLIGHT_DEST) != FLIGHT_SHA:
        die('нет flight.py b69cc5e7')
    if by.get(HOVER_DEST) != HOVER_SHA:
        die('нет hover r6')
    if CAM_VARIANT in by.values():
        die('вариант камеры dabd5076 в payload')
    cams = [d for d in dests if d.endswith('camera_fix.py')]
    if [by[c] for c in cams] != [CAM_DEFAULT]:
        die('camera_fix должен быть ровно одной строкой с 4a15d699: %s' % cams)
    req = {}
    for line in open(os.path.join(kit, 'required_shas.txt'), encoding='utf-8-sig'):
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            req[k] = v
    if (req.get('HOVER_R6_SHA256'), req.get('CAMERA_DEFAULT_SHA256'), req.get('CAMERA_VARIANT_SHA256'),
            req.get('FLIGHT_PY_SHA256')) != (HOVER_SHA, CAM_DEFAULT, CAM_VARIANT, FLIGHT_SHA):
        die('required_shas.txt отличается от констант сборщика')
    img_rows = {r[0][len(P):]: r for r in rows}
    n_cpp_in, n_cpp_same = 0, 0
    for row in read_tsv(os.path.join(kit, 'CPP_SOURCES_r2j.tsv')):
        s, path, flag = row
        if by.get(path) == s:
            n_cpp_in += 1
        elif flag == '-' and path in img_rows and img_rows[path][1] == img_rows[path][2] == s:
            n_cpp_same += 1
        else:
            die('строка CPP_SOURCES_r2j.tsv не покрыта: %s %s %s' % (s[:8], path, flag))
    n_rt_in, n_rt_same = 0, 0
    for row in read_tsv(os.path.join(kit, 'RUNTIME_PY_r2j.tsv')):
        s, kind, path = row
        if kind == 'FCU':
            if path in by:
                die('fcu_detect в payload')
            continue
        full = 'ros2_ws/src/bumblebee/' + path
        if by.get(full) == s:
            n_rt_in += 1
        elif full in img_rows and img_rows[full][1] == img_rows[full][2] == s:
            n_rt_same += 1
        else:
            die('строка RUNTIME_PY_r2j.tsv не покрыта: %s %s' % (s[:8], path))
    n_py_in, n_py_same = 0, 0
    for line in open(os.path.join(kit, 'INSTALL_SHA256_r2j.txt'), encoding='utf-8-sig'):
        if not line.strip():
            continue
        s, name = line.split()
        if not name.endswith('.py'):
            continue   # бинарные узлы собираются из C++ (их исходники - в CPP_SOURCES_r2j.tsv)
        cand = [p for p, r in img_rows.items() if p.startswith('ros2_ws/src/') and p.endswith('/' + name) and r[2] == s]
        if not cand:
            die('python-узел %s (%s) не найден в манифесте образа' % (name, s[:8]))
        if any(by.get(c) == s for c in cand):
            n_py_in += 1
        elif any(img_rows[c][1] == s for c in cand):
            n_py_same += 1
        else:
            die('python-узел %s не покрыт ни payload, ни файлом на дроне' % name)
    log.append('списки набора: CPP_SOURCES %d в payload + %d равны на дроне; RUNTIME launch %d в payload + %d равны на дроне; FCU не в payload; '
               'python-узлы INSTALL_SHA256 %d в payload + %d равны на дроне; required_shas.txt = константы сборщика'
               % (n_cpp_in, n_cpp_same, n_rt_in, n_rt_same, n_py_in, n_py_same))

    # 4. запись payload и манифеста
    for d, s, src in sel:
        dst = os.path.join(pay, d)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            die('уже есть ' + dst)
        shutil.copyfile(src, dst)
        if sha(dst) != s:
            die('копия отличается: ' + d)
    counts = {}
    for d in dests:
        k = why[d].split(' ')[0]
        counts[k] = counts.get(k, 0) + 1
    n_img = counts.get('new', 0) + counts.get('changed', 0)
    hdr = [
        '# image_manifest.final.tsv: образ r2j для bench_kit_20261113_r7/image_r2j (Claude, 13.11.2026, сборщик proverka_r7/make_payload_r2j.py; образец - r2h, /work/saved_r2h_20261111).',
        '# Пути относительно DEST_ROOT=/home/lb (image_target.conf). Колонки: путь<TAB>sha256. Режим не задан: установщик берёт режим файла на дроне,',
        '# у нового файла 755 при #! в первой строке, иначе 644.',
        '# Состав: %d файлов, которые r2j меняет (%d) или добавляет (%d) против образа на дроне a45a264 (из /work/fixed_image_r2j_20261111, SHA256SUMS 14fbcf74,'
        % (n_img, counts.get('changed', 0), counts.get('new', 0)),
        '#   image_manifest_r2.tsv 0c02e391; байты из src образа) + camera_fix.py по умолчанию 4a15d699 + скрипт висения hover r6 a11b195c',
        '#   + 5 исходников MAVROS bp02 (справочная копия в image_r2j_ref/, на сборку не влияет).',
        '# Не входят: scripts/fcu_detect.py (на дроне остаётся исправленный 5932a00a, правило набора); %d файлов, равных на дроне и в r2j;' % n_same,
        '#   %d файлов вне drone/ros2_ws/src/ (их рабочие места на дроне не DEST_ROOT/путь). Флаг S2/S3 и BACKUP_ROOT здесь не задаются.' % len(outside),
    ]
    body = ['%s\t%s' % (d, by[d]) for d in sorted(dests)]
    with open(man_out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(hdr + body) + '\n')
    with open(extra_out[0], 'w', encoding='utf-8', newline='\n') as f:
        f.write('# путь_от_/home/lb\tsha256\tпочему\tисточник\n')
        for d, s, src in sorted(sel):
            f.write('%s\t%s\t%s\t%s\n' % (d, s, why[d], src))
    with open(extra_out[1], 'w', encoding='utf-8', newline='\n') as f:
        f.write('# строки image_manifest_r2.tsv (0c02e391) не в payload и почему\n')
        for p_ in fcu:
            f.write('%s\tfcu_detect: на дроне остаётся исправленный 5932a00a (правило набора, чат 1 10.11 22:00)\n' % p_)
        for p_ in outside:
            f.write('%s\tвне drone/ros2_ws/src/: рабочее место на дроне не DEST_ROOT/путь\n' % p_)
        f.write('# плюс %d строк под drone/ros2_ws/src/, где sha на дроне (a45a264) == sha в r2j\n' % n_same)
    log.append('payload: %d файлов %s; не в payload: fcu %d, равных %d, вне ros2_ws/src %d; строк в манифесте образа %d'
               % (len(dests), counts, len(fcu), n_same, len(outside), len(rows)))
    # учёт строк: каждая строка манифеста образа - ровно в одной группе (camera - строка образа «same», взятая явно)
    if len(rows) != n_img + counts.get('camera', 0) + len(fcu) + n_same + len(outside):
        die('учёт строк не сходится')
    if len(dests) != n_img + counts.get('camera', 0) + 1 + 5:
        die('учёт payload не сходится')
    man_sha = sha(man_out)
    log.append('image_manifest.final.tsv sha256 %s (строк файлов: %d)' % (man_sha, len(body)))
    with open(extra_out[2], 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(log) + '\n')
    print('\n'.join(log))
    print('BUILD_OK')


if __name__ == '__main__':
    main()
