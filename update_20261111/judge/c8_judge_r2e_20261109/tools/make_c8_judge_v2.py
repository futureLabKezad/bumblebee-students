#!/usr/bin/env python3
"""make_c8_judge_v2.py - T28 (09.11.2026): judge copy for C8 on airframe 4061 / image r2e (owner: variant B).
Copies flight_verification_03/verify_flight.py and the legacy verifier it loads into /work/c8_judge_r2e_20261109 and
applies anchored edits. Allowed changes only: expected airframe (a fixed identity table, chosen by --identity),
profile name list (r2e), report folder (own), and (v2, owner 09.11 «да» to "approve set 4061 and that the judge expects
exactly it", variant A) the expectation of real_parameters_before_arm for c8_4061: own files pinned by sha whose only
difference from sim/ros_stack is the 5 values of airframe 4061: NAV_RCL_ACT 3, COM_RCL_EXCEPT 0, COM_DISARM_LAND 0.5,
COM_SPOOLUP_TIME 1.0, BAT1_SOURCE 1 (chat 1 09.11: variant A5, covered by the owner's «да» to "the judge expects the set").
Every threshold and pass/failed/unknown rule is unchanged.
The identity 'rel3_4030' reproduces the accepted judge exactly (proof: tools/compare_rel3.py), old expectation files.
Usage: python3 -I make_c8_judge_v2.py OUT_DIR   (refuses to overwrite)
"""
import hashlib
import os
import sys

# Variant A: (source file, anchored replacements) -> expect/<name> in OUT_DIR. Exactly five numbers change (A5).
EXPECT_SRC = {
    'flight_real_params.json': ('/work/sim/ros_stack/flight_real_params.json',
                                '3798b84ae80cd4a826fb555f7cfb835edd392eff734b6a5944695d5c7003466f',
                                [('    "COM_DISARM_LAND": {\n      "value": 2.0,\n',
                                  '    "COM_DISARM_LAND": {\n      "value": 0.5,\n'),
                                 ('    "COM_SPOOLUP_TIME": {\n      "value": 0.0,\n',
                                  '    "COM_SPOOLUP_TIME": {\n      "value": 1.0,\n'),
                                 ('    "BAT1_SOURCE": {\n      "value": -1,\n',
                                  '    "BAT1_SOURCE": {\n      "value": 1,\n')]),
    'rc_real_params.json': ('/work/sim/ros_stack/rc_real_params.json',
                            'e6a88f9a2b36d9dd2768f8e086d1da5a6fe98837af6348e2aad7faecc5ac70c4',
                            [('    "COM_RCL_EXCEPT": {\n      "value": 4.0,\n',
                              '    "COM_RCL_EXCEPT": {\n      "value": 0.0,\n'),
                             ('    "NAV_RCL_ACT": {\n      "value": 0.0,\n',
                              '    "NAV_RCL_ACT": {\n      "value": 3.0,\n')]),
}
EXPECT_NAME = {'flight_real_params.json': 'flight_real_params_4061.json', 'rc_real_params.json': 'rc_real_params_4061.json'}

SRC_JUDGE = '/work/parallel_work/20261015/integration/flight_verification_03/verify_flight.py'
SRC_JUDGE_SHA = 'd7f96939632aaff8377965324b36c3418a506d6af3a38b374d96b381818c1156'
SRC_LEGACY = '/work/analysis/exp_scripts/verify_package1b_gates.py'
SRC_LEGACY_SHA = '1f6e2b0bf4b4885f370591d303951eed2cfe10de40ab8a711527378a40ff3e88'

