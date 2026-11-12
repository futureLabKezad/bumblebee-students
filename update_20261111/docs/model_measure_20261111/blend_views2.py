# READ ONLY for the .blend (works on a copy, never saves): views with the SELECTED parts solid and the rest ghosted,
# plus pixel anchors of the selected parts for labels.
# Run: blender -b -Y <copy.blend> --python blend_views2.py -- <out_dir>
import bpy, sys, os, math, json
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

out_dir = sys.argv[sys.argv.index('--') + 1:][0]
os.makedirs(out_dir, exist_ok=True)
sc = bpy.context.scene
sc.frame_set(sc.frame_end)

BODY = {'Корпус', 'Крышка', 'Луч1', 'Луч2', 'Луч3', 'Луч4', 'Охлаждение Рама3'}
INNER = {'Ноги', 'низ', 'рама1', 'рама2', 'рама3', 'Плата', 'Полетник', 'Питание плата', 'Распбери', 'РЕГ'}
SEL = {
    'Body1.382': ('flow', (1.0, 0.05, 0.05, 1)),
    'Body1.153': ('cam_down', (0.05, 0.75, 0.05, 1)),
    'Body1.152': ('cam_front', (0.0, 0.75, 0.9, 1)),
    'Body847': ('fc', (0.1, 0.2, 1.0, 1)), 'Body848': ('fc', (0.1, 0.2, 1.0, 1)), 'Body849': ('fc', (0.1, 0.2, 1.0, 1)),
}
FLOOR_Z = -0.1857
LENS_Z = -0.0027
FC_Z = 0.047


def colls(ob):
    return {c.name for c in ob.users_collection}


def bbox_center(names):
    pts = []
    for n in names:
        ob = bpy.data.objects[n]
        pts += [ob.matrix_world @ v.co for v in ob.data.vertices]
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    return (mn + mx) / 2, mn, mx


def setup(show, ghost_alpha, legs_alpha):
    for ob in bpy.data.objects:
        cs = colls(ob)
        vis = bool(cs & show) and ob.type == 'MESH'
        ob.hide_render = not vis
        if ob.name in SEL:
            ob.color = SEL[ob.name][1]
        elif 'Полетник' in cs:
            ob.color = (0.35, 0.45, 0.95, max(ghost_alpha, 0.55))
        elif 'Ноги' in cs:
            ob.color = (0.95, 0.75, 0.1, legs_alpha)
        else:
            ob.color = (0.70, 0.70, 0.70, ghost_alpha)


sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
sh.color_type = 'OBJECT'
sh.show_object_outline = True
sh.show_cavity = True
sh.show_xray = False
sh.background_type = 'VIEWPORT'
sh.background_color = (1, 1, 1)
sc.render.film_transparent = False
sc.render.image_settings.file_format = 'PNG'

cam_data = bpy.data.cameras.new('chat1_cam2')
cam = bpy.data.objects.new('chat1_cam2', cam_data)
sc.collection.objects.link(cam)
sc.camera = cam

c_flow, mn_flow, mx_flow = bbox_center(['Body1.382'])
c_camd, mn_camd, mx_camd = bbox_center(['Body1.153'])
c_camf, _, _ = bbox_center(['Body1.152'])
c_fc, mn_fc, mx_fc = bbox_center(['Body847', 'Body848'])
c_leg, mn_leg, mx_leg = bbox_center(['Body1.021'])
POINTS = {
    'flow': c_flow, 'cam_down': c_camd, 'cam_front': c_camf, 'fc': c_fc, 'leg': c_leg,
    'flow_lens': Vector((c_flow.x, c_flow.y, LENS_Z)),
    'flow_floor': Vector((c_flow.x, c_flow.y, FLOOR_Z)),
    'fc_level': Vector((c_fc.x, c_fc.y, FC_Z)),
    'fc_at_lens_level': Vector((c_fc.x, c_fc.y, LENS_Z)),
    'floor_front': Vector((0.0, -0.20, FLOOR_Z)), 'floor_rear': Vector((0.0, 0.20, FLOOR_Z)),
}
anchors = {'_world': {k: [round(v.x, 4), round(v.y, 4), round(v.z, 4)] for k, v in POINTS.items()}}


def shot(name, loc, rot, res, show, ghost_alpha, legs_alpha, ortho=None, lens=None, target=None):
    setup(show, ghost_alpha, legs_alpha)
    cam.location = loc
    if target is not None:
        d = Vector(target) - Vector(loc)
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    else:
        cam.rotation_euler = rot
    if ortho:
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = ortho
    else:
        cam_data.type = 'PERSP'
        cam_data.lens = lens
    cam_data.clip_start, cam_data.clip_end = 0.01, 20.0
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    bpy.context.view_layer.update()
    a = {}
    for k, v in POINTS.items():
        co = world_to_camera_view(sc, cam, v)
        a[k] = [round(co.x * res[0], 1), round((1 - co.y) * res[1], 1)]
    anchors[name] = a
    sc.render.filepath = os.path.join(out_dir, name)
    bpy.ops.render.render(write_still=True)
    print('SHOT', name)


P = math.pi
# A. from below, opaque (what you see when the drone is turned over): top = front
shot('a_bottom.png', (0, 0, -2), (P, 0, 0), (1400, 1400), BODY | INNER, 1.0, 1.0, ortho=0.30)
# B. side view from +x, rest ghosted: left = front, up = +z
shot('b_side.png', (2, 0, -0.065), (P / 2, 0, P / 2), (1600, 1000), BODY | INNER, 0.16, 0.45, ortho=0.46)
# C. perspective from below, front-left, rest ghosted
shot('c_persp.png', (0.40, -0.52, -0.34), None, (1600, 1100), BODY | INNER, 0.30, 0.45, lens=42, target=(0.0, -0.02, -0.03))
json.dump(anchors, open(os.path.join(out_dir, 'anchors.json'), 'w'), indent=1)
print('BLEND_VIEWS2_DONE')
