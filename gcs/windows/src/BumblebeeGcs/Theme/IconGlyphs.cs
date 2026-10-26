// Copyright 2026 FutureLab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

namespace BumblebeeGcs.Theme;

/// <summary>
/// SF Symbols -> Segoe Fluent Icons mapping. The only place glyphs live;
/// names mirror the icon role in the mac version.
/// </summary>
public static class IconGlyphs
{
    public const string Dashboard     = "\uEC4A"; // gauge -> SpeedHigh
    public const string Entertainment = "\uEC4F"; // music.note -> MusicNote
    public const string Wifi          = "\uE701"; // wifi
    public const string Reconnect     = "\uE895"; // arrow.triangle.2.circlepath -> Sync
    public const string Rescan        = "\uE704"; // dot.radiowaves.left.and.right -> InternetSharing
    public const string Refresh       = "\uE72C"; // arrow.clockwise -> Refresh
    public const string Power         = "\uE7E8"; // power -> PowerButton
    public const string Flip          = "\uE7AD"; // camera flip -> Rotate
    public const string Mode          = "\uE709"; // airplane
    public const string Armed         = "\uE945"; // bolt.fill -> LightningBolt
    public const string Disarmed      = "\uE945"; // bolt.slash - differs by color
    public const string Battery       = "\uE859"; // battery.75 -> Battery8
    public const string BatteryUnknown = "\uE996"; // battery not measured / no data -> BatteryUnknown
    public const string Unknown       = "\uE9CE"; // questionmark -> Unknown
    public const string Pilot         = "\uE7FC"; // gamecontroller.fill -> Game
    public const string Flag          = "\uE7C1"; // flag.fill -> Flag
    public const string Altitude      = "\uE74A"; // arrow.up.to.line -> Up
    public const string Link          = "\uE701"; // dot.radiowaves.up.forward -> Wifi
    public const string Attitude      = "\uE7AD"; // gyroscope -> Rotate
    public const string Telemetry     = "\uE707"; // location.fill -> MapPin
    public const string FlightData    = "\uEC4A"; // speedometer -> SpeedHigh
    public const string Cpu           = "\uE950"; // cpu -> Component
    public const string Charts        = "\uE9D2"; // chart.xyaxis.line -> AreaChart
    public const string Map           = "\uE909"; // map -> World
    public const string Messages      = "\uE8FD"; // list.bullet.rectangle -> BulletedList
    public const string LedColor      = "\uE790"; // paintpalette -> Color
    public const string Sparkles      = "\uE793"; // sparkles -> Light
    public const string Speaker       = "\uE767"; // speaker.wave.2.fill -> Volume
    public const string Tts           = "\uE8BD"; // text.bubble -> Message
    public const string Antenna       = "\uE704"; // antenna.radiowaves.left.and.right
    public const string Bookmark      = "\uE74E"; // bookmark.fill -> Save
    public const string Add           = "\uE710"; // plus.circle -> Add
    public const string Key           = "\uE8D7"; // key -> Permissions
    public const string Lock          = "\uE72E"; // lock.fill -> Lock
    public const string Unlock        = "\uE785"; // lock.open -> Unlock
    public const string ChevronRight  = "\uE76C"; // chevron.right
    public const string LocationOff   = "\uE81D"; // location.slash -> Location (text explains)
    public const string Info          = "\uE946"; // info.circle
    public const string Success       = "\uE930"; // checkmark.circle -> Completed
    public const string Caution       = "\uE7BA"; // exclamationmark.triangle -> Warning
    public const string Error         = "\uE783"; // xmark.octagon -> Error
}
