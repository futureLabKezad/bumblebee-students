# Bumblebee: give SSH/login shells the same ROS 2 network scope as the drone's
# services (/etc/bumblebee/ros.env), so `ros2 topic list` and student scripts
# see this drone's nodes -- and only this drone's.
if [ -r /etc/bumblebee/ros.env ]; then
    set -a
    . /etc/bumblebee/ros.env
    set +a
fi