LEGACY_EDITS = [
    ('''"""Read local SITL artifacts and report pass/failed/unknown without commanding ROS.
''',
     '''"""Read local SITL artifacts and report pass/failed/unknown without commanding ROS.

C8 COPY (T28, 09.11.2026, owner variant B): copy of analysis/exp_scripts/verify_package1b_gates.py (sha 1f6e2b0b).
Only changes: the expected SYS_AUTOSTART of the 'candidate4030' check is the module value AUTOSTART, and (owner 09.11,
variant A) the expectation files of 'real_parameters_before_arm' are the module value REAL_PARAMS when set; both are set by
the C8 judge copy (verify_flight_c8.py) from its fixed identity table (it checks the sha of the files). With the defaults
(4030, None) this file behaves exactly as the original. The check id stays 'candidate4030' (historical name).
''', 1),
    ('''PX4_COMMIT = '94cb2012792b2ae89f0b147cfee53ee31ae550be'
''',
     '''PX4_COMMIT = '94cb2012792b2ae89f0b147cfee53ee31ae550be'
AUTOSTART = 4030   # C8 copy: set by verify_flight_c8.py from its identity table (4030 = the accepted judge)
REAL_PARAMS = None  # C8 copy: {file name: pinned path} for c8_4061; None = the original lookup (run copy, else sim/ros_stack)
''', 1),
    ('''    for name in ['flight_real_params.json', 'rc_real_params.json']:
        path = run / name
        if not path.exists():
            path = WORKSPACE / 'sim/ros_stack' / name
''',
     '''    for name in ['flight_real_params.json', 'rc_real_params.json']:
        if REAL_PARAMS is not None:
            # C8 copy (variant A): the identity's pinned expectation; a run copy cannot replace it
            path = Path(REAL_PARAMS[name])
        else:
            path = run / name
            if not path.exists():
                path = WORKSPACE / 'sim/ros_stack' / name
''', 1),
    ('''    identity = {'SYS_AUTOSTART': 4030, 'SIM_GZ_EN': 1, 'COM_OBL_RC_ACT': 4}
''',
     '''    identity = {'SYS_AUTOSTART': AUTOSTART, 'SIM_GZ_EN': 1, 'COM_OBL_RC_ACT': 4}
''', 1),
]

