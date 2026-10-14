# Simulator trial (Gazebo Harmonic + PX4 v1.16.1 SITL)

A 1-2 day trial before we build strict simulator checks for the Bumblebee
software (decision: Gazebo, not Isaac Sim). Question: does a machine without a
GPU - a free GitHub runner (ubuntu-24.04, 4 vCPU) and the Lima VM on the Mac -
run the simulator fast enough with a camera rendering, and does it fly
reliably?

**Pass criteria**

| Criterion | Measured by |
|---|---|
| RTF >= 0.3 while every camera renders | `measure_rtf.py`, 120 s window, Gazebo's own sim/real clocks |
| 10 automated flights in a row, no failure | `smoke_flights.py`: arm, climb to 1 m, hover 10 s, land, disarm |

RTF = simulated seconds per real second. 0.3 means a 10 s hover takes ~33 s.

## Models

The future faithful setup is: no GPS, ArUco vision position, optical flow +
rangefinder, downward camera 640x480. No stock PX4 1.16 model has all of it,
so the trial measures the two stock models that bracket it:

| Model | Airframe | Sensors that render | Role |
|---|---|---|---|
| `x500_flow` | 4021 | flow camera 100x100 @ 50 Hz, 1-ray lidar @ 50 Hz; **no GPS** | closest flight setup (flow + rangefinder, GPS off); light rendering |
| `x500_mono_cam_down` | 4014 | downward camera 1280x960 @ 30 Hz; GPS | rendering upper bound (4x the pixels of our 640x480 camera) |

A Gazebo camera renders only while something subscribes to it (gz-sim skips
rendering sensors without connections). `measure_rtf.py` subscribes to every
camera image topic and counts the frames, so each result shows that the
cameras really rendered and at what rate.

## Pins (nothing floats)

| What | Pin | Where |
|---|---|---|
| PX4 | tag `v1.16.1` = commit `94cb2012792b...` (= the drones' FMU-v6C) | `versions.env`, checked by `build_px4.sh`, `run_trial.sh` and again over MAVLink (`AUTOPILOT_VERSION`) |
| PX4 Gazebo models | submodule `e05f4312` (recorded in the tag) | `versions.env` |
| PX4-OpticalFlow | `5d60b9e` - PX4 v1.16.1 itself clones `master` (moved on 2026-09-21); we pin what master was on the tag date via a local git mirror | `versions.env`, `build_px4.sh` |
| Gazebo Harmonic | 124 packages at exact versions (gz-sim 8.15.0), same list for amd64 and arm64; apt key by sha256 | `apt-gz-harmonic.txt`, `install_deps.sh` |
| Ubuntu packages (CI) | container `ubuntu:noble-20260911@sha256:...` + one dated archive snapshot `20260928T000000Z` for every Ubuntu package (versions and SHA256 from the snapshot index; the identical `.deb` files mostly come from the Azure Ubuntu mirror, see below) | `.github/workflows/sim-trial.yml`, `apt-ubuntu.txt`, `apt_prefetch.sh` |
| Python | PX4's `requirements.txt` resolved to exact versions + sha256 (pymavlink 2.4.50 included) | `requirements*.txt`, `setup_venv.sh` |
| GitHub actions | commit SHAs | workflow |

Each run also records what was really installed (`packages.tsv`,
`pip-freeze.txt`, `system.txt`, `renderer.txt`).

Two deliberate deviations from a plain `make px4_sitl gz_<model>`:
* Gazebo is started by `run_trial.sh` (PX4 in its documented standalone mode,
  `PX4_GZ_STANDALONE=1`) so the script owns its process, logs and render flags;
* PX4's `server.config` is used without `GstCameraSystem` (x264 video streaming
  of a camera on the CPU): our software never does that, it would only skew RTF.
  The GStreamer dev packages are not installed for the same reason.

## Safety

Simulator only. `smoke_flights.py` refuses any MAVLink endpoint other than a
UDP port on 127.0.0.1, and refuses to arm unless the vehicle reports
`SIM_GZ_EN = 1` (a parameter that exists only in PX4 SITL with Gazebo). Gazebo
transport stays on 127.0.0.1 in a private `GZ_PARTITION`. Nothing here connects
to a drone (no ssh, nothing to 10.255.254.x).

