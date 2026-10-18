---
name: check-consequences-first
description: "Before proposing ANY change (esp. PX4 params, flight behaviour, failsafes), analyse its bad consequences first — the MAV_0_RATE proposal was wrong"
type: feedback
source: copy of the Mac-side Claude memory, 17.10.2026 (session metadata removed)
---

Before I recommend a change, I must first check what can go wrong with it (side effects, interactions, classroom misuse, failure modes), and only present proposals that survived that check — with the downsides stated.

**Why:** on 2026-10-12 I proposed setting PX4 `MAV_0_RATE=1200` to fix the ROS stall; when the user asked "проверь какие могут быть плохие последствия у этого решения", it turned out there were many and the proposal was wrong (the real cause was the Fast DDS shared-memory transport). On 2026-10-13 the user said: remember that case and do not repeat it.

**How to apply:** for every proposed fix or setting (especially in the flight stack — simple_offboard, drone.py, vision, PX4 failsafes/limits), run an adversarial "what breaks / who gets hurt / what interacts" pass (a workflow with skeptic lenses when non-trivial) BEFORE presenting it; list the downsides next to each recommendation; never present a speculative fix as the answer. Related: [[debugging-discipline]], [[bumblebee-work-plan]] rule 4, [[never-arm-motors]].
