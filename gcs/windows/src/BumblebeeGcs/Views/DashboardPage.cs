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
using BumblebeeGcs.Controls;
using BumblebeeGcs.Logic;
using BumblebeeGcs.Models;
using BumblebeeGcs.Services;
using BumblebeeGcs.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.UI;

namespace BumblebeeGcs.Views;

/// <summary>
/// Дашборд: hero-плитки, «кто управляет», камеры, masonry-панели. Порт DashboardView.swift.
/// Честный экран: до первых данных «—», устаревший источник — серая панель с «no data N s»,
/// armed — три состояния, Link — одно из четырёх (решения — в BumblebeeGcs.Logic).
/// </summary>
public sealed class DashboardPage : Grid
{
    private readonly AppState _app;
    private readonly TelemetryStore _t;

    // Hero
    private readonly StatTile _modeTile, _stateTile, _batteryTile, _altTile, _linkTile;

    // Who is in control (display only) + visible control events
    private readonly FontIcon _controlIcon;
    private readonly TextBlock _controlValue, _controlCaption;
    private readonly StackPanel _eventList = new() { Spacing = Palette.S1 };
    private int _eventsVersion = -1;

    // Cameras
    private readonly CameraView _front, _bottom, _pip;
    private bool _pipBig;

    // Panels
    private readonly AttitudeView _attitude = new();
    private readonly ReadoutRow _roll = new("Roll"), _pitch = new("Pitch"), _yaw = new("Yaw");
    private readonly TextBlock _attitudeHint;
    private readonly Grid _rpyRow;
    private readonly LabeledBarRow _batteryBar;
    private readonly ReadoutRow _x, _y, _z, _vx, _vy, _vz;
    private readonly LabeledBarRow _hSpeed, _vSpeed, _angRate, _imuAccel;
    private readonly LabeledBarRow _cpuTemp, _cpuLoad, _load135, _ram;
    private readonly ChartView _chartAlt, _chartSpd, _chartBat;
    private readonly PositionMapView _map;
    private readonly StackPanel _logList = new() { Spacing = Palette.S0 };
    private int _logVersion = -1;
    private readonly PanelCard _attitudePanel, _telemetryPanel, _flightPanel, _piPanel, _chartsPanel, _mapPanel;

    private readonly Grid _masonry = new() { ColumnSpacing = Palette.S4 };
    private readonly FrameworkElement[] _panels;
    private int _masonryCols;

    private bool _dirty = true, _dirtyMetrics = true;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _refresh;
    private readonly Action _onTelemetry, _onMetrics, _onReconnected;

    private const string AttitudeHint = "+pitch = nose down (ROS) · yaw ENU, 0 = east";

