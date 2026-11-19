"""How many floor markers the down camera can see from a point (17.11.2026).

Model: pinhole camera looking straight down (roll = pitch = 0), mounted on the
body as on 20EC: +0.081 m forward of base_link, 0.034 m below it (ЭТАЛОН_РАЗМЕРОВ_20EC).
Image axes (both r2j launch TF "down + backward" and the Gazebo model.sdf):
image x (right) = body right, image y (down) = body backward.

A marker counts as visible when all 4 corners fall inside the image, within the
cone tan <= `max_tan` around the camera nadir, and its side is >= `min_side_px`.

`max_tan` is NOT a camera fact: in the Gazebo runs a marker inside the frame is
often not decoded (96 real rows, pyramid, tracking). calib/calib_gazebo.py fits
it on the Gazebo frames; for the real drone it is still unmeasured.

Heights: the TRUE map z of base_link (on the floor -0.11 in Gazebo); the marker
plane is at map z = mp['z'] (-0.32). Camera height above the floor
= z_base - mount_down - mp['z']. drone.py prints EKF z, whose zero drifts between
runs (start z -0.57..+0.28): calibration shifts each run so that its start is -0.11.
"""
import math

from . import bbmap

# The usable image of the down camera, on the drone AND in Gazebo (proved by chat 1's
# camera review 17.11 and the review of this module): the drone’s calibration
# /home/lb/.ros/camera_info/main_camera_640x480.yaml (sha c002c604, equidistant) has
# K fx 251.99, fy 314.81, cx 352.09, cy 306.35 for 640x480; aruco_detect undistorts
# with new_K = K, so the detector sees this pinhole window. Gazebo model.sdf has the same
# <intrinsics>, and its strict bridge distorts the render with the real K/D.
# (fisheye_cam_320x240.yaml in the image is NOT used in flight - my first version took it, wrong.)
# Forward (image up) reaches tan 0.97, backward (image down) only tan 0.55.
_K = {'W': 640, 'H': 480, 'fx': 251.99, 'fy': 314.81, 'cx': 352.09, 'cy': 306.35}
CAMERAS = {
    'gazebo': dict(_K, **{
        # max_tan 0.95: calib/out/calib_gazebo.json v2 - fitted on 33 runs (81 388 frames),
        # CHECKED on the other 32 runs (79 383 frames): count exact 50 %, within +-1 in 92 %,
        # mean error +0.13 marker. The full frame (no cone) over-predicts by 2.1 on average.
        'label': 'Gazebo (fitted on half of the runs of the real map, checked on the other half)',
        'mount_fwd': 0.081, 'mount_left': 0.0, 'mount_down': 0.034,
        'inner': 1.0, 'min_side_px': 12.0, 'max_tan': 0.95, 'calibrated': True,
    }),
    'drone': dict(_K, **{
        # Same geometry. The detection limit max_tan is TAKEN FROM GAZEBO: on the real drone
        # it is not measured, and Gazebo is optimistic (detector 23 fps there vs 6.4-7.0 on the
        # Pi at 99 % CPU; no noise or blur; 96 real image rows; marker 0 on the floor read in
        # 46.9 % of messages on the drone) - chat 1, camera_review_20261117. An ESTIMATE.
        'label': 'Drone 20EC (estimate: the drone’s camera, limit as in Gazebo; not measured on the drone)',
        'mount_fwd': 0.081, 'mount_left': 0.0, 'mount_down': 0.034,
        'inner': 1.0, 'min_side_px': 12.0, 'max_tan': 0.95, 'calibrated': False,
    }),
}

# The drone never holds a point exactly, and a marker near the edge of the cone
# flips in and out. So the count used for the colours is the MEAN over the point
# and 4 points JITTER metres around it. JITTER = 0.12 m is the EKF error of the
# Gazebo runs (p95 0.09-0.21 m, ИТОГ_ПОЛЕ_REAL), not a fitted number.
# Check against Gazebo at true z 0.71-0.85 (calib/out/calib_gazebo.json v2, per marker):
#   over 0, 1, 2, 3, 5, 6, 7, 8, 13, 16  model 2.0-2.4 -> yellow  (Gazebo mean 1.7-2.35; >= 2 markers in 74-93 % of frames)
#   over 10, 18, 19                      model 1.0     -> red     (Gazebo mean 0.83-0.99; >= 2 markers in 0-0.7 % of frames)
JITTER = 0.12
RED_BELOW = 1.5        # mean < 1.5 -> red ("one marker or none")
GREEN_FROM = 2.5       # mean >= 2.5 -> green; between -> yellow
# 18.11: inside red, a mean below 0.5 is shown apart as a BLIND spot: at most 2 of the 5
# points see one marker, usually none. Only the picture changes: red stays red everywhere.
BLIND_BELOW = 0.5

