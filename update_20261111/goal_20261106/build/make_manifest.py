#!/usr/bin/env python3
"""make_manifest.py - list of files of the FIXED IMAGE with SHA256 (Claude, 05.11.2026, goal step 1).

READ ONLY for every source: reads git objects and files, writes only into OUT_DIR (refuses to overwrite).
Fixed image = repo commit a45a264 (what runs on bumblebee-20ec, folder drone/) + overlays:
  1) flight-code fixes  : /work/ws_package1b_port_03/src/bumblebee, tag port-rc3 (64438f4), base 394a0f1 = a45a264 package
  2) port fix           : /work/fcu_detect_fix_01/scripts/fcu_detect.py
  3) camera fix         : camera_fullrow_01/candidate/camera_fix.py (not yet in the image: owner's condition, Pi load check)
  4) MAVROS             : /work/ws_mavros214_bp02_rel/src/mavros-source, tag backport-02 (source identity only)
Usage: python3 -I make_manifest.py OUT_DIR
"""
import hashlib
import os
import subprocess
import sys

REPO = os.path.expanduser('~/bumblebee-students')
A45 = 'a45a2643ddf876d82395f9599724d83c36ef6ffc'
PKG = 'drone/ros2_ws/src/bumblebee'
RC3 = '/work/ws_package1b_port_03/src/bumblebee'
RC3_BASE = '394a0f1'
RC3_TAG = 'port-rc3'
FCU_NEW = '/work/fcu_detect_fix_01/scripts/fcu_detect.py'
FCU_OLD_SHA = 'ee174fd1a610eacc9bdcf1a995379f068200abc49045774dbeec088982ed9f00'
FCU_NEW_SHA = '5932a00afc79e421a7bb26a7e84564cf106afdcbc009642c7e872ab86b839bf5'
CAM_NEW = '/work/parallel_work/20261015/integration/camera_fullrow_01/candidate/camera_fix.py'
CAM_OLD_SHA = '4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310'
CAM_NEW_SHA = 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'
MAV = '/work/ws_mavros214_bp02_rel/src/mavros-source'
MAV_BASE = 'b964c11'
MAV_TAG = 'backport-02'


def git(repo, *args, raw=False):
    out = subprocess.run(['git', '-C', repo] + list(args), check=True, capture_output=True).stdout
    return out if raw else out.decode().strip()


def sha_blob(repo, rev_path):
    return hashlib.sha256(git(repo, 'cat-file', 'blob', rev_path, raw=True)).hexdigest()


def sha_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def die(msg):
    print('STOP: ' + msg)
    sys.exit(2)


