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
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.UI;

namespace BumblebeeGcs.Controls;

// MARK: - Panel (титулованная glass-карточка с иконкой)
// Примечание: Border в WinUI sealed, поэтому карточки наследуют Grid —
// у него есть те же Background/BorderBrush/CornerRadius/Padding.

public sealed class PanelCard : Grid
{
    public readonly StackPanel Content;
    private readonly TextBlock _note;

    public PanelCard(string title, string? glyph = null, params UIElement[] rows)
    {
        var titleRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = Palette.S2 };
        if (glyph is not null)
            titleRow.Children.Add(Ui.Icon(glyph, Palette.IconSm, Palette.Muted));
        titleRow.Children.Add(Ui.Text(title.ToUpperInvariant(), Fonts.SectionLbl, Palette.Muted, tracking: 1.1));
        // Справа в заголовке — «no data N s», когда источник панели устарел.
        _note = Ui.Text("", Fonts.SectionLbl, Palette.Caution);
        var header = Ui.SpaceBetween(titleRow, _note);

        Content = new StackPanel { Orientation = Orientation.Vertical, Spacing = Palette.S3 };
        Content.Children.Add(header);
        foreach (var r in rows) Content.Children.Add(r);

        Background = Ui.GlassBrush();
        BorderBrush = Palette.EdgeStroke();
        BorderThickness = new Thickness(1);
        CornerRadius = new CornerRadius(Palette.RPanel);
        Padding = new Thickness(Palette.S4);
        HorizontalAlignment = HorizontalAlignment.Stretch;
        Children.Add(Content);
    }

    public void Add(UIElement row) => Content.Children.Add(row);

    /// <summary>Header note ("no data 7 s"); null hides it.</summary>
    public void SetNote(string? note) => _note.Text = note ?? "";
}

/// <summary>
/// Persistent red strip for a safety alarm ("Flight controller link lost", low battery), as the
/// Mac app's AlarmBanner: solid danger colour, not dismissable, stays until the condition clears.
/// </summary>
public sealed class AlarmBanner : Grid
{
    private readonly TextBlock _text;

    public AlarmBanner(string glyph)
    {
        var icon = Ui.Icon(glyph, Palette.IconMd, Colors.White);
        _text = Ui.Text("", Fonts.BodyStrong, Colors.White);
        _text.TextWrapping = TextWrapping.Wrap;
        _text.VerticalAlignment = VerticalAlignment.Center;
        icon.VerticalAlignment = VerticalAlignment.Center;
        Background = Palette.Brush(Palette.Danger);
        Padding = new Thickness(Palette.S4, Palette.S2 + 2, Palette.S4, Palette.S2 + 2);
        HorizontalAlignment = HorizontalAlignment.Stretch;
        Children.Add(Ui.HStack(Palette.S2, icon, _text));
        Visibility = Visibility.Collapsed;
    }

    /// <summary>Show the text, or hide the banner for null.</summary>
    public void Set(string? text)
    {
        if (text is null)
        {
            Visibility = Visibility.Collapsed;
            return;
        }
        _text.Text = text;
        Visibility = Visibility.Visible;
    }
}

/// <summary>Серый вид устаревших данных: панель/строка остаётся, но явно «не живая».</summary>
public static class Stale
{
    public const double DimOpacity = 0.4;

    public static void Dim(UIElement e, bool dim) => e.Opacity = dim ? DimOpacity : 1;
}

// MARK: - StatTile (hero-плитка)

public sealed class StatTile : Grid
{
    private readonly Border _iconBox;
    private readonly FontIcon _icon;
    private readonly TextBlock _value;
    private readonly TextBlock _caption;
    private Color _color;

