---
name: never-arm-motors
description: Hard rule from the user — never start/arm drone motors or send flight commands during diagnostics
type: feedback
source: copy of the Mac-side Claude memory, 17.10.2026 (session metadata removed)
---

Never arm, start motors, take off, run motor_test.py / flight scripts, press arm/takeoff in the app, or call /mavros/cmd/arming, set_mode, offboard setpoints or param writes on a real drone. Diagnostics stay read-only (topics, /diagnostics, rosapi) plus Pi-side-only changes (e.g. `stty` on /dev/ttyAMA0).

**Why:** user said (2026-10-11) "только не включай двигатели умоляю" — a real drone with propellers sits on their desk; a spin-up could injure someone.

**How to apply:** before any on-drone action, check it cannot reach the motors; tell the user what will and won't be touched; suggest props off for bench tests. Also the ground wheel follows RC CH7 (wheel_rc.py) once MAVROS links — ask for the RC transmitter to be off. Part of [[bumblebee-work-plan]] safety rules; see [[bumblebee-sd-image-project]].
