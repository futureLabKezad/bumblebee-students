# 🎛️ Ground Control Station — Source Code

Source code of the Bumblebee GCS desktop apps. Ready-to-run builds of **Bumblebee GCS 1.1.0** are on the GitHub release [gcs-v1.1.0](https://github.com/futureLabKezad/bumblebee-students/releases/tag/gcs-v1.1.0) — see [Ground Control Station](https://github.com/futureLabKezad/bumblebee-students/wiki/Ground‐Control‐Station) in the wiki:

- **Mac** — `BumblebeeGCS-1.1.0-mac.dmg` (universal: Apple Silicon and Intel, macOS 14+). Drag the app to Applications; on first launch use System Settings → Privacy & Security → *Open Anyway*. Allow Location when asked: without it macOS hides Wi-Fi names from the app.
- **Windows** — `BumblebeeGCS-1.1.0-windows-x64.zip` (Windows 10/11 x64, self-contained). Unzip and run `BumblebeeGcs.exe`; allow Location for Wi-Fi scanning.

Drones on the network are listed automatically by name (Bonjour `_bumblebee._tcp`); **Add drone** sets a new drone up over its `Bumblebee-XXXX` hotspot and sends it your Wi-Fi. Battery shows "—": PX4 battery measurement is off (`BAT1_SOURCE = -1`, see `PX4_parameters/`).

| Folder | Platform | Stack | Build |
| --- | --- | --- | --- |
| `macos/` | macOS 14+ (Apple Silicon and Intel) | Swift 5.9 / SwiftUI | `./build_app.sh` → `build/Bumblebee GCS.app` (universal); `./make_dmg.sh` → `build/BumblebeeGCS-<ver>-mac.dmg` |
| `windows/` | Windows 10/11 x64 | C# / .NET 10 / WinUI 3 | `dotnet publish src\BumblebeeGcs\BumblebeeGcs.csproj -c Release -r win-x64 --self-contained true -o publish\BumblebeeGCS` (on Windows) |

**Ready-to-run downloads, nothing to build.** CI (`.github/workflows/ci.yml`) builds
both apps on every push and keeps them as workflow artifacts (`BumblebeeGCS-mac`:
the `.dmg`; `BumblebeeGCS-windows`: a self-contained `.zip`, no .NET needed). Pushing
a tag `gcs-v<version>` (e.g. `gcs-v1.1.0`) also publishes them on a GitHub Release.
Each download carries a short "How to open" note: the apps are not signed with a paid
Apple/Microsoft certificate, so the first launch shows a one-time system warning.

`windows/tools/SimDrone` is a mock drone on localhost for testing the GCS without hardware (`dotnet run --project tools\SimDrone`, then connect to `localhost`).

## Checks without a drone

**The apps only watch the drone.** They subscribe to telemetry and call a fixed set of drone endpoints (Wi-Fi, lights, sounds); they never arm, change modes, send setpoints or write PX4 parameters. `tools/check_watch_only.py` enforces this in CI (`.github/workflows/gcs-checks.yml`): any other rosbridge op, a MAVROS command/parameter/setpoint name, or a REST path missing from its reviewed list fails the build.

| Tool | What it is for | Run |
| --- | --- | --- |
| `tools/check_watch_only.py` | the rule above | `python3 gcs/tools/check_watch_only.py` (tests: `test_check_watch_only.py`) |
| `tools/mock_drone.py` | the drone's real REST backend with faked hardware, plus a rosbridge stub; flight-controller states `--fcu disarmed\|armed\|stale\|lost`, `--telemetry freeze`, `--battery low`, switchable at run time on `127.0.0.1:8799` (see its docstring) | `pip install 'tornado==6.4' bcrypt`, then `python3 gcs/tools/mock_drone.py --host 127.0.0.1` (tests: `test_mock_drone.py`) |
| `windows/tools/mac_compile_check.py` | compiles the Windows app's C# on a Mac or Linux (XAML parts stubbed); catches C# errors early, does not replace the Windows build | `python3 gcs/windows/tools/mac_compile_check.py` (.NET 10 SDK) |
