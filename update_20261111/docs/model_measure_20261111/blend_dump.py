# READ ONLY (chat 1, 11.11): dump object names and world-space bounding boxes of the owner's 1:1 drone model.
# Run: blender -b -Y <file.blend> --python blend_dump.py -- <out.tsv>
# Nothing is saved back into the .blend (no bpy.ops.wm.save*).
import bpy, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
out = argv[0]
sc = bpy.context.scene
us = sc.unit_settings
lines = []
lines.append('# scene=%s unit_system=%s scale_length=%s length_unit=%s frame_start=%d frame_end=%d frame_current=%d'
             % (sc.name, us.system, us.scale_length, us.length_unit, sc.frame_start, sc.frame_end, sc.frame_current))
lines.append('# scenes: %s' % ', '.join(s.name for s in bpy.data.scenes))
for c in bpy.data.collections:
    lines.append('# collection %s: %d objects; children: %s' % (c.name, len(c.objects), ', '.join(ch.name for ch in c.children)))
animated = [o.name for o in bpy.data.objects if o.animation_data and o.animation_data.action]
lines.append('# animated objects: %d %s' % (len(animated), ', '.join(animated[:40])))


def dump(tag):
    for ob in bpy.data.objects:
        mw = ob.matrix_world
        try:
            pts = [mw @ Vector(c) for c in ob.bound_box]
            mn = [min(p[i] for p in pts) for i in range(3)]
            mx = [max(p[i] for p in pts) for i in range(3)]
        except Exception:
            mn = mx = list(mw.translation)
        try:
            hidden = ob.hide_get()
        except Exception:
            hidden = 'n/a'
        nv = len(ob.data.vertices) if ob.type == 'MESH' else 0
        colls = '|'.join(c.name for c in ob.users_collection)
        lines.append('\t'.join([tag, ob.name, ob.type, ob.parent.name if ob.parent else '-', colls,
                                '%.4f,%.4f,%.4f' % tuple(mw.translation),
                                '%.4f,%.4f,%.4f' % tuple(mn), '%.4f,%.4f,%.4f' % tuple(mx),
                                str(hidden), str(ob.hide_render), str(nv)]))


lines.append('# columns: tag name type parent collections loc(x,y,z) bbox_min bbox_max hidden hide_render nverts')
dump('cur')
if animated:
    sc.frame_set(sc.frame_end)
    dump('end')
open(out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('BLEND_DUMP_DONE', len(bpy.data.objects))
