# corner_18 -- a route to the field corner over marker 18 (+X, -Y).
# Gazebo 16-17.11: over 18 only one marker is in the frame in 99 % of frames,
# routes a/b/e never reached it. The simulation should show the red zone.
import drone

drone.require_map('field_real')
if not drone.check_aruco(timeout=10):
    exit(1)

try:
    drone.takeoff(height=0.9)
    drone.hover(1.0)
    if drone.fly_to_marker(9, speed=0.10):
        drone.hover(1.0)
        drone.fly_to_marker(18, speed=0.10)
        drone.hover(3.0)
finally:
    drone.land_on_marker(0)
