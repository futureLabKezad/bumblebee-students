#!/usr/bin/python3
"""trial_runner.py - goal step 5b (Claude, 09.11.2026). SIMULATOR STAND ONLY. Labelled trial option --trial-map-file.

Runs an UNMODIFIED example script of the image like `python3 -u SCRIPT` does, with exactly ONE labelled change:
the module constant drone.MAP_FILE (the file drone.set_aruco_map() writes, drone.py:625) is set to MAP_OUT instead of
/home/lb/ros2_ws/src/aruco_pose/map/map.txt. Reason: /home/lb does not exist on the PC and cannot be created without
sudo; open(MAP_FILE, 'w') would raise FileNotFoundError and stop the script before arming (drone.py:1535).
Nothing else changes:
  * the script file, drone.py and flight_profile.py are the image's files (read-only, sha256 recorded by the launcher);
  * the script runs as __main__ (runpy.run_path), sys.argv[0] = the script, sys.path[0] = the script's folder (as
    `python3 SCRIPT` sets it); the script's own sys.path.insert('/home/lb/...examples') is a folder that does not
    exist on the PC, so `import drone` resolves from PYTHONPATH (the image's examples folder) - recorded below;
  * exceptions and exit codes propagate unchanged; nothing is printed to the script's output.
Why this is faithful for the drone (checked by code, report F2): the running marker detector (aruco_detect.py) reads
its map once at start from install/aruco_pose/share/aruco_pose/map/map.txt and never re-reads it during a session,
and the C++ aruco_map node is disabled in the image; so on the drone, too, the written file does not reach the
detector during the flight. The written file is kept in the run folder and compared with the image map.
Writes RUN/trial_runner.json (what was loaded) before the script starts.
Usage: python3 -u trial_runner.py --map-file MAP_OUT --record JSON_OUT SCRIPT
"""
import hashlib
import json
import os
import runpy
import sys


def sha(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    args = sys.argv[1:]
    map_out = args[args.index('--map-file') + 1]
    record = args[args.index('--record') + 1]
    script = os.path.abspath(args[-1])
    readonly = '--map-readonly' in args   # 09.11 r2b: set_aruco_map only compares with MAP_FILE (no write)
    if readonly:
        if not os.path.isfile(map_out):
            sys.exit('trial_runner: --map-readonly but %s missing' % map_out)
    else:
        if os.path.exists(map_out):
            sys.exit('trial_runner: refusing, %s exists' % map_out)
        os.makedirs(os.path.dirname(map_out), exist_ok=True)
    sys.argv = [script]
    sys.path[0] = os.path.dirname(script)
    import drone  # noqa: E402  (the image's examples/drone.py via PYTHONPATH; the script's `import drone` gets this module)
    rec = {'script': script, 'script_sha256': sha(script), 'drone_py': drone.__file__,
           'drone_py_sha256': sha(drone.__file__), 'map_file_image_default': drone.MAP_FILE,
           'map_file_trial': map_out, 'home_lb_exists': os.path.exists('/home/lb'),
           'sys_path_head': sys.path[:4]}
    with open(record, 'x', encoding='utf-8') as f:
        json.dump(rec, f, indent=1)
    drone.MAP_FILE = map_out
    runpy.run_path(script, run_name='__main__')


if __name__ == '__main__':
    main()