    public DashboardPage(AppState app)
    {
        _app = app;
        _t = app.Telemetry;

        // MARK: Hero
        _modeTile = new StatTile("Mode", IconGlyphs.Mode, Palette.Primary);
        _stateTile = new StatTile("State", IconGlyphs.Unknown, Palette.Caution);
        _batteryTile = new StatTile("Battery", IconGlyphs.BatteryUnknown, Palette.Muted);
        _altTile = new StatTile("Z (local)", IconGlyphs.Altitude, Palette.Primary);
        _linkTile = new StatTile("Link", IconGlyphs.Link, Palette.Warn);
        var hero = new AdaptiveGridPanel { MinItemWidth = 190, Spacing = Palette.S3 };
        foreach (var tile in new[] { _modeTile, _stateTile, _batteryTile, _altTile, _linkTile })
            hero.Children.Add(tile);

        // MARK: Who is in control (display only)
        _controlIcon = Ui.Icon(IconGlyphs.InControl, Palette.IconLg, Palette.Caution);
        _controlValue = Ui.Text("Unknown", Fonts.StatValue, Palette.Caution);
        _controlCaption = Ui.Text("", Fonts.MonoSmall, Palette.Muted);
        var controlPlate = Ui.VStack(Palette.S0,
            Ui.Text("IN CONTROL", Fonts.SectionLbl, Palette.Muted, tracking: 0.8),
            Ui.HStack(Palette.S2, _controlIcon, _controlValue),
            _controlCaption);
        controlPlate.MinWidth = 220;
        var controlRow = new Grid { ColumnSpacing = Palette.S5 };
        controlRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        controlRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        _eventList.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(controlPlate, 0);
        Grid.SetColumn(_eventList, 1);
        controlRow.Children.Add(controlPlate);
        controlRow.Children.Add(_eventList);
        var controlCard = Ui.GlassCard(controlRow, Palette.RPanel,
            new Thickness(Palette.S3, Palette.S2 + 2, Palette.S3, Palette.S2 + 2));

        // MARK: Cameras
        _front = new CameraView { Host = app.DroneHost, Topic = "/second_camera/image_raw" };
        _bottom = new CameraView { Host = app.DroneHost, Topic = "/main_camera/image_raw" };
        _pip = new CameraView(showFlipButton: false)
        {
            Host = app.DroneHost,
            Topic = "/aruco_map/image",
            Quality = 50, Fps = 3, StreamWidth = 160, StreamHeight = 120,
            Width = 120, Height = 90,
            CompactHint = true,
        };
        _pip.BorderBrush = Palette.Brush(Palette.WithAlpha(Palette.Primary, 0.7));
        _pip.BorderThickness = new Thickness(1);
        _pip.CornerRadius = new CornerRadius(Palette.RMedia);
        _pip.HorizontalAlignment = HorizontalAlignment.Right;
        _pip.VerticalAlignment = VerticalAlignment.Top;
        _pip.Margin = new Thickness(Palette.S2);
        Ui.OnTap(_pip, () =>
        {
            _pipBig = !_pipBig;
            _pip.Width = _pipBig ? 190 : 120;
            _pip.Height = _pipBig ? 142 : 90;
        });

        var tabs = new SegmentedTabs(new[]
        {
            ("Bottom", "/main_camera/image_raw"),
            ("ArUco", "/aruco_detect/debug"),
        }, "/main_camera/image_raw");
        // One stream per view: SetTopic cancels the old connection before opening the new one.
        tabs.SelectionChanged += topic => _bottom.SetTopic(topic);

        var bottomStack = new Grid();
        bottomStack.Children.Add(_bottom);
        bottomStack.Children.Add(_pip);

        var cameras = new Grid { ColumnSpacing = Palette.S4 };
        cameras.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        cameras.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var frontCard = CameraCard("Front", null, _front);
        var bottomCard = CameraCard("Bottom", tabs, bottomStack);
        Grid.SetColumn(frontCard, 0);
        Grid.SetColumn(bottomCard, 1);
        cameras.Children.Add(frontCard);
        cameras.Children.Add(bottomCard);
        cameras.VerticalAlignment = VerticalAlignment.Top;

        // MARK: Panels
        _batteryBar = new LabeledBarRow("Battery", Palette.Muted);
        _x = new ReadoutRow("X", Palette.Danger);
        _y = new ReadoutRow("Y", Palette.Ok);
        _z = new ReadoutRow("Z (local)", Palette.Accent2);
        _vx = new ReadoutRow("Vx"); _vy = new ReadoutRow("Vy"); _vz = new ReadoutRow("Vz");
        _hSpeed = new LabeledBarRow("Horiz. Speed", Palette.DataTeal);
        _vSpeed = new LabeledBarRow("Vert. Speed", Palette.DataBlue);
        _angRate = new LabeledBarRow("Angular Rate", Palette.DataOrange);
        _imuAccel = new LabeledBarRow("IMU Accel", Palette.DataGreen);
        _cpuTemp = new LabeledBarRow("CPU Temp", Palette.Muted);
        _cpuLoad = new LabeledBarRow("CPU Load", Palette.Muted);
        _load135 = new LabeledBarRow("Load 1/5/15", Palette.Accent2);
        _ram = new LabeledBarRow("RAM", Palette.Accent2);
        _chartAlt = new ChartView("Z (local), m", _t.ChartAlt, Palette.DataBlue, minSpan: ChartScale.AltitudeMinSpan);
        _chartSpd = new ChartView("Speed, m/s", _t.ChartSpd, Palette.DataTeal, fixedMin: 0, fixedMax: 5);
        _chartBat = new ChartView("Battery, %", _t.ChartBat, Palette.DataGreen, fixedMin: 0, fixedMax: 100);
        _map = new PositionMapView(_t.PosTrail);

        var attitudeCentered = new Grid();
        _attitude.HorizontalAlignment = HorizontalAlignment.Center;
        attitudeCentered.Children.Add(_attitude);
        _rpyRow = new Grid { ColumnSpacing = Palette.S3 };
        foreach (var i in Enumerable.Range(0, 3))
            _rpyRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        Grid.SetColumn(_roll, 0); Grid.SetColumn(_pitch, 1); Grid.SetColumn(_yaw, 2);
        _rpyRow.Children.Add(_roll); _rpyRow.Children.Add(_pitch); _rpyRow.Children.Add(_yaw);
        // Цифра Pitch — в ROS-конвенции, как get_telemetry() у учеников; рисунок исправлен.
        _attitudeHint = Ui.Text(AttitudeHint, Fonts.MonoSmall, Palette.Muted);
        _attitudeHint.TextWrapping = TextWrapping.Wrap;

        var divider = new Border { Height = 1, Background = Palette.Brush(Palette.Hairline) };

        _logList.Children.Add(Ui.Text("—", Fonts.MonoSmall, Palette.Muted));
        var logScroll = new ScrollViewer
        {
            Content = _logList,
            MaxHeight = 360,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };

        _attitudePanel = new PanelCard("Attitude", IconGlyphs.Attitude, attitudeCentered, _rpyRow, _attitudeHint);
        _telemetryPanel = new PanelCard("Telemetry", IconGlyphs.Telemetry, _batteryBar, _x, _y, _z, divider, _vx, _vy, _vz);
        _flightPanel = new PanelCard("Flight Data", IconGlyphs.FlightData, _hSpeed, _vSpeed, _angRate, _imuAccel);
        _piPanel = new PanelCard("Raspberry Pi", IconGlyphs.Cpu, _cpuTemp, _cpuLoad, _load135, _ram);
        _chartsPanel = new PanelCard("Charts", IconGlyphs.Charts, _chartAlt, _chartSpd, _chartBat);
        _mapPanel = new PanelCard("Position Map", IconGlyphs.Map, _map);
        _panels = new FrameworkElement[]
        {
            _attitudePanel,
            _telemetryPanel,
            _flightPanel,
            _piPanel,
            _chartsPanel,
            _mapPanel,
            new PanelCard("Messages", IconGlyphs.Messages, logScroll),
        };

        // MARK: Layout
        var stack = Ui.VStack(Palette.S4, hero, controlCard, cameras, _masonry);
        stack.Padding = new Thickness(Palette.S4);
        var scroll = new ScrollViewer { Content = stack, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Children.Add(scroll);

        SizeChanged += (_, e) => RebuildMasonry(e.NewSize.Width);
        RebuildMasonry(1280);

        // MARK: Refresh
        // Store.Updated приходит и от таймера AppState раз в 500 мс, поэтому «no data N s»
        // и серые панели обновляются, даже когда сообщений нет совсем.
        _onTelemetry = () => _dirty = true;
        _onMetrics = () => _dirtyMetrics = true;
        _onReconnected = () =>
        {
            _front.Restart(force: true);
            _bottom.Restart(force: true);
            _pip.Restart(force: true);
        };
        _t.Updated += _onTelemetry;
        _app.Metrics.Updated += _onMetrics;
        _app.Reconnected += _onReconnected;

        _refresh = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread().CreateTimer();
        _refresh.Interval = TimeSpan.FromMilliseconds(50);
        _refresh.Tick += (_, _) =>
        {
            if (_dirtyMetrics) { _dirtyMetrics = false; RefreshMetrics(); }
            if (_dirty) { _dirty = false; RefreshTelemetry(); }
        };
        _refresh.Start();

        Unloaded += (_, _) =>
        {
            _refresh.Stop();
            _t.Updated -= _onTelemetry;
            _app.Metrics.Updated -= _onMetrics;
            _app.Reconnected -= _onReconnected;
        };

        RefreshMetrics();
        RefreshTelemetry();
    }

    /// <summary>
    /// Плотная упаковка панелей по колонкам (Pinterest-style), распределение i % cols
    /// — как в DashboardView.swift.
    /// </summary>
    private void RebuildMasonry(double width)
    {
        var cols = width > 1500 ? 3 : (width > 1040 ? 2 : 1);
        if (cols == _masonryCols) return;
        _masonryCols = cols;

        foreach (var p in _panels)
            if (p.Parent is StackPanel sp) sp.Children.Remove(p);
        _masonry.Children.Clear();
        _masonry.ColumnDefinitions.Clear();

        var columns = new StackPanel[cols];
        for (var c = 0; c < cols; c++)
        {
            _masonry.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            columns[c] = new StackPanel { Spacing = Palette.S4, VerticalAlignment = VerticalAlignment.Top };
            Grid.SetColumn(columns[c], c);
            _masonry.Children.Add(columns[c]);
        }
        for (var i = 0; i < _panels.Length; i++)
            columns[i % cols].Children.Add(_panels[i]);
    }

    private FrameworkElement CameraCard(string title, SegmentedTabs? tabs, FrameworkElement content)
    {
        var header = new Grid { ColumnSpacing = Palette.S2 };
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var label = Ui.Text(title.ToUpperInvariant(), Fonts.SectionLbl, Palette.Muted, tracking: 1.1);
        Grid.SetColumn(label, 0);
        header.Children.Add(label);
        if (tabs is not null)
        {
            Grid.SetColumn(tabs, 1);
            header.Children.Add(tabs);
        }

        // 4:3 контейнер: высота следует за шириной.
        var video = new Grid { Background = Palette.Brush(Colors.Black), CornerRadius = new CornerRadius(Palette.RMedia) };
        video.Children.Add(content);
        Ui.ClipRounded(video, (float)Palette.RMedia);
        video.SizeChanged += (_, e) =>
        {
            var h = e.NewSize.Width * 3.0 / 4.0;
            if (double.IsNaN(video.Height) || Math.Abs(video.Height - h) > 0.5) video.Height = h;
        };

        var inner = Ui.VStack(Palette.S2, header, video);
        return Ui.GlassCard(inner, Palette.RPanel, new Thickness(Palette.S3));
    }

    // MARK: - Refresh

    private static double Limit(TelemetrySource s) => Freshness.Limit(s);

    private static string? Note(double? at, double now, TelemetrySource s) => Freshness.StaleNote(at, now, Limit(s));

    /// <summary>"no data N s" of the oldest stale source of a mixed panel (its stale rows are greyed), or null.</summary>
    private static string? OldestNote(double now, params (double? At, TelemetrySource Source)[] sources)
    {
        double? worst = null;
        foreach (var (at, src) in sources)
            if (at is double t && Freshness.IsStale(t, now, Limit(src)) && (worst is null || now - t > worst))
                worst = now - t;
        return worst is double w ? Freshness.NoDataText(w) : null;
    }

    private void RefreshTelemetry()
    {
        var now = MonoClock.Now;
        var stateNote = Note(_t.StateAt, now, TelemetrySource.State);
        var poseNote = Note(_t.PoseAt, now, TelemetrySource.Pose);
        var velNote = Note(_t.VelocityAt, now, TelemetrySource.Velocity);
        var imuNote = Note(_t.ImuAt, now, TelemetrySource.Imu);
        var attNote = Note(_t.AttitudeAt, now, TelemetrySource.Attitude);
        var batNote = Note(_t.BatteryAt, now, TelemetrySource.Battery);

        // MARK: Hero
        _modeTile.Update(ModeLogic.DisplayMode(_t.Mode), Palette.Primary);
        _modeTile.SetCaption(stateNote ?? ModeLogic.Explain(_t.Mode), stateNote is null ? null : Palette.Caution);
        _modeTile.SetDimmed(stateNote is not null);

        var armed = ArmedLogic.Display(_t.Armed, _t.LastKnownArmed);
        var armedColor = Palette.ForTone(armed.Tone);
        _stateTile.Update(armed.Value, armedColor,
            _t.Armed is null ? IconGlyphs.Unknown : (_t.Armed == true ? IconGlyphs.Armed : IconGlyphs.Disarmed));
        _stateTile.SetCaption(armed.Caption, armedColor);

        var bat = _t.Battery;
        _batteryTile.Update(bat.Short, Palette.ForTone(bat.Tone), bat.HasLevel ? IconGlyphs.Battery : IconGlyphs.BatteryUnknown);
        _batteryTile.SetCaption(batNote ?? bat.Caption, batNote is null ? null : Palette.Caution);
        _batteryTile.SetDimmed(batNote is not null);

        _altTile.Update(Format.Fixed(_t.PosZ, 2, "m"), Palette.Primary);
        _altTile.SetCaption(poseNote ?? (_t.PosZ is null ? "no position yet" : "local estimate"),
            poseNote is null ? null : Palette.Caution);
        _altTile.SetDimmed(poseNote is not null);

        var link = _t.Link;
        var linkColor = Palette.ForTone(LinkLogic.ToneOf(link));
        _linkTile.Update(LinkLogic.Text(link), linkColor);
        _linkTile.SetCaption(LinkLogic.Caption(link, _t.LinkConnecting, _t.StateAgeOnSocket(now)),
            link == LinkState.Ok ? null : linkColor);

        RefreshControl();

        // MARK: Attitude (IMU orientation when valid, else pose)
        _attitude.Update(_t.Roll ?? 0, _t.Pitch ?? 0);
        Stale.Dim(_attitude, _t.Roll is null || attNote is not null);
        _roll.Set(Format.Degrees(_t.Roll));
        _pitch.Set(Format.Degrees(_t.Pitch));
        _yaw.Set(Format.Degrees(_t.Yaw));
        Stale.Dim(_rpyRow, attNote is not null);
        _attitudeHint.Text = AttitudeHint + (_t.Roll is null ? "" : _t.AttitudeFromImu ? " · from IMU" : " · from pose");
        _attitudePanel.SetNote(attNote);

        // MARK: Telemetry
        _batteryBar.Set(bat.Text, bat.Pct ?? 0, Palette.ForTone(bat.Tone));
        Stale.Dim(_batteryBar, batNote is not null);
        _x.Set(Format.Signed(_t.PosX, "m"));
        _y.Set(Format.Signed(_t.PosY, "m"));
        _z.Set(Format.Signed(_t.PosZ, "m"));
        _vx.Set(Format.Signed(_t.Vx, "m/s"));
        _vy.Set(Format.Signed(_t.Vy, "m/s"));
        _vz.Set(Format.Signed(_t.Vz, "m/s"));
        foreach (var r in new UIElement[] { _x, _y, _z }) Stale.Dim(r, poseNote is not null);
        foreach (var r in new UIElement[] { _vx, _vy, _vz }) Stale.Dim(r, velNote is not null);
        _telemetryPanel.SetNote(OldestNote(now,
            (_t.BatteryAt, TelemetrySource.Battery), (_t.PoseAt, TelemetrySource.Pose), (_t.VelocityAt, TelemetrySource.Velocity)));

        // MARK: Flight data
        _hSpeed.Set(Format.Fixed(_t.SpeedH, 2, "m/s"), MathUtil.PctOf(_t.SpeedH ?? 0, 5));
        _vSpeed.Set(Format.Fixed(_t.SpeedV, 2, "m/s"), MathUtil.PctOf(_t.SpeedV ?? 0, 3));
        _angRate.Set(Format.Fixed(_t.GyroMag, 1, "°/s"), MathUtil.PctOf(_t.GyroMag ?? 0, 360));
        _imuAccel.Set(Format.Fixed(_t.AccelMag, 2, "m/s²"), MathUtil.PctOf(_t.AccelMag ?? 0, 30));
        Stale.Dim(_hSpeed, velNote is not null);
        Stale.Dim(_vSpeed, velNote is not null);
        Stale.Dim(_angRate, imuNote is not null);
        Stale.Dim(_imuAccel, imuNote is not null);
        _flightPanel.SetNote(OldestNote(now, (_t.VelocityAt, TelemetrySource.Velocity), (_t.ImuAt, TelemetrySource.Imu)));

        // MARK: Charts & map
        _chartAlt.SetStale(poseNote);
        _chartSpd.SetStale(velNote);
        _chartBat.SetStale(batNote);
        _chartAlt.Refresh();
        _chartSpd.Refresh();
        _chartBat.Refresh();
        _chartsPanel.SetNote(OldestNote(now,
            (_t.PoseAt, TelemetrySource.Pose), (_t.VelocityAt, TelemetrySource.Velocity), (_t.BatteryAt, TelemetrySource.Battery)));
        _map.Refresh();
        Stale.Dim(_map, poseNote is not null);
        _mapPanel.SetNote(poseNote);

        RefreshMetricsFreshness(now);
        RefreshLog();
    }

    /// <summary>Плашка «кто управляет» и последние события смены режима/управления.</summary>
    private void RefreshControl()
    {
        var who = _t.InControl;
        var color = Palette.ForTone(ModeLogic.ControllerTone(who));
        _controlValue.Text = ModeLogic.ControllerText(who);
        _controlValue.Foreground = Palette.Brush(color);
        _controlIcon.Foreground = Palette.Brush(color);
        _controlCaption.Text = ModeLogic.ControllerCaption(who, _t.Mode);

        if (_t.Events.Version == _eventsVersion) return;
        _eventsVersion = _t.Events.Version;
        _eventList.Children.Clear();
        if (_t.Events.Items.Count == 0)
        {
            _eventList.Children.Add(Ui.Text("no control changes yet", Fonts.MonoSmall, Palette.Muted));
            return;
        }
        var first = true;
        foreach (var ev in _t.Events.Items)
        {
            var text = Ui.Text(ev.Text, first ? Fonts.BodyStrong : Fonts.Body,
                first ? Palette.ForTone(ev.Tone) : Palette.Muted);
            var time = Ui.Text(ev.Time, Fonts.LogMono, Palette.Muted);
            _eventList.Children.Add(Ui.HStack(Palette.S2, time, text));
            first = false;
        }
    }

    private void RefreshLog()
    {
        if (_t.Messages.Version == _logVersion) return;
        _logVersion = _t.Messages.Version;

        _logList.Children.Clear();
        var entries = _t.Messages.Entries;
        if (entries.Count == 0)
        {
            _logList.Children.Add(Ui.Text("—", Fonts.MonoSmall, Palette.Muted));
            return;
        }
        foreach (var e in entries)
        {
            var text = Ui.Text(e.Text, Fonts.LogMono, e.Kind == LogKind.Fcu ? Palette.Caution : Palette.Text);
            text.TextWrapping = TextWrapping.Wrap;
            var row = new Grid { ColumnSpacing = Palette.S1 + 2 };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var time = Ui.Text(e.Time, Fonts.LogMono, Palette.Muted);
            time.VerticalAlignment = VerticalAlignment.Top;
            text.VerticalAlignment = VerticalAlignment.Top;
            Grid.SetColumn(time, 0);
            Grid.SetColumn(text, 1);
            row.Children.Add(time);
            row.Children.Add(text);
            _logList.Children.Add(row);
        }
    }

    private void RefreshMetrics()
    {
        var m = _app.Metrics.Metrics;
        _cpuTemp.Set(Format.Fixed(m.CpuTemp, 1, "°C"), Math.Min(100, m.CpuTemp ?? 0), TempColor(m.CpuTemp));
        _cpuLoad.Set(m.CpuPct is double c ? Format.Fixed(c, 0) + "%" : Format.Dash, m.CpuPct ?? 0, CpuColor(m.CpuPct));
        _load135.Set(LoadText(m), (m.Load1 ?? 0) / (m.CpuCount ?? 4) * 100);
        _ram.Set(MemText(m), m.MemPct ?? 0);
        RefreshMetricsFreshness(MonoClock.Now);
    }

    /// <summary>Metrics older than 6 s (:8888 stopped answering): grey with "no data N s".</summary>
    private void RefreshMetricsFreshness(double now)
    {
        var note = Note(_app.Metrics.LastArrival, now, TelemetrySource.Metrics);
        foreach (var r in new UIElement[] { _cpuTemp, _cpuLoad, _load135, _ram }) Stale.Dim(r, note is not null);
        _piPanel.SetNote(note);
    }

    // MARK: - Derived (цвета метрик)

    private static Color TempColor(double? x) =>
        x is not double v ? Palette.Muted : v < 60 ? Palette.Ok : (v < 75 ? Palette.Warn : Palette.Danger);

    private static Color CpuColor(double? x) =>
        x is not double v ? Palette.Muted : v < 60 ? Palette.Ok : (v < 85 ? Palette.Warn : Palette.Danger);

    private static string LoadText(SystemMetrics m) =>
        m.Load1 is double l1 && m.Load5 is double l5 && m.Load15 is double l15
            ? $"{Format.Fixed(l1, 2)} / {Format.Fixed(l5, 2)} / {Format.Fixed(l15, 2)}" : Format.Dash;

    private static string MemText(SystemMetrics m) =>
        m.MemUsed is int u && m.MemTotal is int tot && m.MemPct is double p
            ? $"{u} / {tot} MB ({Format.Fixed(p, 0)}%)" : Format.Dash;
}
