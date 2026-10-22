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
using BumblebeeGcs.Logic;
using BumblebeeGcs.Models;
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.UI;

namespace BumblebeeGcs.Controls;

// Рисование сделано XAML-шейпами (не Win2D): CanvasControl в unpackaged-окне
// компоновался мимо своего лейаута. Шейпы дешевле для этих сцен: авиагоризонт
// обновляется двумя углами RenderTransform без перерисовки.

/// <summary>
/// Авиагоризонт: roll вращает горизонт, pitch сдвигает его по вертикали;
/// pitch-лесенка, roll-дуга и неподвижный маркер самолёта — конструкция 1:1
/// с web-канвасом и AttitudeView.swift. Pitch в ROS-конвенции: + = нос вниз,
/// поэтому при +pitch горизонт уходит вверх и земли становится больше.
/// </summary>
public sealed class AttitudeView : Grid
{
    private const double S = 186, C = S / 2;          // размер, центр
    private const double R = C - 2;                   // радиус приборного круга
    private const double PxPerDeg = C / 45.0;

    private static readonly Color Sky = Palette.Hex(0x1a4cc0);
    private static readonly Color Ground = Palette.Hex(0x7c4820);

    private readonly RotateTransform _horizonRot = new() { CenterX = C, CenterY = C };
    private readonly TranslateTransform _pitchShift = new();
    private readonly RotateTransform _arcRot = new() { CenterX = C, CenterY = C };

    public AttitudeView()
    {
        Width = S;
        Height = S;

        // Клипованный круг с горизонтом и roll-дугой.
        var clipHost = new Grid { Width = S, Height = S };
        Ui.ClipRounded(clipHost, (float)C);

        // Слой горизонта: внутренний канвас сдвигается по pitch, внешний вращается по roll.
        var pitched = new Canvas { RenderTransform = _pitchShift };
        const double big = 500;
        pitched.Children.Add(Place(new Rectangle { Width = big * 2, Height = big, Fill = Palette.Brush(Sky) }, C - big, C - big));
        pitched.Children.Add(Place(new Rectangle { Width = big * 2, Height = big, Fill = Palette.Brush(Ground) }, C - big, C));
        pitched.Children.Add(new Line
        {
            X1 = C - big, Y1 = C, X2 = C + big, Y2 = C,
            Stroke = Palette.Brush(Colors.White), StrokeThickness = 1.5,
        });
        // Pitch-лесенка.
        for (var deg = -30; deg <= 30; deg += 10)
        {
            if (deg == 0) continue;
            var y = C - deg * PxPerDeg;
            double w = deg % 30 == 0 ? 30 : 20;
            pitched.Children.Add(new Line
            {
                X1 = C - w, Y1 = y, X2 = C + w, Y2 = y,
                Stroke = Palette.Brush(Palette.WithAlpha(Colors.White, 0.8)), StrokeThickness = 1,
            });
            var label = Ui.Text(Math.Abs(deg).ToString(), Fonts.Micro, Colors.White);
            pitched.Children.Add(Place(label, C + w + 4, y - 5));
        }
        var horizon = new Canvas { Width = S, Height = S, RenderTransform = _horizonRot };
        horizon.Children.Add(pitched);
        clipHost.Children.Add(horizon);

        // Слой roll-дуги (только вращение).
        var arc = new Canvas { Width = S, Height = S, RenderTransform = _arcRot };
        foreach (var deg in new[] { -60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60 })
        {
            var ang = deg * Math.PI / 180 - Math.PI / 2;
            double r1 = R - 2, r2 = R - (deg % 30 == 0 ? 10 : 6);
            arc.Children.Add(new Line
            {
                X1 = C + Math.Cos(ang) * r1, Y1 = C + Math.Sin(ang) * r1,
                X2 = C + Math.Cos(ang) * r2, Y2 = C + Math.Sin(ang) * r2,
                Stroke = Palette.Brush(Palette.WithAlpha(Colors.White, 0.7)), StrokeThickness = 1,
            });
        }
        clipHost.Children.Add(arc);
        Children.Add(clipHost);

        // Неподвижное: окантовка, маркер самолёта, верхний указатель roll.
        var overlay = new Canvas { Width = S, Height = S };
        overlay.Children.Add(Place(new Ellipse
        {
            Width = R * 2, Height = R * 2,
            Stroke = Palette.Brush(Palette.Border), StrokeThickness = 2,
        }, C - R, C - R));
        overlay.Children.Add(new Line { X1 = C - 30, Y1 = C, X2 = C - 10, Y2 = C, Stroke = Palette.Brush(Palette.Caution), StrokeThickness = 2 });
        overlay.Children.Add(new Line { X1 = C + 10, Y1 = C, X2 = C + 30, Y2 = C, Stroke = Palette.Brush(Palette.Caution), StrokeThickness = 2 });
        overlay.Children.Add(Place(new Ellipse
        {
            Width = 6, Height = 6,
            Stroke = Palette.Brush(Palette.Caution), StrokeThickness = 2,
        }, C - 3, C - 3));
        overlay.Children.Add(new Polygon
        {
            Points = { new(C, C - R + 2), new(C - 6, C - R + 12), new(C + 6, C - R + 12) },
            Fill = Palette.Brush(Palette.Caution),
        });
        Children.Add(overlay);
    }

