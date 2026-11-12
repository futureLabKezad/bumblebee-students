# READ ONLY (chat 1, 11.11): details for selected collections — data names, materials, exact vertex extremes.
# Run: blender -b -Y <copy.blend> --python blend_dump2.py -- <out.tsv>
import bpy, sys
from mathutils import Vector

out = sys.argv[sys.argv.index('--') + 1:][0]
WANT = {'низ', 'MODUL', 'Полетник', 'Плата', 'Корпус', 'Финал', 'Распбери', 'Питание плата', 'рама1', 'рама2', 'рама3',
        'Охлаждение Рама3', 'Крышка', 'Для проводов', 'Collection', '3', 'LED'}
lines = ['# name\tcollections\tdata\tmaterials\tvmin\tvmax\tnverts\tparent']
for ob in bpy.data.objects:
    cs = [c.name for c in ob.users_collection]
    if not (set(cs) & WANT) or ob.type != 'MESH':
        continue
    mw = ob.matrix_world
    vs = [mw @ v.co for v in ob.data.vertices]
    if not vs:
        continue
    mn = [min(v[i] for v in vs) for i in range(3)]
    mx = [max(v[i] for v in vs) for i in range(3)]
    mats = ','.join(sorted({s.material.name for s in ob.material_slots if s.material}))
    lines.append('\t'.join([ob.name, '|'.join(cs), ob.data.name, mats,
                            '%.4f,%.4f,%.4f' % tuple(mn), '%.4f,%.4f,%.4f' % tuple(mx), str(len(vs)),
                            ob.parent.name if ob.parent else '-']))
mat_names = sorted(m.name for m in bpy.data.materials)
lines.append('# all materials (%d): %s' % (len(mat_names), ', '.join(mat_names)))
open(out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('BLEND_DUMP2_DONE', len(lines))
