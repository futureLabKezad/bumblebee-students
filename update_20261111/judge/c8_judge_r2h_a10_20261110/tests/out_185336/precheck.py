import hashlib, json, os, sys
from pathlib import Path
comb, pins_p, trial, work, accepted_p = sys.argv[1:]
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
doc = {'combined_root': comb, 'frozen_pins': pins_p, 'trial': trial, 'problems': []}
P = doc['problems']
try:
    accepted = {l.split()[0] for l in open(accepted_p) if l.strip() and not l.startswith('#')}
    doc['frozen_pins_sha256'] = psha = sha(pins_p)
    if psha not in accepted: P.append('pins %s (sha %s) are not in %s' % (pins_p, psha[:12], accepted_p))
    try:
        pins = json.load(open(pins_p))
        if not isinstance(pins, dict): raise ValueError('not a JSON object')
    except Exception as e:
        P.append('pins unreadable: %s' % e); pins = {}
    croot = Path(comb)
    man = croot / 'manifest.json'
    exp = pins.get('expected_manifest')
    pf = pins.get('combined_files')
    if not isinstance(pf, dict) or not pf: P.append('pins have no combined_files object'); pf = {}
    if not exp: P.append('pins have no expected_manifest')
    elif not man.is_file(): P.append('%s missing' % man)
    else:
        if man.resolve() != Path(exp).resolve():
            P.append('candidate %s is not the pinned manifest %s' % (man.resolve(), exp))
        doc['manifest_sha256'] = msha = sha(man)
        if msha != pins.get('combined_manifest_sha256'):
            P.append('manifest sha256 differs from pins combined_manifest_sha256')
        try: mfiles = json.load(open(man)).get('files', {})
        except Exception as e: mfiles = {}; P.append('manifest unreadable: %s' % e)
        if mfiles != pf: P.append('manifest files differ from pins combined_files')
        bad = []
        for name, h in sorted(pf.items()):
            f = croot / name
            try:
                if f.is_symlink() or not f.resolve().is_relative_to(croot) or not f.is_file() or sha(f) != h: bad.append(name)
            except OSError: bad.append(name)
        if bad: P.append('candidate files differ from pins: ' + ', '.join(bad))
    # nothing else may be in the candidate (run.sh hashes $CAND/*.py into the ledger): only the pinned files,
    # manifest.json and README.md; no symlinks
    allowed = set(pf) | {'manifest.json', 'README.md'}
    extra = []
    for d, dirs, files in os.walk(croot):
        for n in dirs + files:
            full = Path(d) / n; rel = str(full.relative_to(croot))
            if full.is_symlink() or (n in files and rel not in allowed): extra.append(rel)
    if extra: P.append('unexpected entries in the candidate: ' + ', '.join(sorted(extra)[:20]))
    rf = pins.get('repo_files')
    if not isinstance(rf, dict) or not rf: P.append('pins have no repo_files object'); rf = {}
    runner = 'c8_judge_r2h_a10_20261110/executor/run.sh'  # A10: the fixed runner
    if runner not in rf: P.append('pins do not cover TRIAL %s (%s not pinned)' % (trial, runner))
    # c8: every file named by a C8_* parameter must be pinned in repo_files (another target set = new pins = new ACCEPTED_PINS)
    for key in ('C8_AF_FILE', 'C8_MODEL_SDF', 'C8_FLOW_PLUGIN', 'C8_DRONE_PY'):
        rel = os.path.relpath(os.path.realpath(os.environ[key]), work)
        if rel not in rf: P.append('pins do not cover %s (%s not pinned)' % (key, rel))
    bad = []
    for name, h in sorted(rf.items()):
        f = Path(work) / name
        try:
            if not f.is_file() or sha(f) != h: bad.append(name)
        except OSError: bad.append(name)
    if bad: P.append('pinned repo files changed: ' + ', '.join(bad))
except Exception as e:
    P.append('candidate check failed: %r' % e)
doc['ok'] = not P
print(json.dumps(doc)); sys.exit(0 if doc['ok'] else 3)
