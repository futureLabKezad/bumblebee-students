#!/usr/bin/env python3
"""param_parity.py - goal step 4 (Claude, 06.11.2026). SIMULATOR ONLY, reads files only.

Compares the parameters a running SITL reported (params_sitl.json from sim_driver.py) with the drone's QGC file,
component 1 only. Every drone parameter ends in exactly one class:
  equal            - SITL value equals the drone value (int exact, float within tolerance);
  absent:<id>      - not in the SITL build, reason in sim_only.json absent_groups;
  sim_only:<id>    - listed sim-only exception, and the SITL value is the expected sim value;
  control:<param>  - the run's control variant changes it on purpose (sim_only.json variants);
  UNEXPLAINED      - anything else (also: a sim-only parameter whose SITL value is not the expected one,
                     or a drone parameter the SITL did not report at all).
Writes parity.json and parity.txt into RUN_DIR (refuses to overwrite). Exit 0 if UNEXPLAINED == 0, else 3.
Usage: python3 -I param_parity.py RUN_DIR DRONE.params SIM_ONLY.json AIRFRAME_ID
"""
import fnmatch
import json
import os
import sys


def read_drone(path):
    out = {}
    for line in open(path, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        _, comp, name, value, ptype = line.rstrip('\n').split('\t')
        if int(comp) == 1:
            out[name] = (float(value), int(ptype))
    return out


def match(name, patterns):
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def eq(a, b, ptype, tol):
    if ptype != 9:
        return int(round(a)) == int(round(b))
    return abs(a - b) <= max(tol['float_abs'], tol['float_rel'] * max(abs(a), abs(b)))


def main():
    run_dir, drone_path, policy_path, af = sys.argv[1:5]
    sfx = sys.argv[5] if len(sys.argv) > 5 else ''      # re-evaluation of an old run: parity<sfx>.json, never overwrite
    drone = read_drone(drone_path)
    policy = json.load(open(policy_path, encoding='utf-8'))
    sitl = json.load(open(os.path.join(run_dir, 'params_sitl.json')))['params']
    names_build = set(open(os.path.join(os.path.dirname(policy_path), 'tools', 'sitl_param_names.txt')).read().split())
    tol = policy['tolerance']
    variant = policy['variants'][af]['changes']
    rows, counts, unexplained = [], {}, []
    for name in sorted(drone):
        dv, ptype = drone[name]
        sv = sitl.get(name, {}).get('value')
        cls, note = None, ''
        if name not in names_build:
            grp = next((g for g in policy['absent_groups'] if match(name, g['patterns'])), None)
            cls = 'absent:' + grp['id'] if grp else 'UNEXPLAINED'
            note = 'not in SITL build' + ('' if grp else ', no group')
            if sv is not None:
                cls, note = 'UNEXPLAINED', 'listed absent but SITL reported it'
        elif name in variant:
            cls = 'control:' + name if (sv is not None and eq(variant[name], sv, ptype, tol)) else 'UNEXPLAINED'
            note = f'control value {variant[name]}'
        else:
            so = next((s for s in policy['sim_only'] if match(name, s['patterns'])), None)
            if sv is None:
                cls, note = 'UNEXPLAINED', 'drone parameter not reported by SITL'
            elif so is not None:
                exp = so['sim_expected']
                ok = (exp == 'any' or (exp == 'airframe' and int(sv) == int(af))
                      or (isinstance(exp, list) and any(eq(e, sv, ptype, tol) for e in exp))
                      or (isinstance(exp, (int, float)) and eq(exp, sv, ptype, tol)))
                same = eq(dv, sv, ptype, tol)
                cls = ('sim_only:' + so['id']) if ok else 'UNEXPLAINED'
                note = 'same value as drone' if same else 'differs on purpose'
            elif eq(dv, sv, ptype, tol):
                cls = 'equal'
            else:
                cls = 'UNEXPLAINED'
        rows.append({'name': name, 'drone': dv, 'sitl': sv, 'type': ptype, 'class': cls, 'note': note})
        key = cls.split(':')[0]
        counts[key] = counts.get(key, 0) + 1
        if cls == 'UNEXPLAINED':
            unexplained.append(rows[-1])
    differs = [r for r in rows if r['class'].startswith('sim_only') and r['note'] == 'differs on purpose']
    res = {'airframe': af, 'drone_params': len(drone), 'counts': counts, 'unexplained': unexplained,
           'sim_only_differs': len(differs), 'sim_only_differs_by_id': {}}
    for r in differs:
        k = r['class'].split(':')[1]
        res['sim_only_differs_by_id'][k] = res['sim_only_differs_by_id'].get(k, 0) + 1
    with open(os.path.join(run_dir, f'parity{sfx}.json'), 'x', encoding='utf-8') as f:
        json.dump({'summary': res, 'rows': rows}, f, indent=1, ensure_ascii=False)
    with open(os.path.join(run_dir, f'parity{sfx}.txt'), 'x', encoding='utf-8') as f:
        f.write(f"airframe {af}: drone params {len(drone)}; {json.dumps(counts)}; "
                f"sim-only that really differ {len(differs)} {json.dumps(res['sim_only_differs_by_id'])}\n")
        f.write(f"UNEXPLAINED {len(unexplained)}\n")
        for r in unexplained:
            f.write(f"  {r['name']}: drone {r['drone']} sitl {r['sitl']} ({r['note']})\n")
    print(open(os.path.join(run_dir, f'parity{sfx}.txt'), encoding='utf-8').read(), end='')
    sys.exit(0 if not unexplained else 3)


if __name__ == '__main__':
    main()