## CI

`.github/workflows/sim-trial.yml` runs on push to `feat/sim-trial` and by hand
(*Actions -> Simulator trial -> Run workflow*: flights, RTF seconds, `xvfb` or
`egl` rendering). One job per model, in parallel. Results: the job summary
table, and the artifact `sim-trial-<model>-attempt<N>` (summary, RTF/CPU/RAM
time series, flights, px4/gz logs, ulog files).

Downloads: `install_deps.sh` lets `apt_prefetch.sh` fetch every `.deb` first,
6 at a time, and accepts a file only if its size and SHA256 match apt's signed
index. In CI it takes snapshot pool files from `UBUNTU_POOL_MIRRORS` (Azure
Ubuntu mirror, then archive.ubuntu.com) and only falls back to
snapshot.ubuntu.com for versions the mirror no longer has (~3%). The
snapshot alone was the bottleneck: ~400 MB took 16 min on a good day and on
2026-10-13 ran at ~50 kB/s with HTTP 503s until the job failed after 2 hours.
The install step has a 45 min limit.

Expected time per job: first run ~30-45 min (Ubuntu + Gazebo install ~5-7 min,
PX4 build ~10-15 min, trial 10-25 min depending on RTF); later runs reuse the
cached PX4 build, ~15-30 min.

## Lima VM (Ubuntu 24.04 arm64) - same scripts

```bash
cd /repo/simulation/trial                 # read-only mount is fine
sudo ./install_deps.sh                    # Ubuntu packages + pinned Gazebo (checks the pins)
./setup_venv.sh                           # ~/.venvs/bb-sim-trial
./build_px4.sh                            # ~/PX4-Autopilot at v1.16.1 (PX4_DIR=... to change)
./run_trial.sh --model x500_flow --out ~/sim-trial-out/x500_flow-1
./run_trial.sh --model x500_mono_cam_down --out ~/sim-trial-out/x500_mono_cam_down-1
```

Options: `--flights N`, `--rtf-seconds S`, `--min-rtf X`, `--render egl`,
`--instance N` (MAVLink port 14540+N, to run beside another PX4). Exit code 0 =
criteria met, 1 = not met, 2 = could not run. In Lima the Ubuntu packages come
from the live arm64 archive (snapshot.ubuntu.com has no arm64); Gazebo, PX4 and
Python are pinned exactly as in CI.

## Output folder

| File | Content |
|---|---|
| `summary.md`, `summary.json` | verdict, RTF, cameras, flights, CPU/RAM, timings |
| `rtf.json`, `rtf_samples.jsonl` | 120 s window: RTF (whole, 10 s windows), frames per camera, CPU/RAM per second |
| `rtf_flights.json`, `rtf_flights_samples.jsonl` | the same during the flights |
| `flights.json`, `flights.log` | per flight: phases (sim/wall s), hover drift and height error, errors, PX4 messages |
| `commands.log`, `timings.json` | exact commands with timestamps, phase times |
| `system.txt`, `renderer.txt`, `packages.tsv`, `pip-freeze.txt` | machine, renderer (expect llvmpipe), versions |
| `px4.log`, `gz.log`, `px4_rootfs/log/**/*.ulg` | PX4 and Gazebo logs, PX4 flight logs |

## Updating the pins

* Gazebo: OSRF keeps only the newest build of each package, so the install
  stops working when Harmonic is updated (on purpose). Regenerate
  `apt-gz-harmonic.txt` as the dependency closure of `gz-harmonic` in the new
  `packages.osrfoundation.org` noble index (same list for amd64/arm64), update
  `GZ_SIM_VERSION`, re-run the trial.
* Ubuntu: new `UBUNTU_SNAPSHOT` (and, if needed, base image digest) in the
  workflow; the snapshot date must not be older than the image.
* Python: the `uv pip compile` command in `requirements.in`.
