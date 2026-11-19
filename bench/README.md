# Bench check kit r17b for the drone 20EC (Windows PC + real drone)

`bench_kit_r17b/` is the PC-side check kit used with the real drone 20EC (2026-11-19).
Every launcher (`NN_*.cmd`) says on its first line whether it only reads
(«ТОЛЬКО ЧТЕНИЕ») or changes the drone («МЕНЯЕТ ДРОН»), checks the PC name and the
drone's hostname, and refuses to overwrite files. It never arms the drone and never
writes PX4 parameters; passwords and sudo are typed by the owner.

- The kit is tied to one setup: PC `DESKTOP-H5CPN8E`, drone `bumblebee-20ec`
  (10.255.254.26). For another drone or PC it refuses by design; a version for that
  drone is needed.
- Not published here: `out/` (reports of runs on the drone) and `proverka_*`
  (test-run outputs). They are not in `SHA256SUMS.txt`; check the kit with
  `sha256sum -c SHA256SUMS.txt` inside `bench_kit_r17b/`.
- What changed between kit versions: `DIFF_*.txt` and `README_r*.md` (in Russian).
- r17b = r17a + the owner's approved `COM_RC_OVERRIDE 3` in `params_check/approved_changes.txt`.