JUDGE_EDITS = [
    ('''"""Host-only, fail-closed review of one saved combined SITL scenario."""
''',
     '''"""Host-only, fail-closed review of one saved combined SITL scenario.

C8 COPY (T28, 09.11.2026, owner variant B) of flight_verification_03/verify_flight.py (sha d7f96939).
Changed only: expected airframe, profile names and (c8_4061, owner 09.11 variant A) the pinned expectation files of
real_parameters_before_arm come from the fixed IDENTITIES table (--identity, required); reports are written only into
this folder's reviews/; the legacy verifier is this folder's copy (legacy/).
'rel3_4030' = the accepted judge's values (bit-for-bit proof on rel3: tools/compare_rel3.py).
"""
''', 1),
    ('''ROOT = HERE.parents[3]
LEGACY = ROOT / 'analysis/exp_scripts/verify_package1b_gates.py'
LEGACY_SHA = '1f6e2b0bf4b4885f370591d303951eed2cfe10de40ab8a711527378a40ff3e88'
NAMES = set(''',
     '''ROOT = HERE.parent   # /work (the accepted judge: HERE.parents[3] of flight_verification_03 = /work)
LEGACY = HERE / 'legacy/verify_package1b_gates_c8.py'
LEGACY_SHA = '@LEGACY_SHA@'
NAMES_REL3 = set(''', 1),
    ('''MPC_Z_VEL_MAX_DN MPC_Z_VEL_MAX_UP MPC_Z_V_AUTO_DN MPC_Z_V_AUTO_UP'.split())
''',
     '''MPC_Z_VEL_MAX_DN MPC_Z_VEL_MAX_UP MPC_Z_V_AUTO_DN MPC_Z_V_AUTO_UP'.split())
# C8 identity table (fixed; no free values on the command line).
#  rel3_4030: the accepted judge (airframe 4030, 19 names = combined_13 profile 14 + closure 5).
#  c8_4061:   airframe 4061 (candidate set 09.11), image r2e: its flight_profile.py DEFAULT has 13 names
#             (no COM_SPOOLUP_TIME: the drone's own value), + the same closure 5 = 18 names.
#             real_parameters_before_arm expects expect/*_4061.json (owner 09.11 «да», variant A): the sim/ros_stack
#             files with only the 5 values of 4061 (NAV_RCL_ACT 3, COM_RCL_EXCEPT 0, COM_DISARM_LAND 0.5,
#             COM_SPOOLUP_TIME 1.0, BAT1_SOURCE 1; A5); pinned here by sha.
IDENTITIES = {
    'rel3_4030': dict(autostart=4030, names=frozenset(NAMES_REL3), real_params=None),
    'c8_4061': dict(autostart=4061, names=frozenset(NAMES_REL3 - {'COM_SPOOLUP_TIME'}), real_params={
        'flight_real_params.json': (HERE / 'expect/flight_real_params_4061.json', '@SHA_flight_real_params.json@'),
        'rc_real_params.json': (HERE / 'expect/rc_real_params_4061.json', '@SHA_rc_real_params.json@')}),
}
IDENTITY = None
NAMES = None


def use_identity(key):
    global IDENTITY, NAMES
    IDENTITY = key
    NAMES = set(IDENTITIES[key]['names'])
''', 1),
    ('''    spec.loader.exec_module(module)
    return module
''',
     '''    spec.loader.exec_module(module)
    module.AUTOSTART = IDENTITIES[IDENTITY]['autostart']   # C8 copy: identity values passed to the legacy copy
    real = IDENTITIES[IDENTITY]['real_params']
    if real is not None:
        for name, (path, sha) in real.items():
            if not path.is_file() or digest(path) != sha:
                raise ValueError('Pinned real-parameter expectation changed: ' + str(path))
        module.REAL_PARAMS = {name: str(path) for name, (path, sha) in real.items()}
    return module
''', 1),
    ('''expected_count=19, actual_count=len(baseline))''',
     '''expected_count=len(NAMES), actual_count=len(baseline))''', 1),
    ('''limits=['PARAM has no nonce and reads are not an atomic snapshot.', 'Only these 19 known dependencies are covered.'])''',
     '''limits=['PARAM has no nonce and reads are not an atomic snapshot.', 'Only these %d known dependencies are covered.' % len(NAMES)])''', 1),
    ('''    parser.add_argument('--criteria', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE) or out.exists():
        raise SystemExit('Write a new report only inside flight_verification_03')
''',
     '''    parser.add_argument('--criteria', type=Path)
    parser.add_argument('--identity', required=True, choices=sorted(IDENTITIES))
    args = parser.parse_args()
    use_identity(args.identity)
    out = args.out.resolve()
    if not out.is_relative_to(HERE / 'reviews') or out.exists():
        raise SystemExit('Write a new report only inside c8_judge_r2e_20261109/reviews')
''', 1),
    ('''    report['evidence_sha256'] = {''',
     '''    report['judge_identity'] = dict(identity=IDENTITY, autostart=IDENTITIES[IDENTITY]['autostart'],
                                    names=sorted(NAMES), legacy=str(LEGACY),
                                    real_params=({n: [str(p), s] for n, (p, s) in IDENTITIES[IDENTITY]['real_params'].items()}
                                                 if IDENTITIES[IDENTITY]['real_params'] else None))
    report['evidence_sha256'] = {''', 1),
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def edit(text, edits, what):
    for old, new, n in edits:
        c = text.count(old)
        if c != n:
            sys.exit('STOP: %s anchor %r: %d matches' % (what, old[:70], c))
        text = text.replace(old, new)
    return text


def main():
    out = sys.argv[1]
    lj = os.path.join(out, 'legacy', 'verify_package1b_gates_c8.py')
    vj = os.path.join(out, 'verify_flight_c8.py')
    for p in (lj, vj):
        if os.path.exists(p):
            sys.exit('STOP: refusing to overwrite ' + p)
    srcj, srcl = open(SRC_JUDGE, 'rb').read(), open(SRC_LEGACY, 'rb').read()
    if sha(srcj) != SRC_JUDGE_SHA or sha(srcl) != SRC_LEGACY_SHA:
        sys.exit('STOP: source judge changed')
    expect = {}
    for name, (src, ssha, edits) in EXPECT_SRC.items():
        b = open(src, 'rb').read()
        if sha(b) != ssha:
            sys.exit('STOP: expectation source changed: ' + src)
        t = b.decode('utf-8')
        for old, new in edits:
            if t.count(old) != 1:
                sys.exit('STOP: expectation anchor %r in %s' % (old[:40], src))
            t = t.replace(old, new)
        expect[name] = t.encode('utf-8')
    legacy = edit(srcl.decode('utf-8'), LEGACY_EDITS, 'legacy').encode('utf-8')
    judge = edit(srcj.decode('utf-8'), JUDGE_EDITS, 'judge').replace('@LEGACY_SHA@', sha(legacy))
    for name, b in expect.items():
        judge = judge.replace('@SHA_%s@' % name, sha(b))
    assert '@SHA_' not in judge and '@LEGACY' not in judge
    judge = judge.encode('utf-8')
    os.makedirs(os.path.dirname(lj), exist_ok=True)
    os.makedirs(os.path.join(out, 'reviews'), exist_ok=True)
    os.makedirs(os.path.join(out, 'expect'), exist_ok=True)
    for name, b in expect.items():
        with open(os.path.join(out, 'expect', EXPECT_NAME[name]), 'xb') as f:
            f.write(b)
        print('expect', EXPECT_NAME[name], sha(b))
    with open(lj, 'xb') as f:
        f.write(legacy)
    with open(vj, 'xb') as f:
        f.write(judge)
    print('legacy', sha(legacy))
    print('judge ', sha(judge))


if __name__ == '__main__':
    main()
