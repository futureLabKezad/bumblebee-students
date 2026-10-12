# ⚙️ PX4 Parameters

Exported PX4 parameter snapshots for the Bumblebee drone (`.params` files, loadable in QGroundControl).

| File | Notes |
| --- | --- |
| `px4_v0_0_1.params` | First parameter snapshot |
| `px4_v0_0_2.params` | Current snapshot |

Battery measurement is off in both snapshots (`BAT1_SOURCE = -1`): PX4 does not measure the battery, so the GCS shows "—" for it.

## Restoring parameters

In **QGroundControl**: *Vehicle Setup → Parameters → Tools → Load from File* → pick the `.params` file. Reboot the flight controller afterwards.

Always restore a snapshot after flashing new PX4 firmware — flashing erases tuning. Details:
👉 **[PX4 Params Backup — Bumblebee Students Wiki](https://github.com/futureLabKezad/bumblebee-students/wiki/PX4‐Params‐Backup)**
