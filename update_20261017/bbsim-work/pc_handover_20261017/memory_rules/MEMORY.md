# Memory rules carried over from the Mac (17.10.2026)

Copies of the previous assistant's memory, cleaned of personal, network and security details (this folder is
published in a public repository). Follow them from the first PC session on.

Where to keep them: Claude Code keeps auto-memory per start folder and loads /work/CLAUDE.md only for a session
started in /work. So: (1) with the owner's permission, put a short hard-rules block into ~/.claude/CLAUDE.md
(loaded by every session); (2) after the restore, create /work/CLAUDE.md; (3) have the owner restart Claude as
`cd /work && claude` (no background job running) and save these files into THAT session's memory (one file each,
this file as the index). Details: ПЕРЕДАЧА_НА_ПК.md section 0.

- [MAIN RULES: Bumblebee work plan](bumblebee-work-plan.md) - rules + phases; consult before every task
- [Never arm motors](never-arm-motors.md) - no motor/flight commands to a real drone ever; diagnostics read-only
- [Check consequences first](check-consequences-first.md) - analyse bad consequences of every proposal before presenting it (MAV_0_RATE lesson)
- [Debugging discipline](debugging-discipline.md) - prior art first, control experiments, one change at a time, no pgrep -f self-match
- [MANDATORY: flight work plan (stage 2)](flight-work-plan.md) - agreed 2026-10-13: order, designs, PX4 groups, presets, Gazebo; last paragraph = state 17.10
- [PC transfer rules](pc-transfer-2026-10-17.md) - /work layout on WSL, launcher, pins, how runs are counted
- [User profile](user-profile.md) - who the owner is and how to talk to him (short simple Russian)
- [Parallel work + Codex](parallel-work-codex.md) - keep helpers busy with useful, clearly described jobs
- [Project background](bumblebee-sd-image-project.md) - drone architecture, stage 1 (SD image) facts, real physical data
