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
/// Дашборд: hero-плитки (с «Control» — кто управляет), строка события управления, камеры,
/// masonry-панели. Порт DashboardView.swift, те же правила: до первых данных «—» и серая
/// панель с «no data yet», устаревший источник — серая группа с «no data N s», armed — три
/// состояния, Link — одно из четырёх (решения — в BumblebeeGcs.Logic, там же тесты).
/// </summary>
public sealed class DashboardPage : Grid
{
    private readonly AppState _app;
    private readonly TelemetryStore _t;

    // Hero (the Control tile: who is in control, display only)
    private readonly StatTile _modeTile, _stateTile, _batteryTile, _altTile, _linkTile, _controlTile;

    // The latest change of who is in control, as its own line under the tiles
    private readonly Border _eventCard;
    private readonly FontIcon _eventIcon;
    private readonly TextBlock _eventTime, _eventText, _eventMode;
    private int _eventsVersion = -1;

    // Cameras
    private readonly CameraView _front, _bottom, _pip;
    private bool _pipBig;

    // Panels
    private readonly AttitudeView _attitude = new();
    private readonly ReadoutRow _roll = new("Roll"), _pitch = new("Pitch"), _yaw = new("Yaw");
    private readonly TextBlock _attitudeHint;
    private readonly StackPanel _attitudeBody;
    private readonly LabeledBarRow _batteryBar;
    private readonly ReadoutRow _x, _y, _z, _vx, _vy, _vz;
    private readonly LabeledBarRow _hSpeed, _vSpeed, _angRate, _imuAccel;
    private readonly LabeledBarRow _cpuTemp, _cpuLoad, _load135, _ram;
    private readonly ChartView _chartAlt, _chartSpd, _chartBat;
    private readonly PositionMapView _map;
    private readonly StackPanel _logList = new() { Spacing = Palette.S0 };
    private int _logVersion = -1;
    private readonly PanelCard _attitudePanel, _piPanel, _mapPanel;
    // Rows fed by one source: greyed together, with their own "no data N s" line (as on the Mac).
    private readonly SourceGroup _batteryGroup, _poseGroup, _velGroup, _speedGroup, _imuGroup;

    private readonly Grid _masonry = new() { ColumnSpacing = Palette.S4 };
    private readonly FrameworkElement[] _panels;
    private int _masonryCols;

    private bool _dirty = true, _dirtyMetrics = true;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _refresh;
    private readonly Action _onTelemetry, _onMetrics, _onReconnected;

    private const string AttitudeHint = "Pitch + = nose down (ROS) · yaw ENU, 0 = east";

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
        _controlTile = new StatTile("Control", IconGlyphs.Unknown, Palette.Caution);
        var hero = new AdaptiveGridPanel { MinItemWidth = 190, Spacing = Palette.S3 };
        foreach (var tile in new[] { _modeTile, _stateTile, _batteryTile, _altTile, _linkTile, _controlTile })
            hero.Children.Add(tile);

        // MARK: Control event line (display only; hidden until the first change)
        _eventIcon = Ui.Icon(IconGlyphs.Flag, Palette.IconSm, Palette.Caution);
        _eventTime = Ui.Text("", Fonts.MonoSmall, Palette.Muted);
        _eventText = Ui.Text("", Fonts.BodyStrong, Palette.Text);
        _eventMode = Ui.Text("", Fonts.MonoSmall, Palette.Muted);
        foreach (var t in new[] { _eventTime, _eventText, _eventMode }) t.VerticalAlignment = VerticalAlignment.Center;
        _eventIcon.VerticalAlignment = VerticalAlignment.Center;
        _eventCard = Ui.GlassCard(Ui.HStack(Palette.S2, _eventIcon, _eventTime, _eventText, _eventMode),
            Palette.RControl, new Thickness(Palette.S3, Palette.S2, Palette.S3, Palette.S2));
        _eventCard.Visibility = Visibility.Collapsed;

