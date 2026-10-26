# Bumblebee GCS — Windows

Native Windows port of the macOS `bumblebee_gcs_app` (SwiftUI → WinUI 3).
Design and feature parity: the same dark glass interface, the same screens,
the same drone protocols.

**Ready-to-run build (1.2.0):** `BumblebeeGCS-1.2.0-windows-x64.zip` on the GitHub release
[gcs-v1.2.0](https://github.com/futureLabKezad/bumblebee-students/releases/tag/gcs-v1.2.0) —
Windows 10/11 x64, self-contained (no .NET needed). Unzip, run `BumblebeeGcs.exe`
(if SmartScreen warns: *More info* → *Run anyway*, once) and allow Location
(Settings → Privacy & security → Location) so the app can scan Wi-Fi and find new drones.
Built by CI (`.github/workflows/ci.yml`).

## Stack

- **WinUI 3** (Windows App SDK 1.7), C# / .NET 10, unpackaged + self-contained
- Acrylic (`AcrylicBrush`) instead of `ultraThinMaterial`, Segoe Fluent Icons instead of SF Symbols
- Attitude indicator / charts / position map — XAML shapes with transforms
- `ClientWebSocket` — rosbridge `:9090`; `HttpClient` — MJPEG `:8080`, metrics `:8888`, API `:8765`
- DNS-SD (`DeviceWatcher`, `_bumblebee._tcp`) + subnet scan on `:9090` — drone discovery
- `ManagedNativeWifi` (wlanapi) — air scan and the "Add drone" hand-off via the drone's
  `Bumblebee-XXXX` hotspot (password `12345678`, drone at `10.42.0.1`): sends the PC's
  Wi-Fi to the drone and shows why a join failed
  (Windows 11 requires location services enabled for WiFi scanning)
- `PasswordVault` — WiFi provisioning password; `%LOCALAPPDATA%\BumblebeeGCS\settings.json` — lastHost/fleet

## Build and run

```powershell
# build
dotnet build src\BumblebeeGcs\BumblebeeGcs.csproj -c Release

# run
src\BumblebeeGcs\bin\x64\Release\net10.0-windows10.0.22621.0\win-x64\BumblebeeGcs.exe

# self-contained delivery (publish folder, no SDK needed on the target machine; same as CI)
dotnet publish src\BumblebeeGcs\BumblebeeGcs.csproj -c Release -r win-x64 --self-contained true -p:Platform=x64 -o publish\BumblebeeGCS
```

## Testing without a drone — SimDrone

`tools\SimDrone` emulates a drone on localhost: rosbridge telemetry (circular flight,
battery drain), Raspberry Pi metrics, `/api/*` (LED/sounds/wifi) and a synthetic MJPEG stream.

```powershell
dotnet run --project tools\SimDrone
# then enter the host in the GCS:  localhost
```

Test hook: `BumblebeeGcs.exe --connect localhost` connects right away, skipping the selection screen.

## Unit and socket tests (any OS with the .NET 10 SDK)

```powershell
dotnet test tests\BumblebeeGcs.Logic.Tests            # ~30 s
python3 tools/mac_compile_check.py                     # on a Mac/Linux: compiles all app C# (no XAML)
```

`Logic\` holds every decision the dashboard makes (link state, freshness, armed, mode
text, who is in control, battery, charts, log, alarms, video status) without WinUI. The
test project compiles it together with `Models.cs`, `RosbridgeClient.cs` and
`MjpegStream.cs`; the socket tests run the real clients against fake servers on
127.0.0.1 (frozen drone, rosbridge without data, FC lost while armed, one video
connection per view, video back after a server restart or a half-open connection).
The rules are the same as in the Mac app (`gcs/macos/Sources/GCSApp/TelemetryLogic.swift`).

## Structure

```
src\BumblebeeGcs\
  Theme\      Palette/ConnectPalette (colors 1:1 with mac), Fonts, IconGlyphs, UI factories
  Logic\      dashboard decisions without WinUI (unit-tested): LinkLogic, Freshness, ArmedLogic,
              ModeLogic, BatteryLogic, MessageLog, RosMessages, DisplayMath
  Models\     TelemetryStore, SystemMetrics, KnownDrone, QuatToEuler
  Services\   RosbridgeClient, MjpegStream, MetricsClient, DroneApi,
              DroneScanner (+DnssdBrowser), WifiHandoff, AppSettings,
              CredentialStore, KeepAwake, AppState
  Controls\   PanelCard, StatTile, StatusDot, LabeledBar, chips/bars/fields,
              AttitudeView, ChartView, PositionMapView, CameraView, AdaptiveGridPanel
  Views\      Splash, Launch, ProvisioningDialog, MainShell, Dashboard,
              Entertainment, Settings
tools\SimDrone\   drone mock for end-to-end testing
tests\BumblebeeGcs.Logic.Tests\   unit + socket tests (dotnet test)
```

Hotkeys: `Ctrl+R` Reconnect · `Ctrl+K` Rescan · `Ctrl+Shift+D` Disconnect.