    public StatTile(string label, string glyph, Color color)
    {
        _color = color;
        _icon = Ui.Icon(glyph, Palette.IconMd, color);
        _icon.HorizontalAlignment = HorizontalAlignment.Center;
        _iconBox = new Border
        {
            Width = 34,
            Height = 34,
            CornerRadius = new CornerRadius(Palette.RControl),
            Background = Palette.Brush(Palette.WithAlpha(color, 0.15)),
            Child = _icon,
            VerticalAlignment = VerticalAlignment.Center,
        };
        _value = Ui.Text("—", Fonts.StatValue, Palette.Text);
        _value.TextWrapping = TextWrapping.WrapWholeWords;
        _value.MaxLines = 2;
        // Короткое пояснение под значением (режим, «waiting for FC data», «no data N s»).
        _caption = Ui.Text(" ", Fonts.MonoSmall, Palette.Muted);
        _caption.TextTrimming = TextTrimming.CharacterEllipsis;
        _caption.MaxLines = 1;

        var texts = Ui.VStack(Palette.S0 - 1,
            Ui.Text(label.ToUpperInvariant(), Fonts.SectionLbl, Palette.Muted, tracking: 0.8),
            _value, _caption);
        texts.VerticalAlignment = VerticalAlignment.Center;

        Background = Ui.GlassBrush();
        BorderBrush = Palette.EdgeStroke();
        BorderThickness = new Thickness(1);
        CornerRadius = new CornerRadius(Palette.RPanel);
        Padding = new Thickness(Palette.S3, Palette.S2 + 2, Palette.S3, Palette.S2 + 2);
        Children.Add(Ui.HStack(Palette.S3, _iconBox, texts));
    }

    /// <param name="valueColor">Colour of the value text (UNKNOWN in caution, "ARMED? link lost" in danger); default text.</param>
    public void Update(string value, Color? color = null, string? glyph = null, Color? valueColor = null)
    {
        _value.Text = value;
        _value.Foreground = Palette.Brush(valueColor ?? Palette.Text);
        // Длинные значения («Telemetry frozen», «Not measured») мельче, чтобы влезть в 190 px.
        _value.FontSize = value.Length > 10 ? Fonts.StatValue.Size - 3 : Fonts.StatValue.Size;
        if (color is Color c && c != _color)
        {
            _color = c;
            _icon.Foreground = Palette.Brush(c);
            _iconBox.Background = Palette.Brush(Palette.WithAlpha(c, 0.15));
        }
        if (glyph is not null && _icon.Glyph != glyph) _icon.Glyph = glyph;
    }

    /// <summary>Small line under the value; tone colour (e.g. caution for "no data N s").</summary>
    public void SetCaption(string caption, Color? color = null)
    {
        _caption.Text = caption.Length > 0 ? caption : " ";
        _caption.Foreground = Palette.Brush(color ?? Palette.Muted);
        ToolTipService.SetToolTip(this, caption.Length > 0 ? caption : null);
    }

    /// <summary>Stale source: the tile greys out (the caption says how old).</summary>
    public void SetDimmed(bool dim)
    {
        var o = dim ? Stale.DimOpacity : 1;
        _value.Opacity = o;
        _iconBox.Opacity = o;
    }
}

// MARK: - Status dot (с пульсацией)

public sealed class StatusDot : Grid
{
    private readonly Ellipse _dot;
    private readonly Ellipse _ring;
    private bool _pulsing;

    public StatusDot(Color color, bool pulsing = false, double size = 8)
    {
        Width = size + 12;
        Height = size + 12;
        _ring = new Ellipse
        {
            Width = size,
            Height = size,
            Stroke = Palette.Brush(Palette.WithAlpha(color, 0.35)),
            StrokeThickness = 3,
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            Opacity = 0,
        };
        _dot = new Ellipse
        {
            Width = size,
            Height = size,
            Fill = Palette.Brush(color),
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
        };
        Children.Add(_ring);
        Children.Add(_dot);
        SetPulsing(pulsing);
    }

    public void SetColor(Color color)
    {
        _dot.Fill = Palette.Brush(color);
        _ring.Stroke = Palette.Brush(Palette.WithAlpha(color, 0.35));
    }

