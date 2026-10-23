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
using System.Numerics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.UI;

namespace BumblebeeGcs.Theme;

/// <summary>Фабрики примитивов — компактный SwiftUI-подобный слой поверх WinUI.</summary>
public static class Ui
{
    public static readonly FontFamily IconFont = new("Segoe Fluent Icons,Segoe MDL2 Assets");

    public static TextBlock Text(string text, FontSpec f, Color color, double tracking = 0)
    {
        var tb = new TextBlock
        {
            Text = text,
            FontSize = f.Size,
            FontWeight = f.Weight,
            FontFamily = f.Family,
            Foreground = Palette.Brush(color),
            VerticalAlignment = VerticalAlignment.Center,
        };
        if (tracking > 0) tb.CharacterSpacing = (int)(tracking / f.Size * 1000);
        return tb;
    }

    public static FontIcon Icon(string glyph, double size, Color color) => new()
    {
        Glyph = glyph,
        FontSize = size,
        Foreground = Palette.Brush(color),
        FontFamily = IconFont,
        VerticalAlignment = VerticalAlignment.Center,
    };

    public static StackPanel VStack(double spacing, params UIElement[] children)
    {
        var sp = new StackPanel { Orientation = Orientation.Vertical, Spacing = spacing };
        foreach (var c in children) sp.Children.Add(c);
        return sp;
    }