# Heights (18.11, chat 1 item a). ЭТАЛОН_РАЗМЕРОВ_20EC (Blender model 1:1, 11.11): when the
# drone stands, centre B (= base_link) is 0.217 m above the floor and the down camera lens
# 0.183 m (0.217 - 0.034, the mount above). drone.py (r2j, line 2410) takes off to
# z_start + height in the map frame, i.e. `height` is counted from where the drone stood.
# So in flight, after takeoff(height): base_link 0.217 + height above the floor, camera
# 0.183 + height. (Gazebo’s -0.11 rest z is 7 mm lower than the reference; the reference wins.)
# The markers lie on the floor: the floor is the marker plane, map z = mp['z'].
BASE_ABOVE_FLOOR_REST = 0.217


def camera(name, **override):
    c = dict(CAMERAS[name])
    c.update(override)
    return c


def camera_xy(x, y, yaw, cam):
    """Floor point under the camera for base_link at (x, y) with heading yaw (map frame, ENU)."""
    c, s = math.cos(yaw), math.sin(yaw)
    f, l = cam['mount_fwd'], cam['mount_left']
    return x + c * f - s * l, y + s * f + c * l


def project(px, py, x, y, z_base, yaw, cam, z_floor):
    """Pixel (u, v) of floor point (px, py), or None if the camera is not above the floor."""
    h = z_base - cam['mount_down'] - z_floor
    if h <= 0.05:
        return None
    ox, oy = camera_xy(x, y, yaw, cam)
    dx, dy = px - ox, py - oy
    c, s = math.cos(yaw), math.sin(yaw)
    fwd = c * dx + s * dy          # body forward component
    left = -s * dx + c * dy        # body left component
    u = cam['cx'] + cam['fx'] * (-left) / h
    v = cam['cy'] + cam['fy'] * (-fwd) / h
    return u, v


def marker_visible(m, x, y, z_base, yaw, cam, z_floor):
    h = z_base - cam['mount_down'] - z_floor
    if h <= 0.05:
        return False
    if m['length'] * min(cam['fx'], cam['fy']) / h < cam['min_side_px']:
        return False
    inner = cam['inner']
    hw, hh = inner * cam['W'] / 2.0, inner * cam['H'] / 2.0
    mx, my = cam['W'] / 2.0, cam['H'] / 2.0
    max_tan = cam.get('max_tan')
    if max_tan:
        ox, oy = camera_xy(x, y, yaw, cam)
        lim = (max_tan * h) ** 2
    for px, py in bbmap.corners(m):
        u, v = project(px, py, x, y, z_base, yaw, cam, z_floor)
        if abs(u - mx) > hw or abs(v - my) > hh:
            return False
        if max_tan and (px - ox) ** 2 + (py - oy) ** 2 > lim:
            return False
    return True


def visible_ids(mp, x, y, z_base, yaw, cam):
    z_floor = mp.get('z', bbmap.DEFAULT_Z)
    return [m['id'] for m in mp['markers'] if marker_visible(m, x, y, z_base, yaw, cam, z_floor)]


def expected_count(mp, x, y, z_base, yaw, cam, jitter=JITTER, _near=None):
    """Mean number of visible markers over (x, y) and 4 points `jitter` m around it."""
    z_floor = mp.get('z', bbmap.DEFAULT_Z)
    markers = mp['markers'] if _near is None else _near
    pts = [(x, y)] if jitter <= 0 else [(x, y), (x + jitter, y), (x - jitter, y), (x, y + jitter), (x, y - jitter)]
    total = 0
    for px, py in pts:
        for m in markers:
            if marker_visible(m, px, py, z_base, yaw, cam, z_floor):
                total += 1
    return total / len(pts)


