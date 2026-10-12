# 🛠️ Drone Source Code

The complete on-board software of the Bumblebee drone, extracted from the official SD card image (`030726`, see [SD Card Image](https://github.com/futureLabKezad/bumblebee-students/wiki/SD‐Card‐Image)). On the drone this lives in `/home/lb/ros2_ws/src`.

## Layout

| Path | What it is |
| --- | --- |
| `ros2_ws/src/bumblebee/` | Main package: C++ flight core `simple_offboard`, launch files, `scripts/` (wifi manager, LED, sys metrics), `examples/` (drone.py), web dashboard `www/` |
| `ros2_ws/src/aruco_pose/` | ArUco marker detection and map-based pose estimation |
| `ros2_ws/src/bumblebee_bridge/` | I2C bridge to the ATtiny companion (LED strips, gripper servo, wheel) |
| `ros2_ws/src/bumblebee_description/` | URDF model and meshes of the drone |
| `system/systemd/` | systemd units: `bumblebee.service`, wifi manager/watchdog, LED, metrics, I2C recovery |
| `system/start_bumblebee.sh` | Entry point started by `bumblebee.service` |
| `system/mavros_params.yaml` | MAVROS configuration (`/home/lb/mavros_params.yaml` on the drone) |
| `system/i2c_recover.sh` | I2C bus recovery run at boot (`/usr/local/sbin/` on the drone) |

## Building on the drone

```bash
ssh lb@<drone-ip>            # password: lb
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
colcon build --symlink-install --packages-select bumblebee
```

How it all fits together: [System Architecture](https://github.com/futureLabKezad/bumblebee-students/wiki/System‐Architecture) · [Launch Pipeline](https://github.com/futureLabKezad/bumblebee-students/wiki/Launch‐Pipeline) · [System Services](https://github.com/futureLabKezad/bumblebee-students/wiki/System‐Services)

## Updating a running drone

`tools/deploy.sh` installs the files listed in `tools/MANIFEST` on a drone
over SSH. It backs up everything it replaces and writes a `rollback.sh`, refuses
to run while the drone is armed, and only restarts the Wi-Fi / metrics /
identity services. `bumblebee.service` and the flight stack are not touched.

```bash
drone/tools/deploy.sh <drone-ip>                 # keeps the drone's current name
drone/tools/deploy.sh <drone-ip> --reset-name    # drones flashed from V1.0.0-beta (all "bumblebee-4")
```

Roll back with `bash ~/.bumblebee-update/<timestamp>/rollback.sh` on the drone,
then reboot it (`sudo reboot`): until then the flight stack keeps running with
the update.

## Tests

```bash
pip install tornado bcrypt
cd drone/ros2_ws/src/bumblebee && python3 -m unittest test/test_wifi_manager.py test/test_wifi_watchdog.py test/test_set_identity.py
python3 gcs/tools/mock_drone.py     # mock drone for the GCS apps (real wifi_manager.py)
```
