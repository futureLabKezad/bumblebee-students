# 🎛️ Ground Control Station — Source Code

Source code of the Bumblebee GCS desktop apps. Ready-to-run builds are on the download links — see [Ground Control Station](https://github.com/futureLabKezad/bumblebee-students/wiki/Ground‐Control‐Station) in the wiki.

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
