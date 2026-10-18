---
name: parallel-work-codex
description: The owner wants work split across parallel helpers and Codex (ChatGPT) to go faster
type: feedback
source: copy of the Mac-side Claude memory (17.10.2026); Mac-only paths marked as history, login details removed
---

The owner (2026-10-14): «доверь кодексу новому чату какую то работу чтоб быстрее было», then «все таки кодекс надо
тоже занять, кодекс чат гпт». He wants independent work delegated in parallel (background agents / workflows) and,
if available, Codex (OpenAI, through his ChatGPT login) kept busy too. He cancels helpers he finds useless
(«это ненадо»), so give each helper a clearly useful job and tell him what each one does.

**Why:** speed; he pays attention to throughput, not just correctness.

**How to apply:**
- Helpers write only into their own folder, never touch the running simulator, never start VMs/WSL processes
  that compete with a trial, never push.
- Prefer read-only reviews and independent second opinions (skeptic role) for every new launcher, pin file,
  candidate or criterion; verify their findings before acting.
- Never let any helper touch a real drone, push, publish, or change PX4 parameters
  ([[never-arm-motors]], [[flight-work-plan]]).
- Codex: on the Mac it was the CLI inside ChatGPT.app (history; that path does not exist on the PC). On the PC
  Codex is NOT installed. Installing it and logging in is the owner's decision and his action; ask him once
  when parallel reviews would help. Usage pattern that worked: `codex exec -C <dir> -s read-only -o <out.md>
  "<task>"`, in its own git worktree so it never collides with your checkout.