    public void Update(double roll, double pitch)
    {
        _horizonRot.Angle = -roll;
        _arcRot.Angle = -roll;
        _pitchShift.Y = AttitudeMath.HorizonShiftPx(pitch, PxPerDeg);
    }

    private static FrameworkElement Place(FrameworkElement e, double x, double y)
    {
        Canvas.SetLeft(e, x);
        Canvas.SetTop(e, y);
        return e;
    }
}

/// <summary>
/// Залитый line-chart последних N сэмплов с подписью актуального значения.
/// Шкала не уже minSpan (высота — 1 м, чтобы шум в 1-2 см не растягивался на весь
/// график); её min/max подписаны у правого края.
/// </summary>
public sealed class ChartView : StackPanel
{
    private readonly List<double> _data;
    private readonly double? _fixedMin, _fixedMax;
    private readonly double _minSpan;
    private readonly Color _color;
    private readonly TextBlock _latest, _hiLabel, _loLabel;
    private readonly Grid _plot;
    private readonly Polygon _area;
    private readonly Polyline _line;
    private string? _staleNote;

    public ChartView(string title, List<double> data, Color color,
                     double? fixedMin = null, double? fixedMax = null, double minSpan = 1.0)
    {
        _data = data;
        _fixedMin = fixedMin;
        _fixedMax = fixedMax;
        _minSpan = minSpan;
        _color = color;

        Orientation = Orientation.Vertical;
        Spacing = Palette.S1;
        _latest = Ui.Text("—", Fonts.MonoSmall, color);
        Children.Add(Ui.SpaceBetween(Ui.Text(title, Fonts.MonoSmall, Palette.Muted), _latest));

        _area = new Polygon { Fill = Palette.Brush(Palette.WithAlpha(color, 0.15)) };
        _line = new Polyline { Stroke = Palette.Brush(color), StrokeThickness = 1.5 };
        _plot = new Grid
        {
            Height = 56,
            Background = Palette.Brush(Palette.Bg),
            CornerRadius = new CornerRadius(Palette.RSmall),
        };
        Ui.ClipRounded(_plot, (float)Palette.RSmall);
        _plot.Children.Add(_area);
        _plot.Children.Add(_line);
        _hiLabel = Ui.Text("", Fonts.Micro, Palette.Muted);
        _hiLabel.HorizontalAlignment = HorizontalAlignment.Right;
        _hiLabel.VerticalAlignment = VerticalAlignment.Top;
        _hiLabel.Margin = new Thickness(0, 1, Palette.S1, 0);
        _loLabel = Ui.Text("", Fonts.Micro, Palette.Muted);
        _loLabel.HorizontalAlignment = HorizontalAlignment.Right;
        _loLabel.VerticalAlignment = VerticalAlignment.Bottom;
        _loLabel.Margin = new Thickness(0, 0, Palette.S1, 1);
        _plot.Children.Add(_hiLabel);
        _plot.Children.Add(_loLabel);
        _plot.SizeChanged += (_, _) => Redraw();
        Children.Add(_plot);
    }

    public void Refresh()
    {
        if (_staleNote is not null)
        {
            _latest.Text = _staleNote;
            _latest.Foreground = Palette.Brush(Palette.Caution);
        }
        else
        {
            _latest.Text = _data.Count > 0 ? Format.Fixed(_data[^1], 2) : Format.Dash;
            _latest.Foreground = Palette.Brush(_color);
        }
        Redraw();
    }

    /// <summary>Source older than its limit: the chart greys out and says "no data N s".</summary>
    public void SetStale(string? note)
    {
        _staleNote = note;
        Stale.Dim(_plot, note is not null);
    }

    private void Redraw()
    {
        double w = _plot.ActualWidth, h = _plot.ActualHeight;
        var n = _data.Count;
        if (w <= 0 || h <= 0 || n < 2)
        {
            _line.Points.Clear();
            _area.Points.Clear();
            _hiLabel.Text = _loLabel.Text = "";
            return;
        }
        var (lo, hi) = ChartScale.Range(_data, _fixedMin, _fixedMax, _minSpan);
        _hiLabel.Text = ChartScale.Label(hi, hi - lo);
        _loLabel.Text = ChartScale.Label(lo, hi - lo);

        var linePts = new PointCollection();
        var areaPts = new PointCollection { new Windows.Foundation.Point(0, h) };
        for (var i = 0; i < n; i++)
        {
            var x = w * i / (n - 1);
            var norm = (_data[i] - lo) / (hi - lo);
            var pt = new Windows.Foundation.Point(x, h * (1 - norm));
            linePts.Add(pt);
            areaPts.Add(pt);
        }
        areaPts.Add(new Windows.Foundation.Point(w, h));
        _line.Points = linePts;
        _area.Points = areaPts;
    }
}

