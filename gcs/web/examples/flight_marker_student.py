# flight_marker -- the C7 "marker" route written with the student API.
# Same route as examples/flight/flight_marker.py (r2j, map_final copy): take off
# over marker 0, fly over marker 2, back over marker 1, land on marker 0.
# The marker coordinates come from the map on the drone, not from this file.
import drone

drone.require_map('field_real')            # the drone must have this map

if not drone.check_aruco(timeout=10):      # marker 0 under the drone on the floor
    exit(1)
if not drone.wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0):
    exit(1)

try:
    drone.takeoff(height=0.9)
    drone.hover(1.5)
    if drone.fly_to_marker(2, speed=0.10):
        drone.hover(2.0)
        if drone.fly_to_marker(1, speed=0.10):
            drone.hover(1.0)
            drone.fly_to_marker(0, speed=0.10)
finally:
    drone.land_on_marker(0)
