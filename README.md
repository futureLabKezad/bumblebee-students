# 🐝 Bumblebee - Drone Programming Learning Platform

Welcome! This repository is your starting point for learning how to program autonomous drones using the **Bumblebee** platform.

## What You'll Learn

- Working with ROS 2 (Robot Operating System) and MAVROS
- Writing flight scripts in Python
- Using the Gazebo simulator for safe testing
- Autonomous drone control - takeoff, navigation, landing
- Working with cameras, ArUco markers, and the Ground Control Station

## Before You Start

All tasks are completed **in the simulator first**, and only then on a real drone. This keeps things safe and lets you make mistakes without consequences.

## Downloads

| What | Download | Size | Guide |
| --- | --- | --- | --- |
| 🖥️ Gazebo simulator for **Windows** (WSL2, pre-built image) | [📥 Download](https://futurelab-uae.technology/s/fz3gBzbM4ENPH59) | ~3.7 GB | [Gazebo Setup (Windows)](https://github.com/futureLabKezad/bumblebee-students/wiki/Gazebo‐Setup‐(Windows)) |
| 🎛️ Ground Control Station 1.2.0 for **Windows** 10/11 x64 (`BumblebeeGCS-1.2.0-windows-x64.zip`: unzip, run `BumblebeeGcs.exe`) | [📥 Download](https://github.com/futureLabKezad/bumblebee-students/releases/tag/gcs-v1.2.0) | ~73 MB | [Ground Control Station](https://github.com/futureLabKezad/bumblebee-students/wiki/Ground‐Control‐Station) |
| 🎛️ Ground Control Station 1.2.0 for **macOS** 14+, Apple Silicon and Intel (`BumblebeeGCS-1.2.0-mac.dmg`: drag to Applications) | [📥 Download](https://github.com/futureLabKezad/bumblebee-students/releases/tag/gcs-v1.2.0) | ~5.7 MB | [Ground Control Station](https://github.com/futureLabKezad/bumblebee-students/wiki/Ground‐Control‐Station) |
| 💾 Drone SD card image 1.0.1 (Raspberry Pi 5, `bumblebee-1.0.1-rpi5.img.xz`, SD card ≥ 16 GB) | [📥 Download](https://github.com/futureLabKezad/bumblebee-students/releases/tag/v1.0.1) | ~2.0 GB | [SD Card Image](https://github.com/futureLabKezad/bumblebee-students/wiki/SD‐Card‐Image) |
| 🔄 Drone update 1.0.2 (over image 1.0.1, `bumblebee-update-1.0.2.tgz`: copy to the drone, run `bb-update/install_on_drone.sh`) | [📥 Download](https://github.com/futureLabKezad/bumblebee-students/releases/tag/v1.0.2) | ~115 KB | [Release v1.0.2](https://github.com/futureLabKezad/bumblebee-students/wiki/Release‐v1.0.2) |

One SD image for every drone: flash it with Raspberry Pi Imager (Device *Raspberry Pi 5* → OS *Use custom* → your card, answer **No** to OS customisation). On first boot the drone names itself `Bumblebee-XXXX` (from its Wi-Fi MAC) and, with no known Wi-Fi around, raises the hotspot `Bumblebee-XXXX` (password `12345678`); press **Add drone** in the GCS to put it on your Wi-Fi. Drones on your Wi-Fi are listed in the GCS automatically by name.

GCS first launch: on the Mac, System Settings → Privacy & Security → *Open Anyway*; on Mac and Windows, allow Location so the app can see Wi-Fi names (new drones are found by their hotspot name).

Several drones can share one Wi-Fi: each drone has its own ROS domain, so before using rviz, rqt or the `ros2` CLI on a laptop, run `export ROS_DOMAIN_ID=<n>` with that drone's number (see [drone/README.md](drone/README.md)).

Previous version V1.0.0-beta (July 2026), kept for rollback: [SD image](https://futurelab-uae.technology/s/wXSZisHxTZE6zHg) (~3.4 GB) · [GCS Windows](https://futurelab-uae.technology/s/PNmQcA7yfLBAY3W) (~291 MB) · [GCS macOS](https://futurelab-uae.technology/s/4gsYow9JBNACqcG) (~201 MB). What changed: [CHANGELOG.md](CHANGELOG.md).

## Full Documentation

All the information you need — setup instructions, code examples, and assignments — can be found in our wiki:

👉 **[Open Bumblebee Students Wiki](https://github.com/futureLabKezad/bumblebee-students/wiki)**

## Repository Structure

```
bumblebee-students/
├── lectures/                        # Lecture slides and Python notebook
├── tasks/                           # Learning assignments
├── examples/                        # Example flight scripts + drone.py API
├── drone/                           # On-board source code (ROS 2 workspace + system files)
├── simulation/                      # Simulator source code and Windows installer scripts
├── gcs/                             # Ground Control Station source code (macOS + Windows)
├── system-images-for-bumblebee/     # Raspberry Pi SD card images for the drone
├── PX4_bin/                         # PX4 firmware binaries for the flight controller
├── PX4_parameters/                  # PX4 parameter snapshots
├── kezadArucoMap/                   # ArUco marker map of the KEZAD polygon
└── README.md                        # This file
```

## License

This project is licensed under the **Apache License 2.0** — you are free to use, modify and redistribute the code, provided the FutureLab copyright and the `NOTICE` file are preserved. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Components derived from the Clover project (Copter Express Technologies) keep their original MIT license notices.

## Need Help?

Check the wiki first - it covers the most common questions. If something isn't working, don't panic: ask your instructor or open an Issue in the repository.

Good luck and smooth landings! 🚁