def footprint(x, y, z_base, yaw, cam, z_floor):
    """4 floor corners (x, y) of the image, map frame; [] if not above the floor.
    Uses cx, cy: with the drone’s K the frame reaches tan 0.97 forward, 0.55 back."""
    h = z_base - cam['mount_down'] - z_floor
    if h <= 0.05:
        return []
    ox, oy = camera_xy(x, y, yaw, cam)
    right = (cam['W'] - cam['cx']) * h / cam['fx']
    left = cam['cx'] * h / cam['fx']
    back = (cam['H'] - cam['cy']) * h / cam['fy']
    fwd = cam['cy'] * h / cam['fy']
    c, s = math.cos(yaw), math.sin(yaw)
    pts = []
    for f, l in ((fwd, left), (fwd, -right), (-back, -right), (-back, left)):
        pts.append((ox + c * f - s * l, oy + s * f + c * l))
    return pts


def grid(mp, z_base, yaw, cam, step=0.10, margin=0.6, jitter=JITTER):
    """Mean counts (expected_count) on a grid over the field.

    Returns {'x0','y0','step','nx','ny','counts': [[row y0..], ...] (counts[j][i] at x0+i*step, y0+j*step)}.
    Fast enough in Pyodide for step 0.1 m on a 3 x 4 m field.
    """
    xmin, ymin, xmax, ymax = bbmap.bounds(mp, margin)
    nx = int(round((xmax - xmin) / step)) + 1
    ny = int(round((ymax - ymin) / step)) + 1
    z_floor = mp.get('z', bbmap.DEFAULT_Z)
    h = z_base - cam['mount_down'] - z_floor
    reach = (max(cam['W'] / cam['fx'], cam['H'] / cam['fy']) * h * 0.75 + 0.6 + jitter) if h > 0 else 0
    counts = []
    for j in range(ny):
        py = ymin + j * step
        row = []
        for i in range(nx):
            px = xmin + i * step
            near = [m for m in mp['markers'] if abs(m['x'] - px) <= reach and abs(m['y'] - py) <= reach]
            row.append(round(expected_count(mp, px, py, z_base, yaw, cam, jitter, _near=near), 2))
        counts.append(row)
    out = {'x0': xmin, 'y0': ymin, 'step': step, 'nx': nx, 'ny': ny, 'counts': counts,
           'z_base': z_base, 'yaw': yaw, 'camera': cam.get('label', ''),
           'red_below': RED_BELOW, 'green_from': GREEN_FROM, 'blind_below': BLIND_BELOW}
    out['heights'] = heights(z_base, cam, z_floor)
    return out


def level(n):
    """Colour for a mean count: 'red' < 1.5, 'yellow' < 2.5, 'green' otherwise."""
    return 'red' if n < RED_BELOW else ('yellow' if n < GREEN_FROM else 'green')


def shade(n):
    """level() with the blind part of red apart: 'blind' < 0.5, then 'red', 'yellow', 'green'."""
    return 'blind' if n < BLIND_BELOW else level(n)


def z_base_after_takeoff(height, z_floor):
    """Map z of base_link after drone.takeoff(height) from the floor (see BASE_ABOVE_FLOOR_REST)."""
    return z_floor + BASE_ABOVE_FLOOR_REST + height


def heights(z_base, cam, z_floor):
    """Height above the floor of the drone’s centre and of the down camera, m."""
    base = z_base - z_floor
    return {'base': base, 'camera': base - cam['mount_down']}


def point(mp, x, y, z_base, yaw, cam, jitter=JITTER):
    """What the drone at (x, y) sees: for the hint under the cursor.

    {'mean', 'shade', 'ids' (visible from exactly this point), 'footprint' (image corners
    on the floor), 'cone': [cx, cy, r] (the detection cone max_tan, or None), 'camera'
    (height above the floor of the camera), 'base'}."""
    z_floor = mp.get('z', bbmap.DEFAULT_Z)
    mean = expected_count(mp, x, y, z_base, yaw, cam, jitter)
    h = z_base - cam['mount_down'] - z_floor
    ox, oy = camera_xy(x, y, yaw, cam)
    cone = [ox, oy, cam['max_tan'] * h] if cam.get('max_tan') and h > 0.05 else None
    out = {'mean': round(mean, 2), 'shade': shade(mean), 'ids': sorted(visible_ids(mp, x, y, z_base, yaw, cam)),
           'footprint': footprint(x, y, z_base, yaw, cam, z_floor), 'cone': cone}
    out.update(heights(z_base, cam, z_floor))
    return out