def main():
    out_dir = sys.argv[1]
    outs = [os.path.join(out_dir, n) for n in ('image_manifest.tsv', 'mavros_bp02_sources.tsv', 'manifest_check.txt')]
    for p in outs:
        if os.path.exists(p):
            die('refuse to overwrite ' + p)
    log = []

    # 0. identity checks
    rc3_tip = git(RC3, 'rev-parse', RC3_TAG + '^{commit}')
    rc3_base_full = git(RC3, 'rev-parse', RC3_BASE + '^{commit}')
    t_base = git(RC3, 'rev-parse', RC3_BASE + '^{tree}')
    t_a45 = git(REPO, 'rev-parse', A45 + ':' + PKG)
    if t_base != t_a45:
        die('port-rc3 base tree %s != a45a264 package tree %s' % (t_base, t_a45))
    if git(RC3, 'status', '--porcelain'):
        die('port-rc3 working tree is not clean')
    if git(RC3, 'rev-parse', 'HEAD') != rc3_tip:
        die('port-rc3 HEAD is not the tag')
    log.append('a45a264 commit: ' + A45)
    log.append('a45a264 package tree = port-rc3 base %s tree: %s (equal)' % (rc3_base_full, t_a45))
    log.append('port-rc3 tag commit: %s, working tree clean, HEAD = tag' % rc3_tip)

    # 1. base: a45a264 drone/ (what is on the drone)
    rows = {}
    for line in git(REPO, 'ls-tree', '-r', A45, '--', 'drone').splitlines():
        meta, path = line.split('\t', 1)
        mode, typ, obj = meta.split()
        if typ != 'blob':
            die('unexpected %s %s' % (typ, path))
        s = hashlib.sha256(git(REPO, 'cat-file', 'blob', obj, raw=True)).hexdigest()
        rows[path] = [s, s, 'a45a264', 'same']
    log.append('a45a264 drone/ files: %d' % len(rows))

    # 2. overlay port-rc3
    n = {'M': 0, 'A': 0, 'D': 0}
    for line in git(RC3, 'diff', '--name-status', rc3_base_full, rc3_tip).splitlines():
        st, p = line.split('\t', 1)
        if st not in n:
            die('unexpected status %s %s' % (st, p))
        n[st] += 1
        path = PKG + '/' + p
        if st == 'D':
            rows[path][1:] = ['-', 'port-rc3', 'removed']
            continue
        s = sha_blob(RC3, rc3_tip + ':' + p)
        if st == 'A':
            if path in rows:
                die('added path exists in a45 ' + path)
            rows[path] = ['-', s, 'port-rc3', 'new']
        else:
            rows[path][1:] = [s, 'port-rc3', 'changed']
    log.append('port-rc3 overlay: modified %(M)d, added %(A)d, removed %(D)d' % n)

    # 3. overlay fcu_detect fix
    fp = PKG + '/scripts/fcu_detect.py'
    if rows[fp][1] != FCU_OLD_SHA or sha_file(FCU_NEW) != FCU_NEW_SHA:
        die('fcu_detect sha mismatch')
    rows[fp][1:] = [FCU_NEW_SHA, 'fcu_detect_fix_01', 'changed (on the drone since 05.11 14:10)']
    log.append('fcu_detect.py: %s -> %s' % (FCU_OLD_SHA[:8], FCU_NEW_SHA[:8]))

    # 4. overlay camera fix (pending owner's condition)
    cp = PKG + '/src/python/camera_fix.py'
    if rows[cp][1] != CAM_OLD_SHA or sha_file(CAM_NEW) != CAM_NEW_SHA:
        die('camera_fix sha mismatch')
    rows[cp][1:] = [CAM_NEW_SHA, 'camera_fullrow_01', 'changed (PENDING: Pi load check at the bench)']
    log.append('camera_fix.py: %s -> %s (pending)' % (CAM_OLD_SHA[:8], CAM_NEW_SHA[:8]))

    with open(outs[0], 'w') as f:
        f.write('# path\tsha256_on_drone_a45a264\tsha256_fixed_image\tsource\tchange\n')
        for p in sorted(rows):
            f.write('\t'.join([p] + rows[p]) + '\n')
    cnt = {}
    for r in rows.values():
        cnt[r[3].split(' ')[0]] = cnt.get(r[3].split(' ')[0], 0) + 1
    log.append('fixed image files: %d; by change: %s' % (sum(1 for r in rows.values() if r[1] != '-'), cnt))

    # 5. MAVROS bp02 source identity
    mav_tip = git(MAV, 'rev-parse', MAV_TAG + '^{commit}')
    mav_base = git(MAV, 'rev-parse', MAV_BASE + '^{commit}')
    if git(MAV, 'rev-parse', 'HEAD') != mav_tip:
        die('MAVROS HEAD is not ' + MAV_TAG)
    with open(outs[1], 'w') as f:
        f.write('# MAVROS fixed (bp02): base %s (MAVROS 2.14.0 source), tag %s = %s\n' % (mav_base, MAV_TAG, mav_tip))
        f.write('# commits:\n')
        for line in git(MAV, 'log', '--reverse', '--format=%H %s', mav_base + '..' + mav_tip).splitlines():
            f.write('#   ' + line + '\n')
        f.write('# path\tsha256_base_2.14.0\tsha256_bp02\n')
        for p in git(MAV, 'diff', '--name-only', mav_base, mav_tip).splitlines():
            f.write('%s\t%s\t%s\n' % (p, sha_blob(MAV, mav_base + ':' + p), sha_blob(MAV, mav_tip + ':' + p)))
    log.append('MAVROS bp02: base %s, tip %s' % (mav_base, mav_tip))

    with open(outs[2], 'w') as f:
        f.write('\n'.join(log) + '\nRESULT: OK\n')
    print('\n'.join(log))
    print('RESULT: OK')


if __name__ == '__main__':
    main()
