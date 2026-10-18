---
name: pc-transfer-2026-10-17
description: Rules specific to running the Bumblebee simulator on the Windows PC (WSL2 Ubuntu 24.04, RTX 4090) - layout, what must never be done, how runs are counted
type: project
source: written for the PC handover on 17.10.2026 (pc_handover_20261017/ПЕРЕДАЧА_НА_ПК.md is the full version)
---

- `/work` is a REAL directory on the WSL ext4 disk (never a symlink, never /mnt/c): the trial code resolve()s
  paths and compares them with literal /work/... (sitl_setup.py:312, start_mavros.py:18, save_run_state.py:8,
  vision.launch.py:16, pipeline_probe.py:67; run.sh:3 `test "$PWD" = /work`). `~/bbsim-work` -> /work and
  /repo -> ~/bumblebee-students (b31ca69) are only convenience links.
- Claude Code runs INSIDE WSL. sudo prompts cannot be answered by Claude: root steps are run by the owner
  (`sudo bash .../setup_wsl_ubuntu2404.sh root`), one password, after a short explanation of what changes,
  in a SECOND Ubuntu window (Windows Terminal "+" -> Ubuntu 24.04, or Start -> Ubuntu 24.04; paste with
  right-click or Ctrl+Shift+V). The password is never typed into Claude's window. The window where Claude runs
  must stay open during setup and trials (closing it stops Claude and its background jobs).
- Hard rules live in ~/.claude/CLAUDE.md (owner's permission) and, after the restore, in /work/CLAUDE.md; start
  Claude as `cd /work && claude` from then on (memory is per start folder).
- Owner-accepted deviations of the setup (BB_ALLOW_NO_GPU / NEWER_PKGS / PY_DIFF) are recorded in
  ~/bb_pc_setup_logs/DEVIATIONS.md; never set one without the owner's explicit yes.
- Never run `/work/build_test.sh` against ws_package1b or ws_sitl: its `rsync --delete` from /repo would destroy the
  package 1b sources, which exist only in /work and the archive.
- Executors flight_trial_02/03 run unchanged on the PC. The Mac-only host_run.sh is replaced by a NEW launcher
  folder `integration/flight_trial_04_wsl/` (keep-awake through SetThreadExecutionState for the run only, Windows
  Kernel-Power events checked afterwards, environment and renderer recorded), reviewed and SHA-pinned before use.
- Before the first PC trial: a NEW `frozen_inputs_05.json` via freeze_pins.py, run as `python3 -B` WITHOUT -I
  (it imports verify_flight from its own folder). Allowed differences from frozen_inputs_03: supervisor.py
  (682e66 -> 95d84234), simple_offboard (aarch64 41803d1c -> x86 hash), expected_manifest path.
  For flight_trial_03: `frozen_inputs_06.json`, compared with frozen_inputs_04 (supervisor.py bed603a0 -> 95d84234,
  simple_offboard 41803d1c -> x86 hash, expected_manifest path). Never regenerate pins after a run.
- check_isolation.py on the PC: exactly one known difference after the rebuild (ws_package1b/install/.../simple_offboard,
  aarch64 pin). Never edit baseline_manifest.json.
- A run counts only if: RTF gate_min >= 0.20 over the guarded phase, clock jump <= 20 s, the Windows host did not
  sleep (event log), and the independent verifier passes. Otherwise it is kept and marked invalid/failed.
- Renderer: prove it from the GL line in ~/.gz/rendering/ogre2.log (TODO-VERIFY path). `--headless-rendering` may
  silently be llvmpipe on WSL. Change one thing at a time: first the Mac-like renderer (llvmpipe) on the PC, then the
  GPU. The acceptance renderer is the owner's decision, recorded, and constant within a series.
- Windows/WSL settings (power plan, .wslconfig, wsl.conf, Defender, updates) are the owner's decisions.
  Never use WSL `networkingMode=mirrored` (the setup and the render/probe checks refuse anything but nat).
  Never install an NVIDIA Linux driver inside WSL.
- PX4-OpticalFlow is pinned to 8758bd5 = what the VM built (confirmed from the VM build tree 17.10).
- The 4 workspace-root documents (flight audit 13.10, plan after 1.0.1, simulator choice) are in
  ~/bumblebee-workspace-docs/ (copied by restore_snapshot.sh overlay from update_20261017/workspace_root_docs/).
- Never CRLF: clone inside WSL with `git -c core.autocrlf=false`, never edit through \\wsl.localhost with Windows editors.