    public void SetPulsing(bool pulsing)
    {
        if (_pulsing == pulsing) return;
        _pulsing = pulsing;
        var v = ElementCompositionPreview.GetElementVisual(_ring);
        if (pulsing)
        {
            _ring.Opacity = 1;
            var c = v.Compositor;
            var scale = c.CreateVector3KeyFrameAnimation();
            scale.InsertKeyFrame(0f, Vector3.One);
            scale.InsertKeyFrame(0.5f, new Vector3(2.2f, 2.2f, 1f));
            scale.InsertKeyFrame(1f, Vector3.One);
            scale.Duration = TimeSpan.FromSeconds(2);
            scale.IterationBehavior = Microsoft.UI.Composition.AnimationIterationBehavior.Forever;
            v.CenterPoint = new Vector3((float)_ring.Width / 2, (float)_ring.Height / 2, 0);
            v.StartAnimation("Scale", scale);

            var fade = c.CreateScalarKeyFrameAnimation();
            fade.InsertKeyFrame(0f, 0.9f);
            fade.InsertKeyFrame(0.5f, 0.1f);
            fade.InsertKeyFrame(1f, 0.9f);
            fade.Duration = TimeSpan.FromSeconds(2);
            fade.IterationBehavior = Microsoft.UI.Composition.AnimationIterationBehavior.Forever;
            v.StartAnimation("Opacity", fade);
        }
        else
        {
            v.StopAnimation("Scale");
            v.StopAnimation("Opacity");
            v.Scale = Vector3.One;
            v.Opacity = 1;
            _ring.Opacity = 0;
        }
    }
}

// MARK: - Readouts & bars

public sealed class ReadoutRow : Grid
{
    private readonly TextBlock _value;

    public ReadoutRow(string label, Color? valueColor = null)
    {
        _value = Ui.Text("—", Fonts.Value, valueColor ?? Palette.Text);
        var g = Ui.SpaceBetween(Ui.Text(label, Fonts.MonoSmall, Palette.Muted), _value);
        Children.Add(g);
    }

    public void Set(string value) => _value.Text = value;
    public void Set(string value, Color color)
    {
        _value.Text = value;
        _value.Foreground = Palette.Brush(color);
    }
}

public sealed class LabeledBarRow : StackPanel
{
    private readonly TextBlock _value;
    private readonly Rectangle _fill;
    private readonly Grid _track;
    private double _pct;
    private Color _color;

    public LabeledBarRow(string label, Color color)
    {
        Orientation = Orientation.Vertical;
        Spacing = Palette.S1;
        _color = color;
        _value = Ui.Text("—", Fonts.MonoSmall, Palette.Text);
        Children.Add(Ui.SpaceBetween(Ui.Text(label, Fonts.MonoSmall, Palette.Muted), _value));

        _fill = new Rectangle
        {
            RadiusX = 3, RadiusY = 3,
            Fill = Palette.Brush(color),
            HorizontalAlignment = HorizontalAlignment.Left,
            Height = 6,
        };
        _track = new Grid { Height = 6 };
        _track.Children.Add(new Rectangle { RadiusX = 3, RadiusY = 3, Fill = Palette.Brush(Palette.Hairline) });
        _track.Children.Add(_fill);
        _track.SizeChanged += (_, _) => Layout();
        Children.Add(_track);
    }

    public void Set(string value, double pct, Color? color = null)
    {
        _value.Text = value;
        _pct = Math.Max(0, Math.Min(100, pct));
        if (color is Color c && c != _color)
        {
            _color = c;
            _fill.Fill = Palette.Brush(c);
        }
        Layout();
    }

    private void Layout() => _fill.Width = Math.Max(0, _track.ActualWidth * _pct / 100);
}

public static class BadgeFactory
{
    public static Border Badge(string text, Color color) => new()
    {
        Background = Palette.Brush(Palette.WithAlpha(color, 0.16)),
        CornerRadius = new CornerRadius(99),
        Padding = new Thickness(Palette.S2, Palette.S1 - 1, Palette.S2, Palette.S1 - 1),
        Child = Ui.Text(text, Fonts.Badge, color),
        VerticalAlignment = VerticalAlignment.Center,
    };
}

// MARK: - Chip button & segmented tabs

/// <summary>Чип-переключатель — синий при выборе, тусклый — нет.</summary>
public sealed class ChipButton : Button
{
    private bool _selected;
    private readonly TextBlock _label;

    public ChipButton(string label, bool selected, Action onClick, bool fullWidth = false)
    {
        _label = Ui.Text(label, Fonts.Chip, Palette.Muted);
        _label.HorizontalAlignment = HorizontalAlignment.Center;
        Content = _label;
        Padding = new Thickness(Palette.S3, Palette.S1 + 1, Palette.S3, Palette.S1 + 1);
        CornerRadius = new CornerRadius(Palette.RControl);
        BorderThickness = new Thickness(0);
        if (fullWidth) HorizontalAlignment = HorizontalAlignment.Stretch;
        HorizontalContentAlignment = HorizontalAlignment.Center;
        Click += (_, _) => onClick();
        SetSelected(selected);
    }

