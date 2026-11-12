# READ ONLY (chat 1, 11.11): per-collection boxes of the drone model dump; candidates for rangefinder / FC / camera.
import sys, collections
F = sys.argv[1]
rows = []
for line in open(F, encoding='utf-8'):
    if line.startswith('#'):
        continue
    f = line.rstrip('\n').split('\t')
    if len(f) < 11 or f[0] != 'cur':
        continue
    mn = [float(x) for x in f[6].split(',')]
    mx = [float(x) for x in f[7].split(',')]
    rows.append(dict(name=f[1], type=f[2], parent=f[3], colls=[c for c in f[4].split('|') if c], mn=mn, mx=mx,
                     hidden=f[8], hide_render=f[9], nv=int(f[10])))
by = collections.defaultdict(list)
for r in rows:
    for c in r['colls']:
        by[c].append(r)
print('== collection boxes (meshes only; visible/hidden counts)')
for c in sorted(by):
    ms = [r for r in by[c] if r['type'] == 'MESH']
    if not ms:
        continue
    mn = [min(r['mn'][i] for r in ms) for i in range(3)]
    mx = [max(r['mx'][i] for r in ms) for i in range(3)]
    vis = sum(1 for r in ms if r['hidden'] == 'False')
    print('%-22s n=%3d vis=%3d  x %.4f..%.4f  y %.4f..%.4f  z %.4f..%.4f' % (c, len(ms), vis, mn[0], mx[0], mn[1], mx[1], mn[2], mx[2]))
for want in sys.argv[2:]:
    print('== objects of', want, '(sorted by min z)')
    for r in sorted(by.get(want, []), key=lambda r: r['mn'][2]):
        d = [r['mx'][i] - r['mn'][i] for i in range(3)]
        print('  %-28s %-6s vis=%-5s z %.4f..%.4f  x %.4f..%.4f  y %.4f..%.4f  size %.3fx%.3fx%.3f nv=%d' % (
            r['name'][:28], r['type'], r['hidden'] == 'False', r['mn'][2], r['mx'][2], r['mn'][0], r['mx'][0], r['mn'][1], r['mx'][1], d[0], d[1], d[2], r['nv']))
