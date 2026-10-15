#!/usr/bin/env python3
"""Record reviewed host inputs before a run; never reads a run as authority."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from verify_flight import ROOT, HERE, LEGACY, LEGACY_SHA, digest


def collect(manifest, tools):
    data = json.loads(manifest.read_text())
    files = data['files']
    for name, sha in files.items():
        path = (manifest.parent/name).resolve()
        if not path.is_relative_to(manifest.parent.resolve()) or digest(path) != sha:
            raise ValueError('Combined manifest does not match source: '+name)
    if digest(LEGACY) != LEGACY_SHA:
        raise ValueError('Pinned existing verifier changed')
    sources = [p for p in tools.iterdir() if p.is_file() and (p.suffix=='.py' or p.name in ('run.sh','run_sim.snapshot.sh'))]
    required = ['ws_package1b/src/bumblebee/examples/drone.py',
        'ws_package1b/src/bumblebee/examples/flight_profile.py',
        'ws_package1b/src/bumblebee/src/cpp/simple_offboard.cpp',
        'ws_package1b/install/bumblebee/lib/bumblebee/simple_offboard',
        'ws_package1b/src/bumblebee/src/python/setpoint_freshness.py',
        'parallel_work/20261015/integration/combined_trial_tools/start_mavros.py',
        'parallel_work/20261015/integration/combined_trial_tools/vision.launch.py',
        'sim/ros_stack/pipeline_probe.py']
    sources += [ROOT/n for n in required] + [LEGACY] + [manifest.parent/n for n in files]
    repo = {str(p.resolve().relative_to(ROOT)):digest(p) for p in sources}
    run = {p.name:digest(p) for p in tools.iterdir() if p.is_file() and (p.suffix=='.py' or p.name in ('run.sh','run_sim.snapshot.sh'))}
    for name in ['drone.py','flight_profile.py']:
        run[name] = digest(ROOT/'ws_package1b/src/bumblebee/examples'/name)
    ledger = {str(p.resolve().relative_to(ROOT)):digest(p) for p in tools.glob('*.py')}
    ledger[str((tools/'run.sh').resolve().relative_to(ROOT))] = digest(tools/'run.sh')
    for name,sha in files.items():
        ledger[str((manifest.parent/name).resolve().relative_to(ROOT))] = sha
    for name in ['ws_package1b/install/bumblebee/lib/bumblebee/simple_offboard',
                 'ws_package1b/src/bumblebee/src/python/setpoint_freshness.py']:
        ledger[name] = repo[name]
    ledger['@run/drone.py'] = run['drone.py']
    return dict(schema=1, scope='Trusted pre-run host snapshot; root must freeze source work before using this file',
        expected_manifest=str(manifest), combined_manifest_sha256=digest(manifest), combined_files=files,
        repo_files=repo, run_files=run, ledger_files=ledger, legacy_verifier_sha256=LEGACY_SHA)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-manifest',type=Path,required=True)
    p.add_argument('--flight-tools',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve()
    if not out.is_relative_to(HERE) or out.exists():
        raise SystemExit('Create a new pins JSON only inside flight_verification_01')
    result=collect(a.expected_manifest.resolve(),a.flight_tools.resolve())
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(pins=str(out),sha256=digest(out),run_files=len(result['run_files']),repo_files=len(result['repo_files']))))


if __name__=='__main__':
    main()
