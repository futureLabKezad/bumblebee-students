# READ ONLY for the .blend (works on a copy, never saves): colour-coded orthographic views to identify parts by eye.
# Run: blender -b -Y <copy.blend> --python blend_views.py -- <out_dir>
import bpy, sys, os, math

out_dir = sys.argv[sys.argv.index('--') + 1:][0]
os.makedirs(out_dir, exist_ok=True)
sc = bpy.context.scene
sc.frame_set(sc.frame_end)
print('BLENDER_VERSION', bpy.app.version_string)

BODY = {'Корпус', 'Крышка', 'Луч1', 'Луч2', 'Луч3', 'Луч4', 'Охлаждение Рама3'}
INNER = {'Ноги', 'низ', 'рама1', 'рама2', 'рама3', 'Плата', 'Полетник', 'Питание плата', 'Распбери', 'РЕГ'}
COLORS = {
    'Body1.382': (1.0, 0.05, 0.05, 1),   # candidate: flow + rangefinder module (red)
    'Body1.153': (0.05, 0.8, 0.05, 1),   # candidate: down camera (green)
    'Body1.152': (0.0, 0.8, 0.9, 1),     # candidate: front camera (cyan)
    'Body847': (0.1, 0.2, 1.0, 1), 'Body848': (0.1, 0.2, 1.0, 1), 'Body849': (0.3, 0.5, 1.0, 1),  # flight controller (blue)
    'Body1.389': (1.0, 0.0, 1.0, 1),     # unknown bottom part (magenta)
}


def colls(ob):
    return {c.name for c in ob.users_collection}


def setup(show):
    for ob in bpy.data.objects:
        cs = colls(ob)
        vis = bool(cs & show) and ob.type == 'MESH'
        ob.hide_render = not vis
        try:
            ob.hide_viewport = not vis
        except Exception:
            pass
        if ob.name in COLORS:
            ob.color = COLORS[ob.name]
        elif 'Ноги' in cs:
            ob.color = (0.95, 0.75, 0.1, 1)
        elif 'Распбери' in cs:
            ob.color = (0.2, 0.55, 0.3, 1)
        elif 'Полетник' in cs:
            ob.color = (0.45, 0.55, 0.9, 1)
        else:
            ob.color = (0.72, 0.72, 0.72, 1)


sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
sh.color_type = 'OBJECT'
sh.show_object_outline = True
sh.show_cavity = True
sh.background_type = 'VIEWPORT'
sh.background_color = (1, 1, 1)
sc.render.film_transparent = False
sc.render.image_settings.file_format = 'PNG'

cam_data = bpy.data.cameras.new('chat1_cam')
cam_data.type = 'ORTHO'
cam = bpy.data.objects.new('chat1_cam', cam_data)
sc.collection.objects.link(cam)
sc.camera = cam


def shot(name, loc, rot, scale, res, show, clip=(0.01, 10.0)):
    setup(show)
    cam.location = loc
    cam.rotation_euler = rot
    cam_data.ortho_scale = scale
    cam_data.clip_start, cam_data.clip_end = clip
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.filepath = os.path.join(out_dir, name)
    bpy.ops.render.render(write_still=True)
    print('SHOT', name)


P = math.pi
# 1. from below, whole drone: image top = drone front (-y), image right = +x
shot('v1_bottom_all.png', (0, 0, -2), (P, 0, 0), 0.62, (1400, 1400), BODY | INNER)
# 2. from below, centre zoom
shot('v2_bottom_zoom.png', (0, 0, -2), (P, 0, 0), 0.30, (1400, 1400), BODY | INNER)
# 3. side view from +x, body shell hidden: image left = front (-y), up = +z
shot('v3_side_inner.png', (2, 0, -0.065), (P / 2, 0, P / 2), 0.46, (1600, 1000), INNER)
# 4. front view from -y, shell hidden: image right = +x
shot('v4_front_inner.png', (0, -2, -0.065), (P / 2, 0, 0), 0.46, (1600, 1000), INNER)
# 5. top view of the inside (shell hidden): image top = +y (rear), right = +x
shot('v5_top_inner.png', (0, 0, 2), (0, 0, 0), 0.30, (1400, 1400), INNER)
print('BLEND_VIEWS_DONE')