    public void SetSelected(bool selected)
    {
        _selected = selected;
        var bg = selected ? Palette.SelectionBg : Palette.FillFaint;
        var fg = selected ? Palette.Primary : Palette.Muted;
        Resources["ButtonBackground"] = Palette.Brush(bg);
        Resources["ButtonBackgroundPointerOver"] = Palette.Brush(selected ? Palette.SelectionBg : Palette.WithAlpha(Colors.White, 0.09));
        Resources["ButtonBackgroundPressed"] = Palette.Brush(Palette.SelectionBg);
        Resources["ButtonForeground"] = Palette.Brush(fg);
        Resources["ButtonForegroundPointerOver"] = Palette.Brush(fg);
        Resources["ButtonForegroundPressed"] = Palette.Brush(fg);
        _label.Foreground = Palette.Brush(fg);
        // Перезагрузить шаблонные кисти после смены ресурсов.
        Background = Palette.Brush(bg);
        Foreground = Palette.Brush(fg);
    }
}

/// <summary>Ряд чипов, связанный с выбором — glass-сегментед-контрол.</summary>
public sealed class SegmentedTabs : StackPanel
{
    private readonly List<(string Value, ChipButton Chip)> _chips = new();
    private string _selection;

    public event Action<string>? SelectionChanged;
    public string Selection => _selection;

    public SegmentedTabs(IEnumerable<(string Label, string Value)> options, string selection, bool fullWidth = false)
    {
        Orientation = Orientation.Horizontal;
        Spacing = Palette.S1 + 2;
        _selection = selection;
        foreach (var (label, value) in options)
        {
            var chip = new ChipButton(label, value == selection, () => Select(value), fullWidth);
            _chips.Add((value, chip));
            Children.Add(chip);
        }
    }

    public void Select(string value)
    {
        if (_selection == value) return;
        _selection = value;
        foreach (var (v, chip) in _chips) chip.SetSelected(v == value);
        SelectionChanged?.Invoke(value);
    }
}

// MARK: - Status banner

public sealed class StatusBanner : Grid
{
    public enum Kind { Info, Success, Caution, Error }

    private readonly FontIcon _icon;
    private readonly TextBlock _text;

    public StatusBanner()
    {
        _icon = Ui.Icon(IconGlyphs.Info, Palette.IconSm, Palette.Muted);
        _text = Ui.Text("", Fonts.MonoSmall, Palette.Muted);
        _text.TextWrapping = TextWrapping.Wrap;
        CornerRadius = new CornerRadius(Palette.RControl);
        Padding = new Thickness(Palette.S3, Palette.S2, Palette.S3, Palette.S2);
        HorizontalAlignment = HorizontalAlignment.Stretch;
        Children.Add(Ui.HStack(Palette.S2, _icon, _text));
        Visibility = Visibility.Collapsed;
    }

    public void Show(string text, Kind kind)
    {
        var (color, glyph) = kind switch
        {
            Kind.Success => (Palette.Ok, IconGlyphs.Success),
            Kind.Caution => (Palette.Caution, IconGlyphs.Caution),
            Kind.Error => (Palette.Danger, IconGlyphs.Error),
            _ => (Palette.Muted, IconGlyphs.Info),
        };
        _icon.Glyph = glyph;
        _icon.Foreground = Palette.Brush(color);
        _text.Text = text;
        _text.Foreground = Palette.Brush(color);
        Background = Palette.Brush(Palette.WithAlpha(color, 0.12));
        Visibility = Visibility.Visible;
    }

    public void Hide() => Visibility = Visibility.Collapsed;
}

// MARK: - Glass input field

/// <summary>Единый матовый текст-инпут (замена stock-стилей), опционально secure.</summary>
public sealed class GlassTextField : Grid
{
    private readonly TextBox? _box;
    private readonly PasswordBox? _pwd;

    public event Action? Submitted;
    public event Action? TextChanged;

