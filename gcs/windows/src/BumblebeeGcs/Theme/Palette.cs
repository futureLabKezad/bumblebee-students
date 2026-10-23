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

using Microsoft.UI;
using Microsoft.UI.Xaml.Media;
using Windows.UI;

namespace BumblebeeGcs.Theme;

/// <summary>
/// Порт `Theme` из Models.swift — единый источник цветов/отступов/радиусов.
/// Цвета совпадают с mac-версией и веб-дашбордом 1:1.
/// </summary>
public static class Palette
{
    // Surfaces
    public static readonly Color Bg            = Hex(0x0a0c10);
    public static readonly Color BgDeep        = Hex(0x10141d);
    public static readonly Color Surface       = Hex(0x111318);
    public static readonly Color SurfaceRaised = Hex(0x161a22);
    public static readonly Color Border        = Hex(0x232a39);
    public static readonly Color Hairline      = Hex(0x1a2030);

    // Accents / status
    public static readonly Color Accent  = Hex(0xf5c842);
    public static readonly Color Accent2 = Hex(0x3b82f6);
    public static readonly Color Ok      = Hex(0x22c55e);
    public static readonly Color Warn    = Hex(0xf97316);
    public static readonly Color Danger  = Hex(0xef4444);
    public static readonly Color Text    = Hex(0xe2e8f0);
    public static readonly Color Muted   = Hex(0x64748b);

    // Accent semantics
    public static readonly Color Primary = Accent2;
    public static readonly Color Caution = Accent;
    public static readonly Color SelectionBg = WithAlpha(Accent2, 0.18);
    public static readonly Color HoverBg     = WithAlpha(Accent2, 0.10);

    // Categorical data palette
    public static readonly Color DataBlue   = Accent2;
    public static readonly Color DataTeal   = Hex(0x06b6d4);
    public static readonly Color DataGreen  = Ok;
    public static readonly Color DataOrange = Warn;

    // Spacing scale
    public const double S0 = 2, S1 = 4, S2 = 8, S3 = 12, S4 = 16, S5 = 24, S6 = 32, S7 = 40;

    // Corner radii
    public const double RSmall = 4, RMedia = 6, RControl = 8, RPanel = 10, RLogo = 18;

    // Icon sizes
    public const double IconSm = 11, IconMd = 15, IconLg = 18, IconXl = 22;

    // Opacity / glass tokens
    public static readonly Color EdgeHi      = WithAlpha(Colors.White, 0.22);
    public static readonly Color EdgeLo      = WithAlpha(Colors.White, 0.04);
    public static readonly Color GhostStroke = WithAlpha(Colors.White, 0.10);
    public static readonly Color FillFaint   = WithAlpha(Colors.White, 0.06);
    public static readonly Color Scrim       = WithAlpha(Colors.Black, 0.4);
    public static readonly Color GridLine    = WithAlpha(Hex(0x232a39), 0.5);
    public static readonly Color AxisLine    = WithAlpha(Hex(0x64748b), 0.6);

    // Elevation
    public static readonly Color ShadowColor = WithAlpha(Colors.Black, 0.3);
    public const double ShadowRadius = 8, ShadowY = 3;

    public static Color Hex(uint hex) => Color.FromArgb(
        0xFF, (byte)((hex >> 16) & 0xff), (byte)((hex >> 8) & 0xff), (byte)(hex & 0xff));

    public static Color WithAlpha(Color c, double a) =>
        Color.FromArgb((byte)(a * 255 + 0.5), c.R, c.G, c.B);

    public static SolidColorBrush Brush(Color c) => new(c);

    /// <summary>Colour of a logic Tone (BumblebeeGcs.Logic has no UI types).</summary>
    public static Color ForTone(Logic.Tone t) => t switch
    {
        Logic.Tone.Primary => Primary,
        Logic.Tone.Ok => Ok,
        Logic.Tone.Caution => Caution,
        Logic.Tone.Warn => Warn,
        Logic.Tone.Danger => Danger,
        _ => Muted,
    };

    /// <summary>Канонический фон приложения — вертикальный градиент bg → bgDeep.</summary>
    public static LinearGradientBrush AppGradient() => new()
    {
        StartPoint = new Windows.Foundation.Point(0.5, 0),
        EndPoint = new Windows.Foundation.Point(0.5, 1),
        GradientStops =
        {
            new GradientStop { Color = Bg, Offset = 0 },
            new GradientStop { Color = BgDeep, Offset = 1 },
        },
    };

    /// <summary>Градиентная обводка glass-карточки: ярче сверху.</summary>
    public static LinearGradientBrush EdgeStroke() => new()
    {
        StartPoint = new Windows.Foundation.Point(0.5, 0),
        EndPoint = new Windows.Foundation.Point(0.5, 1),
        GradientStops =
        {
            new GradientStop { Color = EdgeHi, Offset = 0 },
            new GradientStop { Color = EdgeLo, Offset = 1 },
        },
    };
}

/// <summary>
/// Порт `ConnectTheme` — палитра стартовых экранов (splash + connect + setup).
/// </summary>
public static class ConnectPalette
{
    public static readonly Color Bg        = Palette.Hex(0x0b0d12);
    public static readonly Color BgGlow    = Palette.Hex(0x131722);
    public static readonly Color Text      = Palette.Hex(0xe6ebf2);
    public static readonly Color Orange    = Palette.Hex(0xff9d1a);
    public static readonly Color Blue      = Palette.Hex(0x2f81f7);
    public static readonly Color BlueHover = Palette.Hex(0x4c92ff);
    public static readonly Color BlueSoft  = Palette.Hex(0x7fb0ff);
    public static readonly Color Green     = Palette.Hex(0x35d07f);
    public static readonly Color Muted     = Palette.Hex(0x7c8494);
    public static readonly Color Muted2    = Palette.Hex(0x8b93a2);
    public static readonly Color Faint     = Palette.Hex(0x535b6a);
    public static readonly Color Hairline  = Palette.WithAlpha(Colors.White, 0.08);
    public static readonly Color RowBg     = Palette.WithAlpha(Colors.White, 0.02);

    /// <summary>radial-gradient(130% 100% at 50% -10%, #131722 0%, #0b0d12 60%)</summary>
    public static RadialGradientBrush Background() => new()
    {
        Center = new Windows.Foundation.Point(0.5, -0.1),
        GradientOrigin = new Windows.Foundation.Point(0.5, -0.1),
        RadiusX = 1.3,
        RadiusY = 1.0,
        GradientStops =
        {
            new GradientStop { Color = BgGlow, Offset = 0 },
            new GradientStop { Color = Bg, Offset = 0.6 },
        },
    };
}
