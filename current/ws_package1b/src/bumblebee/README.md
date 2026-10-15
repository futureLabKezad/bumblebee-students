# `bumblebee` ROS package

A bundle for autonomous navigation and drone control.

This is the ROS 2 Jazzy package that runs on the Bumblebee drone (`/home/lb/ros2_ws/src/bumblebee`); the SD image (Ubuntu 24.04) ships it pre-built. Older versions of this file described the original ROS 1 Noetic package (catkin workspace, `roslaunch bumblebee bumblebee.launch`, cloned from `https://github.com/CopterExpress/bumblebee.git`, FCU on `/dev/px4fmu`); those instructions no longer apply.

## Manual installation

On the drone, rebuild after changing the package:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
colcon build --symlink-install --packages-select bumblebee
```

On another ROS 2 Jazzy machine, the ROS packages listed in `package.xml` (`mavros_msgs`, `cv_bridge`, …) can be installed using `rosdep`:

```bash
cd ~/ros2_ws/
rosdep install -y --from-paths src --ignore-src
```

The drone talks to the flight controller over the Raspberry Pi UART `/dev/ttyAMA0`. The MAVLink baud is detected at every start by `scripts/fcu_detect.py` (a read-only probe for CRC-valid MAVLink frames; the result is remembered in `/home/lb/.bumblebee/fcu_url`); a typical PX4 setting is 921600. The `fcu_url` in `/home/lb/mavros_params.yaml` (`/dev/ttyAMA0:115200`, repo copy `drone/system/mavros_params.yaml`) is only the fallback when nothing is detected.

You may optionally install udev rules to provide `/dev/px4fmu` symlink to your PX4-based flight controller connected over USB. Copy `99-px4fmu.rules` to your `/lib/udev/rules.d` folder:

```bash
cd ~/ros2_ws/src/bumblebee/udev
sudo cp 99-px4fmu.rules /lib/udev/rules.d
```

## Running

On the drone the stack starts at boot: `bumblebee.service` runs `/home/lb/start_bumblebee.sh` (waits up to 20 s for the first NTP sync, detects the flight-controller baud, reads the drone's ROS domain from `/etc/bumblebee/ros.env`), which starts:

```bash
ros2 launch bumblebee bumblebee.launch.py
```

For the simulation see [`simulation/`](../../../../simulation/) in this repository.

> Each drone uses its own `ROS_DOMAIN_ID` (see [drone/README.md](../../../README.md)). To see the drone's topics from a laptop, `export ROS_DOMAIN_ID=<n>` of that drone first.