    public GlassTextField(string placeholder, string? glyph = null, bool secure = false)
    {
        Background = Ui.GlassBrush();
        BorderBrush = Palette.EdgeStroke();
        BorderThickness = new Thickness(1);
        CornerRadius = new CornerRadius(Palette.RControl);
        Padding = new Thickness(Palette.S3, Palette.S2 + 1, Palette.S3, Palette.S2 + 1);

        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = Palette.S2 };
        if (glyph is not null) row.Children.Add(Ui.Icon(glyph, Palette.IconMd, Palette.Muted));

        if (secure)
        {
            _pwd = new PasswordBox { PlaceholderText = placeholder };
            StripChrome(_pwd);
            _pwd.PasswordChanged += (_, _) => TextChanged?.Invoke();
            _pwd.KeyDown += (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) Submitted?.Invoke(); };
            row.Children.Add(_pwd);
        }
        else
        {
            _box = new TextBox { PlaceholderText = placeholder };
            StripChrome(_box);
            _box.TextChanged += (_, _) => TextChanged?.Invoke();
            _box.KeyDown += (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) Submitted?.Invoke(); };
            row.Children.Add(_box);
        }
        Children.Add(row);
    }

    public double InnerWidth
    {
        set { if (_box is not null) _box.Width = value; if (_pwd is not null) _pwd.Width = value; }
    }

    public string Text
    {
        get => _box?.Text ?? _pwd?.Password ?? "";
        set { if (_box is not null) _box.Text = value; if (_pwd is not null) _pwd.Password = value; }
    }

    /// <summary>Убрать фон/рамку у stock TextBox/PasswordBox — стиль задаёт glass-обёртка.</summary>
    private static void StripChrome(Control c)
    {
        c.FontSize = Fonts.Value.Size;
        c.FontFamily = Fonts.Value.Family;
        c.Foreground = Palette.Brush(Palette.Text);
        c.BorderThickness = new Thickness(0);
        c.Padding = new Thickness(0);
        c.MinHeight = 0;
        c.VerticalAlignment = VerticalAlignment.Center;
        foreach (var state in new[] { "", "PointerOver", "Focused", "Disabled" })
        {
            c.Resources[$"TextControlBackground{state}"] = Palette.Brush(Colors.Transparent);
            c.Resources[$"TextControlBorderBrush{state}"] = Palette.Brush(Colors.Transparent);
        }
        c.Resources["TextControlForegroundPointerOver"] = Palette.Brush(Palette.Text);
        c.Resources["TextControlForegroundFocused"] = Palette.Brush(Palette.Text);
        c.Resources["TextControlPlaceholderForeground"] = Palette.Brush(Palette.Muted);
        c.Resources["TextControlPlaceholderForegroundPointerOver"] = Palette.Brush(Palette.Muted);
        c.Resources["TextControlPlaceholderForegroundFocused"] = Palette.Brush(Palette.Muted);
    }
}

// MARK: - Hoverable row (карточки на экране подключения)

/// <summary>Кликабельная строка с hover-подсветкой фона и рамки.</summary>
public sealed class HoverRow : Grid
{
    private readonly Color _bgNormal, _bgHover, _strokeNormal, _strokeHover;

    public HoverRow(UIElement content, double radius,
                    Color bgNormal, Color bgHover, Color strokeNormal, Color strokeHover,
                    Action? onTap = null)
    {
        _bgNormal = bgNormal; _bgHover = bgHover;
        _strokeNormal = strokeNormal; _strokeHover = strokeHover;
        Background = Palette.Brush(bgNormal);
        BorderBrush = Palette.Brush(strokeNormal);
        BorderThickness = new Thickness(1);
        CornerRadius = new CornerRadius(radius);
        Children.Add(content);
        Ui.OnHover(this, h =>
        {
            Background = Palette.Brush(h ? _bgHover : _bgNormal);
            BorderBrush = Palette.Brush(h ? _strokeHover : _strokeNormal);
        });
        if (onTap is not null)
        {
            Tapped += (_, _) => onTap();
            PointerEntered += (_, _) => ProtectedCursor =
                Microsoft.UI.Input.InputSystemCursor.Create(Microsoft.UI.Input.InputSystemCursorShape.Hand);
        }
    }
}