/// <summary>Авто-масштабируемый трейл позиции сверху (X вправо, Y вверх), сетка 1 м.</summary>
public sealed class PositionMapView : Grid
{
    private readonly List<TrailPoint> _trail;
    private readonly Canvas _canvas = new();

    public PositionMapView(List<TrailPoint> trail)
    {
        _trail = trail;
        Height = 240;
        Background = Palette.Brush(Palette.Bg);
        CornerRadius = new CornerRadius(Palette.RMedia);
        BorderBrush = Palette.Brush(Palette.Border);
        BorderThickness = new Thickness(1);
        Children.Add(_canvas);
        Ui.ClipRounded(this, (float)Palette.RMedia);
        SizeChanged += (_, _) => Refresh();
    }

    public void Refresh()
    {
        double w = ActualWidth, h = ActualHeight;
        _canvas.Children.Clear();
        if (w <= 0 || h <= 0) return;
        const double pad = 18;

        // Границы (минимум ±1 м).
        double minX = -1, maxX = 1, minY = -1, maxY = 1;
        foreach (var p in _trail)
        {
            minX = Math.Min(minX, p.X); maxX = Math.Max(maxX, p.X);
            minY = Math.Min(minY, p.Y); maxY = Math.Max(maxY, p.Y);
        }
        var spanX = Math.Max(maxX - minX, 0.5);
        var spanY = Math.Max(maxY - minY, 0.5);
        var span = Math.Max(spanX, spanY) * 1.15;
        double cxData = (minX + maxX) / 2, cyData = (minY + maxY) / 2;
        var plot = Math.Min(w, h) - pad * 2;
        var scale = plot / span;
        double ox = w / 2, oy = h / 2;

        Windows.Foundation.Point ToScreen(double x, double y) =>
            new(ox + (x - cxData) * scale, oy - (y - cyData) * scale);

        // Сетка с шагом 1 м.
        var gridBrush = Palette.Brush(Palette.GridLine);
        var g = -Math.Ceiling(span / 2);
        while (g <= Math.Ceiling(span / 2))
        {
            var sx = ToScreen(cxData + g, 0).X;
            var sy = ToScreen(0, cyData + g).Y;
            _canvas.Children.Add(new Line { X1 = sx, Y1 = pad, X2 = sx, Y2 = h - pad, Stroke = gridBrush, StrokeThickness = 0.5 });
            _canvas.Children.Add(new Line { X1 = pad, Y1 = sy, X2 = w - pad, Y2 = sy, Stroke = gridBrush, StrokeThickness = 0.5 });
            g += 1;
        }

        // Оси начала координат.
        var axisBrush = Palette.Brush(Palette.AxisLine);
        var o = ToScreen(0, 0);
        _canvas.Children.Add(new Line { X1 = o.X, Y1 = pad, X2 = o.X, Y2 = h - pad, Stroke = axisBrush, StrokeThickness = 1 });
        _canvas.Children.Add(new Line { X1 = pad, Y1 = o.Y, X2 = w - pad, Y2 = o.Y, Stroke = axisBrush, StrokeThickness = 1 });

        // Трейл: затухание аппроксимировано четырьмя сегментными полилиниями.
        if (_trail.Count > 1)
        {
            const int chunks = 4;
            var per = Math.Max(2, (int)Math.Ceiling(_trail.Count / (double)chunks));
            for (var c = 0; c < chunks; c++)
            {
                var from = c * per;
                if (from >= _trail.Count - 1) break;
                var to = Math.Min(_trail.Count - 1, from + per);
                var pts = new PointCollection();
                for (var i = from; i <= to; i++)
                    pts.Add(ToScreen(_trail[i].X, _trail[i].Y));
                var alpha = 0.2 + 0.8 * ((c + 1) / (double)chunks);
                _canvas.Children.Add(new Polyline
                {
                    Points = pts,
                    Stroke = Palette.Brush(Palette.WithAlpha(Palette.Primary, alpha)),
                    StrokeThickness = 1.5,
                });
            }
            // Точка текущей позиции.
            var last = ToScreen(_trail[^1].X, _trail[^1].Y);
            var dot = new Ellipse { Width = 8, Height = 8, Fill = Palette.Brush(Palette.Caution) };
            Canvas.SetLeft(dot, last.X - 4);
            Canvas.SetTop(dot, last.Y - 4);
            _canvas.Children.Add(dot);
        }
    }
}
