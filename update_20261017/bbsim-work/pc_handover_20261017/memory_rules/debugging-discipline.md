---
name: debugging-discipline
description: "Lessons from the 2026-10-12 ROS-stall hunt on the drone — how to debug hardware issues without wasting the user's time"
type: feedback
source: copy of the Mac-side Claude memory, 17.10.2026 (session metadata removed)
---

When a drone problem is not understood yet:
1. First look for prior art: the original image's own diagnostics/configs (e.g. freeze dumps, /etc/environment tweaks like FASTDDS_BUILTIN_TRANSPORTS=UDPv4) and known upstream issues — use a parallel research workflow early, not after hours of trial and error.
2. Never state a cause before a control experiment confirms it (wrongly claimed "battery low", "UDP fixes it", "clock jump is the cause", "the app is the trigger").
3. Change one variable at a time; do not deploy speculative fixes (LOCALHOST range, watchdog + socket buffers) to the real drone before the cause is confirmed — they made the drone worse and the experiments noisy.
4. Batch sudo actions into one clear command; the user mis-clicks old Run buttons and gets tired of passwords. Keep updates short.
5. Never `pgrep -f`/`pkill -f` with a pattern that also appears in the ssh command line — it matches the session itself (happened 4 times). Use `systemctl show -p MainPID`, `pidof`, or exact `^/path` patterns.

**Why:** the user said "сколько ждать… сделай выводы по своей работе" after ~3 hours of serial experiments with several wrong conclusions.
**How to apply:** follow [[bumblebee-work-plan]] rules plus this checklist on every on-drone investigation; respect [[never-arm-motors]].