        // MARK: Cameras
        _front = new CameraView { Host = app.DroneHost, Topic = "/second_camera/image_raw" };
        _bottom = new CameraView { Host = app.DroneHost, Topic = "/main_camera/image_raw" };
        _pip = new CameraView(showFlipButton: false)
        {
            Host = app.DroneHost,
            Topic = "/aruco_map/image",
            Quality = 50, Fps = 3, StreamWidth = 160, StreamHeight = 120,
            Width = 120, Height = 90,
            Compact = true,
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
        var rpyRow = new Grid { ColumnSpacing = Palette.S3 };
        foreach (var i in Enumerable.Range(0, 3))
            rpyRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        Grid.SetColumn(_roll, 0); Grid.SetColumn(_pitch, 1); Grid.SetColumn(_yaw, 2);
        rpyRow.Children.Add(_roll); rpyRow.Children.Add(_pitch); rpyRow.Children.Add(_yaw);
        // Цифра Pitch — в ROS-конвенции, как get_telemetry() у учеников; рисунок исправлен.
        _attitudeHint = Ui.Text(AttitudeHint, Fonts.MonoSmall, Palette.Muted);
        _attitudeHint.TextWrapping = TextWrapping.Wrap;
        _attitudeBody = Ui.VStack(Palette.S3, attitudeCentered, rpyRow, _attitudeHint);

        var divider = new Border { Height = 1, Background = Palette.Brush(Palette.Hairline) };
        _batteryGroup = new SourceGroup(_batteryBar);
        _poseGroup = new SourceGroup(_x, _y, _z);
        _velGroup = new SourceGroup(_vx, _vy, _vz);
        _speedGroup = new SourceGroup(_hSpeed, _vSpeed);
        _imuGroup = new SourceGroup(_angRate, _imuAccel);

        _logList.Children.Add(Ui.Text("—", Fonts.MonoSmall, Palette.Muted));
        var logScroll = new ScrollViewer
        {
            Content = _logList,
            MaxHeight = 360,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };

        _attitudePanel = new PanelCard("Attitude", IconGlyphs.Attitude, _attitudeBody);
        _piPanel = new PanelCard("Raspberry Pi", IconGlyphs.Cpu, _cpuTemp, _cpuLoad, _load135, _ram);
        _mapPanel = new PanelCard("Position Map", IconGlyphs.Map, _map);
        _panels = new FrameworkElement[]
        {
            _attitudePanel,
            new PanelCard("Telemetry", IconGlyphs.Telemetry, _batteryGroup.Panel, _poseGroup.Panel, divider, _velGroup.Panel),
            new PanelCard("Flight Data", IconGlyphs.FlightData, _speedGroup.Panel, _imuGroup.Panel),
            _piPanel,
            new PanelCard("Charts", IconGlyphs.Charts, _chartAlt, _chartSpd, _chartBat),
            _mapPanel,
            new PanelCard("Messages", IconGlyphs.Messages, logScroll),
        };

        // MARK: Layout
        var stack = Ui.VStack(Palette.S4, hero, _eventCard, cameras, _masonry);
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

    /// <summary>Rows fed by one source: greyed together, with a right-aligned "no data N s" under them.</summary>
    private sealed class SourceGroup
    {
        public readonly StackPanel Panel = new() { Spacing = Palette.S3 };
        private readonly UIElement[] _rows;
        private readonly TextBlock _note = Ui.Text("", Fonts.MonoSmall, Palette.Caution);

        public SourceGroup(params UIElement[] rows)
        {
            _rows = rows;
            foreach (var r in rows) Panel.Children.Add(r);
            _note.HorizontalAlignment = HorizontalAlignment.Right;
            _note.Visibility = Visibility.Collapsed;
            Panel.Children.Add(_note);
        }

        public void Set(FreshStatus s)
        {
            foreach (var r in _rows) Stale.Dim(r, !s.IsFresh);
            _note.Text = s.Note ?? "";
            _note.Visibility = s.Note is null ? Visibility.Collapsed : Visibility.Visible;
        }
    }

    private void RefreshTelemetry()
    {
        var now = MonoClock.Now;
        var state = Freshness.Status(_t.StateAt, now, TelemetrySource.State);
        var pose = Freshness.Status(_t.PoseAt, now, TelemetrySource.Pose);
        var vel = Freshness.Status(_t.VelocityAt, now, TelemetrySource.Velocity);
        var imu = Freshness.Status(_t.ImuAt, now, TelemetrySource.Imu);
        var att = Freshness.Status(_t.AttitudeAt, now, TelemetrySource.Attitude);
        var bat = Freshness.Status(_t.BatteryAt, now, TelemetrySource.Battery);

        // MARK: Hero
        _modeTile.Update(ModeLogic.DisplayMode(_t.Mode), Palette.Primary);
        _modeTile.SetCaption(state.IsFresh ? ModeLogic.Explain(_t.Mode) : state.Note!, state.IsFresh ? null : Palette.Caution);
        _modeTile.SetDimmed(!state.IsFresh);

        var armed = ArmedLogic.Display(_t.Armed, _t.LastKnownArmed);
        var armedColor = Palette.ForTone(armed.Tone);
        _stateTile.Update(armed.Value, armedColor, _t.Armed switch
        {
            true => IconGlyphs.Armed,
            false => IconGlyphs.Disarmed,
            null => _t.LastKnownArmed == true ? IconGlyphs.Caution : IconGlyphs.Unknown,
        }, valueColor: _t.Armed is null ? armedColor : Palette.Text);
        _stateTile.SetCaption(armed.Caption);

        var battery = _t.Battery;
        _batteryTile.Update(battery.Short, Palette.ForTone(battery.Tone),
            battery.HasLevel ? IconGlyphs.Battery : IconGlyphs.BatteryUnknown);
        _batteryTile.SetCaption(bat.IsFresh ? battery.Caption : bat.Note!, bat.IsFresh ? null : Palette.Caution);
        _batteryTile.SetDimmed(!bat.IsFresh);

        _altTile.Update(Format.Fixed(_t.PosZ, 2, "m"), Palette.Primary);
        _altTile.SetCaption(pose.Note ?? "", Palette.Caution);
        _altTile.SetDimmed(!pose.IsFresh);

        var link = _t.Link;
        _linkTile.Update(LinkLogic.Text(link), Palette.ForTone(LinkLogic.ToneOf(link)), link switch
        {
            LinkState.Ok or LinkState.NoDrone => IconGlyphs.Link,
            _ => IconGlyphs.Caution,
        });
        _linkTile.SetCaption(LinkLogic.Caption(link, _t.RosConnected, state), Palette.Caution);

        var who = _t.InControl;
        var whoColor = Palette.ForTone(ModeLogic.ControllerTone(who));
        _controlTile.Update(ModeLogic.ControllerText(who), whoColor, ControllerGlyph(who),
            valueColor: who == Controller.Unknown ? Palette.Caution : Palette.Text);
        _controlTile.SetCaption(ModeLogic.ControlCaption(who, _t.Armed));
        RefreshEvent(whoColor);

        // MARK: Attitude (IMU orientation when valid, else pose)
        _attitude.Update(_t.Roll, _t.Pitch);
        _roll.Set(Format.Degrees(_t.Roll));
        _pitch.Set(Format.Degrees(_t.Pitch));
        _yaw.Set(Format.Degrees(_t.Yaw));
        _attitudeHint.Text = AttitudeHint + (_t.Roll is null ? "" : _t.AttitudeFromImu ? " · from IMU" : " · from pose");
        Stale.Dim(_attitudeBody, !att.IsFresh);
        _attitudePanel.SetNote(att.Note);

        // MARK: Telemetry
        _batteryBar.Set(battery.Text, battery.Pct ?? 0, Palette.ForTone(battery.Tone));
        _batteryGroup.Set(bat);
        _x.Set(Format.Signed(_t.PosX, "m"));
        _y.Set(Format.Signed(_t.PosY, "m"));
        _z.Set(Format.Signed(_t.PosZ, "m"));
        _poseGroup.Set(pose);
        _vx.Set(Format.Signed(_t.Vx, "m/s"));
        _vy.Set(Format.Signed(_t.Vy, "m/s"));
        _vz.Set(Format.Signed(_t.Vz, "m/s"));
        _velGroup.Set(vel);

        // MARK: Flight data
        _hSpeed.Set(Format.Fixed(_t.SpeedH, 2, "m/s"), MathUtil.PctOf(_t.SpeedH ?? 0, 5));
        _vSpeed.Set(Format.Fixed(_t.SpeedV, 2, "m/s"), MathUtil.PctOf(_t.SpeedV ?? 0, 3));
        _speedGroup.Set(vel);
        _angRate.Set(Format.Fixed(_t.GyroMag, 1, "°/s"), MathUtil.PctOf(_t.GyroMag ?? 0, 360));
        _imuAccel.Set(Format.Fixed(_t.AccelMag, 2, "m/s²"), MathUtil.PctOf(_t.AccelMag ?? 0, 30));
        _imuGroup.Set(imu);

        // MARK: Charts & map
        _chartAlt.SetStale(pose.Note);
        _chartSpd.SetStale(vel.Note);
        _chartBat.SetStale(bat.Note);
        _chartAlt.Refresh();
        _chartSpd.Refresh();
        _chartBat.Refresh();
        _map.Refresh();
        Stale.Dim(_map, !pose.IsFresh);
        _mapPanel.SetNote(pose.Note);

        RefreshMetricsFreshness(now);
        RefreshLog();
    }

    private static string ControllerGlyph(Controller c) => c switch
    {
        Controller.Program => IconGlyphs.Cpu,
        Controller.Pilot => IconGlyphs.Pilot,
        Controller.Px4 => IconGlyphs.Mode,
        Controller.Disarmed => IconGlyphs.Disarmed,
        _ => IconGlyphs.Unknown,
    };

    /// <summary>The latest control event: "12:03:11  Pilot took control  POSCTL · pilot, position hold".</summary>
    private void RefreshEvent(Color ownerColor)
    {
        _eventIcon.Foreground = Palette.Brush(ownerColor);
        if (_t.Events.Version == _eventsVersion) return;
        _eventsVersion = _t.Events.Version;
        if (_t.Events.Latest is not ControlEvent ev)
        {
            _eventCard.Visibility = Visibility.Collapsed;
            return;
        }
        _eventTime.Text = ev.Time;
        _eventText.Text = ev.Text;
        _eventMode.Text = ModeLogic.ModeWithExplanation(ev.Mode);
        _eventCard.Visibility = Visibility.Visible;
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

    /// <summary>Metrics older than 6 s (:8888 stopped answering) or none yet: grey with "no data N s" / "no data yet".</summary>
    private void RefreshMetricsFreshness(double now)
    {
        var s = Freshness.Status(_app.Metrics.LastArrival, now, TelemetrySource.Metrics);
        foreach (var r in new UIElement[] { _cpuTemp, _cpuLoad, _load135, _ram }) Stale.Dim(r, !s.IsFresh);
        _piPanel.SetNote(s.Note);
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
