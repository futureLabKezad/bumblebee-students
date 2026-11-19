# flight_marker_loop -- the C7 "loop" route written with the student API.
# Same as examples/flight/flight_marker_loop.py (r2j, map_final copy): take off
# 1.3 m, fly over markers 1 -> 2 -> 3 -> 7 -> 13 -> 12 -> 11 -> 5 -> 1 with a 1 s
# hover at each, then home to marker 0 and land. Like the original, no "wait for
# 2 markers" before a leg (that is what fly_to_marker adds).
import drone

drone.require_map('field_real')

ROUTE = [1, 2, 3, 7, 13, 12, 11, 5, 1]

if not drone.check_aruco(timeout=10):
    exit(1)
if not drone.wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0):
    exit(1)

try:
    drone.takeoff(height=1.3)
    drone.hover(1.5)
    for m in ROUTE:
        x, y = drone.marker_xy(m)
        if not drone.fly_to(x, y, speed=0.10):
            print('did not reach marker', m, '- landing')
            break
        drone.hover(1.0)
    else:
        drone.fly_to(0.0, 0.0, speed=0.10)
finally:
    drone.land_on_marker(0)