    public static StackPanel HStack(double spacing, params UIElement[] children)
    {
        var sp = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = spacing,
        };
        foreach (var c in children) sp.Children.Add(c);
        return sp;
    }

    /// <summary>Строка «слева — контент, справа — контент», середина растягивается (аналог Spacer()).</summary>
    public static Grid SpaceBetween(UIElement left, UIElement right, double gap = 8)
    {
        var g = new Grid { ColumnSpacing = gap };
        g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        Grid.SetColumn((FrameworkElement)left, 0);
        Grid.SetColumn((FrameworkElement)right, 1);
        ((FrameworkElement)left).HorizontalAlignment = HorizontalAlignment.Left;
        ((FrameworkElement)left).VerticalAlignment = VerticalAlignment.Center;
        ((FrameworkElement)right).VerticalAlignment = VerticalAlignment.Center;
        g.Children.Add(left);
        g.Children.Add(right);
        return g;
    }

    public static void OnHover(UIElement e, Action<bool> set)
    {
        e.PointerEntered += (_, _) => set(true);
        e.PointerExited += (_, _) => set(false);
    }

    public static void OnTap(UIElement e, Action action)
    {
        e.Tapped += (_, _) => action();
    }

    /// <summary>Скругляет и клипует содержимое элемента (WinUI Border не клипует детей).</summary>
    public static void ClipRounded(FrameworkElement e, float radius)
    {
        void Update()
        {
            if (e.ActualWidth <= 0 || e.ActualHeight <= 0) return;
            var v = ElementCompositionPreview.GetElementVisual(e);
            var c = v.Compositor;
            var geo = c.CreateRoundedRectangleGeometry();
            geo.Size = new Vector2((float)e.ActualWidth, (float)e.ActualHeight);
            geo.CornerRadius = new Vector2(radius);
            v.Clip = c.CreateGeometricClip(geo);
        }
        e.SizeChanged += (_, _) => Update();
        e.Loaded += (_, _) => Update();
    }

    /// <summary>Логотип приложения (Assets/AppIcon.png) со скруглением.</summary>
    public static FrameworkElement AppLogo(double size, double radius)
    {
        var img = new Image
        {
            Source = new BitmapImage(new Uri(Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.png"))),
            Width = size,
            Height = size,
            Stretch = Stretch.UniformToFill,
        };
        var host = new Border { Width = size, Height = size, Child = img, CornerRadius = new CornerRadius(radius) };
        ClipRounded(host, (float)radius);
        return host;
    }

    // MARK: - Glass surface (порт glassCard из Components.swift)

    public static Brush GlassBrush() => new AcrylicBrush
    {
        TintColor = Palette.Surface,
        TintOpacity = 0.5,
        TintLuminosityOpacity = 0.75,
        FallbackColor = Palette.SurfaceRaised,
    };

    /// <summary>Матовая поверхность с градиентной кромкой (ярче сверху) — Liquid Glass.</summary>
    public static Border GlassCard(UIElement content, double radius, Thickness padding = default)
    {
        return new Border
        {
            Background = GlassBrush(),
            BorderBrush = Palette.EdgeStroke(),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(radius),
            Padding = padding,
            Child = content,
        };
    }

    // MARK: - Buttons (порт AccentButtonStyle / GhostButtonStyle)

    static void OverrideButtonBrushes(Button b, Color bg, Color bgHover, Color bgPressed,
                                      Color fg, Color? border = null)
    {
        b.Resources["ButtonBackground"] = Palette.Brush(bg);
        b.Resources["ButtonBackgroundPointerOver"] = Palette.Brush(bgHover);
        b.Resources["ButtonBackgroundPressed"] = Palette.Brush(bgPressed);
        b.Resources["ButtonBackgroundDisabled"] = Palette.Brush(Palette.WithAlpha(bg, 0.4));
        b.Resources["ButtonForeground"] = Palette.Brush(fg);
        b.Resources["ButtonForegroundPointerOver"] = Palette.Brush(fg);
        b.Resources["ButtonForegroundPressed"] = Palette.Brush(Palette.WithAlpha(fg, 0.8));
        b.Resources["ButtonForegroundDisabled"] = Palette.Brush(Palette.Muted);
        var bc = border ?? Colors.Transparent;
        b.Resources["ButtonBorderBrush"] = Palette.Brush(bc);
        b.Resources["ButtonBorderBrushPointerOver"] = Palette.Brush(bc);
        b.Resources["ButtonBorderBrushPressed"] = Palette.Brush(bc);
        b.Resources["ButtonBorderBrushDisabled"] = Palette.Brush(Palette.WithAlpha(bc, 0.5));
    }

    public static Button AccentButton(string label, Action onClick)
    {
        var b = new Button
        {
            Content = Text(label, Fonts.Button, Colors.White),
            Padding = new Thickness(Palette.S4, Palette.S2 + 1, Palette.S4, Palette.S2 + 1),
            CornerRadius = new CornerRadius(Palette.RControl),
            BorderThickness = new Thickness(0),
        };
        OverrideButtonBrushes(b, Palette.Primary, Palette.Hex(0x4c8ff8), Palette.WithAlpha(Palette.Primary, 0.7), Colors.White);
        b.Click += (_, _) => onClick();
        return b;
    }

    public static Button GhostButton(string label, Action onClick, string? glyph = null)
    {
        UIElement content = glyph is null
            ? Text(label, Fonts.ButtonSm, Palette.Text)
            : HStack(Palette.S2, Icon(glyph, Fonts.ButtonSm.Size, Palette.Text), Text(label, Fonts.ButtonSm, Palette.Text));
        var b = new Button
        {
            Content = content,
            Padding = new Thickness(Palette.S3, Palette.S2, Palette.S3, Palette.S2),
            CornerRadius = new CornerRadius(Palette.RControl),
            BorderThickness = new Thickness(1),
        };
        OverrideButtonBrushes(b, Palette.FillFaint, Palette.WithAlpha(Colors.White, 0.10),
                              Palette.WithAlpha(Colors.White, 0.04), Palette.Text, Palette.GhostStroke);
        b.Click += (_, _) => onClick();
        return b;
    }

    /// <summary>
    /// A real Button with custom content and colours, for what used to be a tappable Border:
    /// Tab reaches it, Enter/Space press it, Narrator reads <paramref name="name"/>.
    /// </summary>
    public static Button FlatButton(UIElement content, Action onClick, string name, Color bg, Color bgHover,
                                    Color fg, Color? border = null, Thickness? padding = null, double radius = 8)
    {
        var b = new Button
        {
            Content = content,
            Padding = padding ?? new Thickness(0),
            CornerRadius = new CornerRadius(radius),
            BorderThickness = new Thickness(border is null ? 0 : 1),
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
        };
        OverrideButtonBrushes(b, bg, bgHover, bgHover, fg, border);
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(b, name);
        b.Click += (_, _) => onClick();
        return b;
    }

    /// <summary>Круглая иконко-кнопка поверх видео (scrim-фон) — оверлеи камеры.</summary>
    public static Button OverlayIconButton(string glyph, string tooltip, Action onClick)
    {
        var b = new Button
        {
            Content = Icon(glyph, Fonts.Body.Size, Palette.Text),
            Padding = new Thickness(6),
            CornerRadius = new CornerRadius(99),
            BorderThickness = new Thickness(0),
        };
        OverrideButtonBrushes(b, Palette.Scrim, Palette.WithAlpha(Colors.Black, 0.55), Palette.WithAlpha(Colors.Black, 0.7), Palette.Text);
        ToolTipService.SetToolTip(b, tooltip);
        b.Click += (_, _) => onClick();
        return b;
    }

    /// <summary>Иконко-кнопка тулбара без фона.</summary>
    public static Button ToolbarIconButton(string glyph, string tooltip, Action onClick)
    {
        var b = new Button
        {
            Content = Icon(glyph, Palette.IconMd, Palette.Text),
            Padding = new Thickness(8, 6, 8, 6),
            CornerRadius = new CornerRadius(Palette.RControl),
            BorderThickness = new Thickness(0),
        };
        OverrideButtonBrushes(b, Colors.Transparent, Palette.HoverBg, Palette.SelectionBg, Palette.Text);
        ToolTipService.SetToolTip(b, tooltip);
        b.Click += (_, _) => onClick();
        return b;
    }
}
